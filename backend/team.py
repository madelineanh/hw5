"""Shared plumbing for the Campus Customs agent team.

- one model (gpt-6-luna via Portkey) for every agent
- one MCP connection to mcp_server/server.py; each agent sees only its allowed tools
- a `delegate` tool on every agent, so any agent can hand work to any other
- guardrails (human-only money tools, tool allowlists, depth/budget/bounce-back limits, token limits)
- an audit log of every agent-loop step, appended to output/audit_trail.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage

from models import AgentName, AuditLog, TeamDeps

BACKEND = Path(__file__).resolve().parent
HW_ROOT = BACKEND.parent
PROMPTS = BACKEND / "prompts"
SERVER = HW_ROOT / "mcp_server" / "server.py"
DEFAULT_DB = HW_ROOT / "data" / "campus_customs_new.db"
AUDIT_FILE = Path(os.environ.get("CAMPUS_CUSTOMS_AUDIT", HW_ROOT / "output" / "audit_trail.json"))

MODEL_NAME = "gpt-6-luna"

# Token/cost guardrails. One RunUsage is shared by the Boss and every delegated
# agent, so these caps bound the whole ticket, not each agent separately.
USAGE_LIMITS = UsageLimits(request_limit=40, tool_calls_limit=60, total_tokens_limit=400_000)
MAX_OUTPUT_TOKENS = 16_000  # reasoning tokens count toward this, so leave headroom
MAX_DEPTH = 3  # boss -> specialist -> specialist -> specialist
MAX_DELEGATIONS = 8  # per top-level run

HUMAN_ONLY_TOOLS = {"execute_approval", "reject_approval"}  # only the dashboard's Approve/Reject routes
PREPARE_TOOLS = {"prepare_payment", "prepare_purchase"}
WRITE_TOOLS = PREPARE_TOOLS | {"update_ticket_status"}

# Which MCP tools each role may see and call.
TOOL_ACCESS: dict[str, set[str]] = {
    "boss": {"get_shop_date", "list_open_tickets", "get_ticket", "update_ticket_status", "get_cash_balance", "list_pending_approvals"},
    "inventory": {
        "get_shop_date", "get_ticket", "check_inventory_stock", "list_sku_sizes",
        "list_vendors", "get_vendor_open_invoices", "get_sku_pricing_and_margin",
    },
    "accounting": {
        "get_shop_date", "get_ticket", "get_cash_balance", "list_payments", "get_invoice",
        "get_vendor_open_invoices", "get_sku_pricing_and_margin", "quote_bulk_discount",
        "prepare_payment", "prepare_purchase", "list_pending_approvals",
    },
    "facilities": {"get_shop_date", "get_ticket", "get_lease_rent_due", "list_payments"},
    "customer_service": {"get_shop_date", "get_ticket", "check_inventory_stock", "list_sku_sizes", "list_vendors"},
}

AGENTS: dict[str, Agent[TeamDeps, Any]] = {}  # filled in by the per-role modules
ACTIVE_AUDITS: dict[str, AuditLog] = {}  # runs in progress, so the dashboard can show live activity


# ---------------------------------------------------------------------- audit


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(deps: TeamDeps, event: str, **detail: Any) -> None:
    deps.audit.events.append({
        "timestamp": now(),
        "run_id": deps.run_id,
        "seq": len(deps.audit.events) + 1,
        "ticket_id": deps.ticket_id,
        "agent": deps.agent,
        "chain": " > ".join(deps.chain),
        "depth": deps.depth,
        "event": event,
        **detail,
    })


def flush_audit(audit: AuditLog) -> None:
    """Append this run's events to output/audit_trail.json. Never wipes earlier runs."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(AUDIT_FILE.read_text(encoding="utf-8")) if AUDIT_FILE.exists() else []
        if not isinstance(existing, list):
            existing = [existing]
    except json.JSONDecodeError:
        # Keep the unreadable file instead of overwriting it.
        AUDIT_FILE.rename(AUDIT_FILE.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json"))
        existing = []
    existing.extend(audit.events)
    AUDIT_FILE.write_text(json.dumps(existing, indent=2, default=str) + "\n", encoding="utf-8")


def _usage_dict(usage: RunUsage) -> dict[str, int]:
    return {
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def _log_request(deps: TeamDeps, request: ModelRequest) -> None:
    for part in request.parts:
        if isinstance(part, UserPromptPart):
            record(deps, "prompt", content=part.content)
        elif isinstance(part, ToolReturnPart):
            record(deps, "tool_result", tool=part.tool_name, tool_call_id=part.tool_call_id, result=part.content)
        elif isinstance(part, RetryPromptPart):
            record(deps, "tool_retry", tool=part.tool_name, tool_call_id=part.tool_call_id, error=str(part.content))


def _log_response(deps: TeamDeps, response: ModelResponse, step: int) -> None:
    calls = [
        {"tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict()}
        for p in response.parts
        if isinstance(p, ToolCallPart)
    ]
    text = "\n".join(p.content for p in response.parts if isinstance(p, TextPart))
    record(
        deps,
        "model_response",
        step=step,
        model=response.model_name,
        tool_calls=calls,
        text=text or None,
        usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
    )


# ------------------------------------------------------------------ model/MCP


@lru_cache(maxsize=1)
def model() -> OpenAIResponsesModel:
    load_dotenv(HW_ROOT.parent / ".env")  # PORTKEY_API_KEY lives in the parent folder's .env
    load_dotenv(HW_ROOT / ".env")
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing from .env")
    client = AsyncOpenAI(
        api_key=key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": key},
        timeout=120,
        max_retries=2,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


async def guard_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]) -> Any:
    """Harness-level guardrails that run before every MCP call, whatever the prompt says."""
    deps = ctx.deps
    if name in HUMAN_ONLY_TOOLS:
        record(deps, "guardrail_block", tool=name, args=args, reason="human-only tool; agents can only prepare payments")
        return {"ok": False, "error": f"{name} is human-only. Prepare the payment and let a person approve it in the dashboard."}
    if name not in TOOL_ACCESS[deps.agent]:
        record(deps, "guardrail_block", tool=name, args=args, reason="tool not allowed for this role")
        return {"ok": False, "error": f"{deps.agent} is not allowed to call {name}"}
    if name == "update_ticket_status" and deps.depth > 0:
        record(deps, "guardrail_block", tool=name, args=args, reason="only the top-level Boss sets ticket status")
        return {"ok": False, "error": "Only the top-level Boss run may change ticket status. Report your answer instead."}
    if name in PREPARE_TOOLS:
        # Stamp who prepared it and for which ticket; the model can't spoof either.
        args = {**args, "requested_by": deps.agent, "ticket_id": args.get("ticket_id") or deps.ticket_id}
    if name in WRITE_TOOLS:
        record(deps, "db_write_attempt", tool=name, args=args)
    return await call_tool(name, args)


@lru_cache(maxsize=1)
def mcp_toolset() -> MCPToolset:
    db = os.environ.get("CAMPUS_CUSTOMS_DB", str(DEFAULT_DB))
    transport = StdioTransport(
        command=sys.executable,
        args=[str(SERVER)],
        env={**os.environ, "CAMPUS_CUSTOMS_DB": db},
        cwd=str(HW_ROOT),
    )
    return MCPToolset(transport, id="campus-customs", process_tool_call=guard_tool_call, max_retries=2)


def role_toolset(role: AgentName):
    allowed = TOOL_ACCESS[role]
    return mcp_toolset().filtered(lambda ctx, tool_def: tool_def.name in allowed)


# ------------------------------------------------------------------ delegation


async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
    """Hand a specific task to any other Campus Customs agent and get their report back.

    Args:
        to: boss, inventory, accounting, facilities, or customer_service.
        task: Exactly what you need back, the ticket id, and the facts you already have.
    """
    deps = ctx.deps
    root = deps.root
    refusal = None
    if to == deps.agent:
        refusal = "You cannot delegate to yourself."
    elif len(deps.chain) > 1 and to == deps.chain[-2]:
        refusal = f"{to} called you. Do not bounce the task back; put your question in your report instead."
    elif deps.depth + 1 > deps.max_depth:
        refusal = f"Delegation depth limit ({deps.max_depth}) reached. Finish with what you have."
    elif root.delegations_used >= root.max_delegations:
        refusal = f"Delegation budget ({root.max_delegations} per run) used up. Finish with what you have."
    if refusal:
        record(deps, "delegation_refused", to=to, task=task, reason=refusal)
        return json.dumps({"ok": False, "error": refusal})

    root.delegations_used += 1
    child = TeamDeps(
        run_id=deps.run_id,
        agent=to,
        chain=[*deps.chain, to],
        audit=deps.audit,
        ticket_id=deps.ticket_id,
        max_depth=deps.max_depth,
        max_delegations=deps.max_delegations,
        counter_owner=root,
    )
    record(deps, "delegation_sent", to=to, task=task, delegations_used=root.delegations_used)
    try:
        output = await run_agent(to, task, child, usage=ctx.usage)
    except UsageLimitExceeded:
        raise  # the whole ticket is over budget: stop everything
    except Exception as exc:
        # One teammate failing should not sink the whole ticket; tell the caller and carry on.
        record(deps, "delegation_failed", to=to, error_type=type(exc).__name__, error=str(exc)[:500])
        return json.dumps({"ok": False, "error": f"{to} could not finish ({type(exc).__name__}). Continue with what you have."})
    record(deps, "delegation_returned", from_agent=to)
    return output.model_dump_json()


def runtime_instructions(ctx: RunContext[TeamDeps]) -> str:
    """Per-run facts the prompt files can't know: who called, ticket, remaining budget."""
    d = ctx.deps
    money = (
        "Agents never move money. Use prepare_payment / prepare_purchase to create a pending approval; "
        "a person approves it in the dashboard, and only then does cash change."
    )
    left = d.root.max_delegations - d.root.delegations_used
    return (
        f"Runtime context:\n- You are: {d.agent}\n- Call chain: {' > '.join(d.chain)}\n"
        f"- Ticket: {d.ticket_id if d.ticket_id is not None else 'not specified'}\n- {money}\n"
        f"- Delegations left this run: {left}; max depth {d.max_depth}, current depth {d.depth}.\n"
        f"- You may delegate to any teammate except yourself"
        + (f" and {d.chain[-2]} (your caller; answer them in your report instead)." if len(d.chain) > 1 else ".")
    )


def build_agent(role: AgentName, output_type: type) -> Agent[TeamDeps, Any]:
    agent = Agent(
        model(),
        name=role,
        instructions=[(PROMPTS / f"{role}.md").read_text(encoding="utf-8"), runtime_instructions],
        deps_type=TeamDeps,
        output_type=output_type,
        toolsets=[role_toolset(role)],
        tools=[delegate],
        model_settings={"max_tokens": MAX_OUTPUT_TOKENS},
        retries=2,
    )
    AGENTS[role] = agent
    return agent


# ------------------------------------------------------------------ agent loop


async def run_agent(role: AgentName, prompt: str, deps: TeamDeps, usage: RunUsage | None = None) -> Any:
    """Run one agent's loop (model -> tools -> model ... -> output) and audit every step."""
    agent = AGENTS[role]
    record(deps, "agent_started", model=MODEL_NAME, tools=sorted(TOOL_ACCESS[role]) + ["delegate"])
    step = 0
    try:
        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=USAGE_LIMITS) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    _log_request(deps, node.request)
                elif Agent.is_call_tools_node(node):
                    step += 1
                    _log_response(deps, node.model_response, step)
            output = run.result.output
            record(deps, "agent_finished", steps=step, output=output.model_dump(), usage_so_far=_usage_dict(run.usage))
            return output
    except Exception as exc:
        record(deps, "agent_error", steps=step, error_type=type(exc).__name__, error=str(exc)[:1000])
        raise
