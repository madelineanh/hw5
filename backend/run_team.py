"""Run the Campus Customs agent team on one or more tickets (CLI; the API uses work_ticket too).

    .venv/bin/python backend/run_team.py --ticket 101
    .venv/bin/python backend/run_team.py --all-open

Agents never move money: payments and purchases come back as pending approvals
that a person approves in the dashboard (POST /approvals/{id}/approve).
Every run appends its agent-loop steps to output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path


async def work_ticket(ticket_id: int, run_id: str | None = None) -> dict:
    """One Boss-led run on one ticket. Requires the MCP toolset to be entered already."""
    from models import AuditLog, TeamDeps
    from team import (ACTIVE_AUDITS, MAX_DELEGATIONS, MAX_DEPTH, MODEL_NAME, USAGE_LIMITS,
                      flush_audit, mcp_toolset, record, run_agent)

    run_id = run_id or str(uuid.uuid4())
    audit = AuditLog(run_id=run_id, db_path=os.environ["CAMPUS_CUSTOMS_DB"])
    ACTIVE_AUDITS[run_id] = audit
    deps = TeamDeps(
        run_id=run_id, agent="boss", chain=["boss"], audit=audit,
        ticket_id=ticket_id, max_depth=MAX_DEPTH, max_delegations=MAX_DELEGATIONS,
    )
    record(
        deps, "run_started", model=MODEL_NAME, database=audit.db_path,
        limits={"request_limit": USAGE_LIMITS.request_limit, "tool_calls_limit": USAGE_LIMITS.tool_calls_limit,
                "total_tokens_limit": USAGE_LIMITS.total_tokens_limit, "max_depth": MAX_DEPTH,
                "max_delegations": MAX_DELEGATIONS},
    )
    try:
        decision = await run_agent("boss", f"Work ticket {ticket_id} end to end.", deps)
        # A completed run resolves the ticket: the team has done everything agents may do.
        # Anything still needing a person lives in pending_approvals, not in an open ticket.
        # (Via MCP, never direct SQL.)
        current = await mcp_toolset().direct_call_tool("get_ticket", {"ticket_id": ticket_id})
        final_status = decision.new_status if decision.new_status == "in_progress" else "resolved"
        if current.get("status") != final_status:
            pending = [a.approval_id for a in decision.approvals_needed if a.approval_id]
            note = "Agent run complete." + (f" Waiting on human approval(s): {pending}." if pending else "")
            synced = await mcp_toolset().direct_call_tool(
                "update_ticket_status", {"ticket_id": ticket_id, "status": final_status, "note": note},
            )
            record(deps, "harness_status_sync", old_status=current.get("status"), boss_status=decision.new_status,
                   new_status=final_status, result=synced)
        record(deps, "run_finished", stop_reason="completed", delegations_used=deps.delegations_used,
               new_status=final_status, boss_status=decision.new_status)
        return decision.model_dump()
    except Exception as exc:
        record(deps, "run_finished", stop_reason="error", error_type=type(exc).__name__, error=str(exc)[:1000])
        raise
    finally:
        flush_audit(audit)
        ACTIVE_AUDITS.pop(run_id, None)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket", type=int, action="append", help="Ticket id to work (repeatable)")
    parser.add_argument("--all-open", action="store_true", help="Work every open ticket, oldest first")
    parser.add_argument("--db", help="Database path (default: data/campus_customs_new.db)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    # Must be set before the agents (and their MCP connection) are imported.
    os.environ["CAMPUS_CUSTOMS_DB"] = str(Path(args.db).resolve() if args.db else root / "data" / "campus_customs_new.db")

    import accounting, boss, customer_service, facilities, inventory  # noqa: F401  (registers the 5 agents)
    from team import mcp_toolset

    async with mcp_toolset():  # one MCP server process shared by all agents
        tickets = list(args.ticket or [])
        if args.all_open:
            listing = await mcp_toolset().direct_call_tool("list_open_tickets", {})
            tickets += [t["id"] for t in listing["tickets"] if t["id"] not in tickets]
        if not tickets:
            parser.error("give --ticket N or --all-open")
        for ticket_id in tickets:  # one at a time so each sees the cash the last one left
            print(f"\n=== Ticket {ticket_id} ===")
            print(json.dumps(await work_ticket(ticket_id), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
