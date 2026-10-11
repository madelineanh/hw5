"""FastAPI backend for the Campus Customs desk dashboard.

Start from the backend/ directory:
    uvicorn main:app --reload --port 8000

All shop data goes through the campus-customs MCP server (same as the agents).
Agents can only prepare payments; POST /approvals/{id}/approve is the only
route that changes the cash balance, and only after a human clicks Approve.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

HW_ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_DB = HW_ROOT / "data" / "campus_customs.db"
WORKING_DB = Path(os.environ.setdefault("CAMPUS_CUSTOMS_DB", str(HW_ROOT / "data" / "campus_customs_new.db")))

import accounting, boss, customer_service, facilities, inventory  # noqa: E402,F401  (registers the 5 agents)
from models import AuditLog  # noqa: E402
from run_team import work_ticket  # noqa: E402
from team import ACTIVE_AUDITS, AUDIT_FILE, flush_audit, mcp_toolset, now  # noqa: E402

RUNS: dict[str, dict[str, Any]] = {}  # run_id -> status/result for runs started by this server


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_toolset():  # one MCP server process for the API and every agent
        yield


app = FastAPI(title="Campus Customs Desk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",  # any other local port
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp(tool: str, args: dict | None = None) -> dict:
    return await mcp_toolset().direct_call_tool(tool, args or {})


def run_in_progress() -> dict | None:
    return next((r for r in RUNS.values() if r["status"] == "running"), None)


def log_human_action(event: str, **detail: Any) -> None:
    """Human actions (approve/reject/reset) go into the same append-only audit trail."""
    run_id = f"human-{uuid.uuid4()}"
    flush_audit(AuditLog(run_id=run_id, db_path=str(WORKING_DB), events=[{
        "timestamp": now(), "run_id": run_id, "seq": 1, "ticket_id": detail.pop("ticket_id", None),
        "agent": "human", "chain": "human", "depth": 0, "event": event, **detail,
    }]))


# ------------------------------------------------------------------- 1. tickets


@app.get("/tickets")
async def list_tickets():
    """All tickets, each marked open or resolved."""
    data = await mcp("list_all_tickets")
    pending = (await mcp("list_pending_approvals", {"status": "pending"}))["approvals"]
    for t in data["tickets"]:
        t["pending_approvals"] = sum(1 for a in pending if a["ticket_id"] == t["id"])
        t["state"] = "resolved" if t["is_resolved"] else "open"
        t["running"] = any(r["ticket_id"] == t["id"] and r["status"] == "running" for r in RUNS.values())
    return data


# ------------------------------------------------------------------ 2. run team


async def _run(run_id: str, ticket_id: int) -> None:
    try:
        RUNS[run_id]["result"] = await work_ticket(ticket_id, run_id=run_id)
        RUNS[run_id]["status"] = "completed"
    except Exception as exc:  # recorded in the audit trail too
        RUNS[run_id].update(status="error", error=f"{type(exc).__name__}: {exc}"[:1000])
    RUNS[run_id]["finished_at"] = now()


@app.post("/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket in the background; poll /runs/{run_id} or /activity."""
    ticket = await mcp("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, f"ticket {ticket_id} not found")
    if busy := run_in_progress():
        raise HTTPException(409, f"ticket {busy['ticket_id']} is still running (run {busy['run_id']}); one run at a time keeps cash checks accurate")
    run_id = str(uuid.uuid4())
    RUNS[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "started_at": now()}
    asyncio.create_task(_run(run_id, ticket_id))
    return RUNS[run_id]


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Status of one run (running / completed / error) and the Boss's final decision."""
    if run_id not in RUNS:
        raise HTTPException(404, "unknown run id (runs are tracked until the server restarts; see /activity)")
    return RUNS[run_id]


@app.get("/tickets/{ticket_id}/summary")
async def ticket_summary(ticket_id: int):
    """Latest run on one ticket: the Boss's decision and a short line per agent (what it did, tools used)."""
    events = _load_events()
    started = [e for e in events if e.get("ticket_id") == ticket_id and e.get("event") == "run_started"]
    if not started:
        return {"ticket_id": ticket_id, "run_id": None, "agents": [], "decision": None}
    run_id = max(started, key=lambda e: e["timestamp"])["run_id"]
    run = [e for e in events if e.get("run_id") == run_id]
    agents: dict[str, dict] = {}
    for e in run:
        a = agents.setdefault(e["agent"], {"agent": e["agent"], "summary": None, "tools": [], "delegated_to": [], "approvals": []})
        if e["event"] == "tool_result" and e.get("tool") != "delegate" and e["tool"] not in a["tools"]:
            a["tools"].append(e["tool"])
        elif e["event"] == "delegation_sent" and e["to"] not in a["delegated_to"]:
            a["delegated_to"].append(e["to"])
        elif e["event"] == "agent_finished":
            out = e.get("output") or {}
            a["summary"] = out.get("decision") or out.get("summary")
            a["approvals"] = out.get("approvals_needed", [])
    finished = next((e for e in run if e["event"] == "run_finished"), None)
    boss = next((e.get("output") for e in run if e["event"] == "agent_finished" and e.get("depth") == 0), None)
    order = ["boss", "inventory", "accounting", "facilities", "customer_service"]
    return {
        "ticket_id": ticket_id, "run_id": run_id, "started_at": run[0]["timestamp"],
        "status": "running" if finished is None else finished.get("stop_reason"),
        "decision": boss, "agents": sorted(agents.values(), key=lambda a: order.index(a["agent"]) if a["agent"] in order else 9),
        "usage": next((e.get("usage_so_far") for e in run if e["event"] == "agent_finished" and e.get("depth") == 0), None),
    }


# ------------------------------------------------------------------- 3. activity


def _load_events() -> list[dict]:
    events: list[dict] = []
    if AUDIT_FILE.exists():
        try:
            events = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            events = []
    for audit in list(ACTIVE_AUDITS.values()):
        events.extend(audit.events)
    return events


def _simplify(e: dict) -> dict:
    """Add 'said' and 'tools' so the dashboard doesn't have to parse every event type."""
    said, tools = None, []
    kind = e.get("event")
    if kind == "model_response":
        said = e.get("text")
        tools = [c["tool"] for c in e.get("tool_calls", [])]
    elif kind == "tool_result":
        tools = [e.get("tool")]
    elif kind == "delegation_sent":
        said = f"→ {e.get('to')}: {e.get('task')}"
        tools = ["delegate"]
    elif kind == "agent_finished":
        out = e.get("output") or {}
        said = out.get("decision") or out.get("summary")
    elif kind in ("guardrail_block", "delegation_refused"):
        said = e.get("reason")
        tools = [e["tool"]] if e.get("tool") else []
    elif kind in ("human_approved", "human_rejected", "database_reset"):
        said = e.get("summary")
    return {**e, "said": said, "tools": tools}


@app.get("/activity")
async def activity(
    limit: int = Query(100, ge=1, le=1000),
    ticket_id: int | None = None,
    run_id: str | None = None,
):
    """Recent agent activity, newest first: who spoke, what they said, which tools they used.

    Includes runs still in progress, so the dashboard can poll this while a ticket runs.
    """
    events = _load_events()
    if ticket_id is not None:
        events = [e for e in events if e.get("ticket_id") == ticket_id]
    if run_id:
        events = [e for e in events if e.get("run_id") == run_id]
    events = sorted(events, key=lambda e: (e.get("timestamp", ""), e.get("seq", 0)), reverse=True)[:limit]
    return {"count": len(events), "running": [r for r in RUNS.values() if r["status"] == "running"],
            "events": [_simplify(e) for e in events]}


# ------------------------------------------------------------------ 4. approvals


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the person who clicked Approve")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@app.get("/approvals")
async def list_approvals(status: str = "pending"):
    """Payments and purchases the agents prepared, waiting for a human (status: pending/approved/rejected/all)."""
    return await mcp("list_pending_approvals", {"status": status})


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveBody):
    """Human clicked Approve: make the payment/purchase. The ONLY route that changes cash."""
    result = await mcp("execute_approval", {"approval_id": approval_id, "approved_by": body.approved_by})
    appr = next((a for a in (await mcp("list_pending_approvals", {"status": "all"}))["approvals"] if a["id"] == approval_id), {})
    log_human_action(
        "human_approved" if result.get("ok") else "human_approve_refused",
        ticket_id=appr.get("ticket_id"), approval_id=approval_id, approved_by=body.approved_by, result=result,
        summary=(f"{body.approved_by} approved {appr.get('kind')} ${appr.get('amount')} to {appr.get('payee')}; "
                 f"checking ${result.get('balance_before')} → ${result.get('balance_after')}") if result.get("ok") else result.get("error"),
    )
    if not result.get("ok"):
        raise HTTPException(409, result.get("error"))
    return result


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: RejectBody):
    """Human clicked Reject: decline a prepared payment. No money moves."""
    result = await mcp("reject_approval", {"approval_id": approval_id, "rejected_by": body.rejected_by, "reason": body.reason})
    log_human_action("human_rejected", approval_id=approval_id, rejected_by=body.rejected_by, result=result,
                     summary=f"{body.rejected_by} rejected approval {approval_id}: {body.reason}")
    if not result.get("ok"):
        raise HTTPException(409, result.get("error"))
    return result


# ----------------------------------------------------------------------- 5. cash


@app.get("/cash")
async def cash():
    """Current checking balance from cash_accounts."""
    data = await mcp("get_cash_balance", {"account": "checking"})
    pending = await mcp("list_pending_approvals", {"status": "pending"})
    return {**data, "pending_total": pending["total_amount"],
            "balance_after_pending": round(data["balance"] - pending["total_amount"], 2)}


# ---------------------------------------------------------------------- 6. reset


@app.post("/reset")
async def reset():
    """Restore data/campus_customs_new.db from the untouched original. The audit trail is kept."""
    if busy := run_in_progress():
        raise HTTPException(409, f"ticket {busy['ticket_id']} is still running; reset after it finishes")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    log_human_action("database_reset", summary=f"Reset {WORKING_DB.name} from {ORIGINAL_DB.name}")
    return {"ok": True, "database": str(WORKING_DB), "restored_from": str(ORIGINAL_DB),
            "cash": await mcp("get_cash_balance", {"account": "checking"})}


@app.get("/")
async def root():
    return {"ok": True, "service": "Campus Customs Desk API", "docs": "/docs"}
