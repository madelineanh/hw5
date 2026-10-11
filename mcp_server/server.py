"""Campus Customs MCP server.

Exposes shop-database tools to the agent team. All tools read from the
working copy, data/campus_customs_new.db. The original campus_customs.db
is never touched. Set CAMPUS_CUSTOMS_DB to point at a scratch copy for tests.

Money rules are enforced here, at the data layer, so no agent prompt can talk
its way around them. Agents can only PREPARE payments and purchases
(prepare_payment / prepare_purchase -> pending_approvals). Cash changes only in
execute_approval, which the dashboard's Approve route calls for a human.
"""

import calendar
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastmcp import FastMCP

DB_PATH = Path(
    os.environ.get(
        "CAMPUS_CUSTOMS_DB",
        Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db",
    )
)

# House policy for discounts (the database has no policy table, so it lives here).
MIN_MARGIN_PCT = 40.0  # never quote below a 40% margin on list price
MAX_DISCOUNT_PCT_WITHOUT_HUMAN = 15.0  # bigger discounts need a human sign-off

TICKET_STATUSES = {"open", "in_progress", "waiting_on_approval", "waiting_on_vendor", "resolved"}
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "customer service", "agent", "ai"}

mcp = FastMCP("campus-customs")


PENDING_APPROVALS_SQL = """CREATE TABLE IF NOT EXISTS pending_approvals (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,            -- invoice | rent | purchase
    ref_id INTEGER,                -- invoice id or lease id
    vendor_id INTEGER,
    sku TEXT, size TEXT, qty INTEGER,
    amount REAL NOT NULL,
    payee TEXT,
    reason TEXT NOT NULL,
    ticket_id INTEGER,
    requested_by TEXT NOT NULL,    -- agent that prepared it
    status TEXT NOT NULL,          -- pending | approved | rejected
    created_at TEXT NOT NULL,
    decided_by TEXT, decided_at TEXT, decision_note TEXT,
    payment_id INTEGER
)"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(PENDING_APPROVALS_SQL)  # workflow table for agent-prepared payments
    return conn


def _today(conn: sqlite3.Connection) -> str:
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


def _days_between(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def _add_one_month(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


def _approver_problem(approved_by: str) -> str | None:
    name = (approved_by or "").strip()
    if not name:
        return "approved_by is required: every payment needs a named human approver."
    if name.lower() in AGENT_NAMES:
        return f"approved_by '{name}' is an agent role, not a human. A person must approve payments."
    return None


# --------------------------------------------------------------------------- desk


@mcp.tool
def get_shop_date() -> dict:
    """Return the shop's official "today" (desk.date_today) and any desk notes.

    Every due-date, overdue, and ETA calculation must use this date, never the real clock.
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk").fetchone()
    return dict(row)


# ------------------------------------------------------------------------ tickets


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved, oldest first, with all linked IDs."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
    return {"count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool
def list_all_tickets() -> dict:
    """List every ticket (open and resolved) with its status, for the dashboard."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    return {"count": len(rows), "tickets": [{**dict(r), "is_resolved": r["status"] == "resolved"} for r in rows]}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Look up one ticket by id: type, requester, subject, sku/size/qty, lease_id, invoice_id, status, notes."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return {"found": False, "ticket_id": ticket_id}
    return {"found": True, **dict(row)}


@mcp.tool
def update_ticket_status(ticket_id: int, status: str, note: str) -> dict:
    """Set a ticket's status and append a dated note explaining why.

    Allowed statuses: open, in_progress, waiting_on_approval, waiting_on_vendor, resolved.
    The note is appended to the ticket's notes; existing notes are never erased.
    """
    if status not in TICKET_STATUSES:
        return {"ok": False, "error": f"status must be one of {sorted(TICKET_STATUSES)}"}
    if not note.strip():
        return {"ok": False, "error": "a note explaining the status change is required"}
    with _connect() as conn:
        row = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"ticket {ticket_id} not found"}
        today = _today(conn)
        notes = (row["notes"] or "").rstrip()
        new_notes = f"{notes}\n[{today}] {status}: {note.strip()}".strip()
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, new_notes, ticket_id))
    return {"ok": True, "ticket_id": ticket_id, "old_status": row["status"], "new_status": status, "notes": new_notes}


# ---------------------------------------------------------------------- inventory


@mcp.tool
def check_inventory_stock(sku: str, size: str) -> dict:
    """Look up units on hand for one SKU in one size (e.g. CC-TEE-WHITE, S).

    Returns the inventory row, or found=False if that SKU/size does not exist.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku, "size": size}
    return {"found": True, **dict(row), "in_stock": row["qty"] > 0}


@mcp.tool
def list_sku_sizes(sku: str) -> dict:
    """List every size of one SKU with units on hand, so agents can see alternatives and totals."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?", (sku,)
        ).fetchall()
    if not rows:
        return {"found": False, "sku": sku}
    return {
        "found": True,
        "sku": sku,
        "name": rows[0]["name"],
        "sizes": [dict(r) for r in rows],
        "total_units": sum(r["qty"] for r in rows),
    }


# ------------------------------------------------------------------------ vendors


@mcp.tool
def list_vendors() -> dict:
    """List all vendors with their specialty and lead time in days (order to delivery)."""
    with _connect() as conn:
        rows = conn.execute("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id").fetchall()
    return {"vendors": [dict(r) for r in rows]}


@mcp.tool
def get_vendor_open_invoices(vendor_id: int) -> dict:
    """Check whether a vendor is blocked from shipping because the shop owes them money.

    Returns the vendor, its unpaid invoices (with days overdue vs. desk.date_today),
    and can_ship=False if any invoice is still open.
    """
    with _connect() as conn:
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return {"found": False, "vendor_id": vendor_id}
        today = _today(conn)
        rows = conn.execute(
            "SELECT id, amount, due_date, status, description FROM invoices WHERE vendor_id = ? AND status = 'open'",
            (vendor_id,),
        ).fetchall()
    open_invoices = [
        {**dict(r), "days_overdue": max(0, _days_between(today, r["due_date"])), "overdue": r["due_date"] < today}
        for r in rows
    ]
    return {
        "found": True,
        "vendor": dict(vendor),
        "date_today": today,
        "open_invoices": open_invoices,
        "total_owed": round(sum(r["amount"] for r in rows), 2),
        "can_ship": not open_invoices,
    }


# ----------------------------------------------------------------------- invoices


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """Look up one invoice with its vendor, amount, due date, status, and days overdue vs. desk.date_today."""
    with _connect() as conn:
        row = conn.execute(
            """SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, i.status, i.description
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "invoice_id": invoice_id}
        today = _today(conn)
    overdue = row["status"] == "open" and row["due_date"] < today
    return {
        "found": True,
        **dict(row),
        "date_today": today,
        "overdue": overdue,
        "days_overdue": max(0, _days_between(today, row["due_date"])) if overdue else 0,
    }


# ------------------------------------------------------------------------- leases


@mcp.tool
def get_lease_rent_due(lease_id: int) -> dict:
    """Look up a lease's monthly rent, landlord, and next due date.

    Also reports days until due, measured from desk.date_today (the shop's "today").
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "lease_id": lease_id}
        today = _today(conn)
        days_until_due = conn.execute(
            "SELECT CAST(julianday(?) - julianday(?) AS INTEGER)", (row["next_due"], today)
        ).fetchone()[0]
    return {
        "found": True,
        **dict(row),
        "date_today": today,
        "days_until_due": days_until_due,
        "overdue": days_until_due < 0,
    }


# ------------------------------------------------------------------ cash/payments


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """Return the current balance of a cash account (the shop only has 'checking')."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
    if row is None:
        return {"found": False, "account": account}
    return {"found": True, **dict(row)}


@mcp.tool
def list_payments() -> dict:
    """List every payment already made, newest first, so nothing is paid twice."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM payments ORDER BY id DESC").fetchall()
    return {"count": len(rows), "payments": [dict(r) for r in rows]}


# --------------------------------------------------------------- approvals
# Agents can only PREPARE money movements. They become rows in pending_approvals.
# Cash changes only in execute_approval, which the FastAPI /approvals/{id}/approve
# route calls after a human clicks Approve. Agents are never given execute_approval.


def _pay_invoice(conn: sqlite3.Connection, invoice_id: int, approved_by: str, today: str, account: str) -> dict:
    inv = conn.execute("SELECT id, vendor_id, amount, status FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if inv is None:
        return {"ok": False, "error": f"invoice {invoice_id} not found"}
    if inv["status"] != "open":
        return {"ok": False, "error": f"invoice {invoice_id} is already '{inv['status']}'; not paying twice"}
    acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if acct is None:
        return {"ok": False, "error": f"cash account '{account}' not found"}
    if inv["amount"] > acct["balance"]:
        return {"ok": False, "error": f"insufficient funds: invoice ${inv['amount']:.2f} > {account} balance ${acct['balance']:.2f}"}
    new_balance = round(acct["balance"] - inv["amount"], 2)
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES ('invoice', ?, ?, ?, ?, ?)",
        (invoice_id, inv["amount"], account, today, approved_by),
    )
    conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
    conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
    return {"ok": True, "payment_id": cur.lastrowid, "kind": "invoice", "invoice_id": invoice_id,
            "vendor_id": inv["vendor_id"], "amount": inv["amount"],
            "balance_before": acct["balance"], "balance_after": new_balance}


def _pay_rent(conn: sqlite3.Connection, lease_id: int, approved_by: str, today: str, account: str) -> dict:
    lease = conn.execute("SELECT id, landlord, monthly_rent, next_due FROM leases WHERE id = ?", (lease_id,)).fetchone()
    if lease is None:
        return {"ok": False, "error": f"lease {lease_id} not found"}
    already = conn.execute(
        "SELECT id, paid_at FROM payments WHERE kind = 'rent' AND ref_id = ? AND paid_at >= date(?, '-25 days')",
        (lease_id, today),
    ).fetchone()
    if already:
        return {"ok": False, "error": f"rent for lease {lease_id} was already paid on {already['paid_at']} (payment {already['id']}); not paying twice in one month"}
    acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if acct is None:
        return {"ok": False, "error": f"cash account '{account}' not found"}
    if lease["monthly_rent"] > acct["balance"]:
        return {"ok": False, "error": f"insufficient funds: rent ${lease['monthly_rent']:.2f} > {account} balance ${acct['balance']:.2f}"}
    new_balance = round(acct["balance"] - lease["monthly_rent"], 2)
    new_due = _add_one_month(lease["next_due"])
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES ('rent', ?, ?, ?, ?, ?)",
        (lease_id, lease["monthly_rent"], account, today, approved_by),
    )
    conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, lease_id))
    conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
    return {"ok": True, "payment_id": cur.lastrowid, "kind": "rent", "lease_id": lease_id, "landlord": lease["landlord"],
            "amount": lease["monthly_rent"], "paid_due_date": lease["next_due"], "next_due": new_due,
            "balance_before": acct["balance"], "balance_after": new_balance}


def _pay_purchase(conn: sqlite3.Connection, approval: sqlite3.Row, approved_by: str, today: str, account: str) -> dict:
    blocking = conn.execute(
        "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open'", (approval["vendor_id"],)
    ).fetchall()
    if blocking:
        ids = ", ".join(str(r["id"]) for r in blocking)
        return {"ok": False, "error": f"vendor {approval['vendor_id']} will not ship while invoice(s) {ids} are open; approve that payment first"}
    acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if acct is None:
        return {"ok": False, "error": f"cash account '{account}' not found"}
    if approval["amount"] > acct["balance"]:
        return {"ok": False, "error": f"insufficient funds: purchase ${approval['amount']:.2f} > {account} balance ${acct['balance']:.2f}"}
    new_balance = round(acct["balance"] - approval["amount"], 2)
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES ('purchase', ?, ?, ?, ?, ?)",
        (approval["id"], approval["amount"], account, today, approved_by),
    )
    conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
    lead = conn.execute("SELECT lead_days FROM vendors WHERE id = ?", (approval["vendor_id"],)).fetchone()["lead_days"]
    return {"ok": True, "payment_id": cur.lastrowid, "kind": "purchase", "vendor_id": approval["vendor_id"],
            "sku": approval["sku"], "size": approval["size"], "qty": approval["qty"], "amount": approval["amount"],
            "expected_arrival": (date.fromisoformat(today) + timedelta(days=lead)).isoformat(),
            "balance_before": acct["balance"], "balance_after": new_balance}


def _pending_duplicate(conn: sqlite3.Connection, kind: str, ref_id: int | None, sku: str | None = None, size: str | None = None):
    return conn.execute(
        """SELECT id FROM pending_approvals WHERE status = 'pending' AND kind = ?
           AND COALESCE(ref_id, -1) = COALESCE(?, -1) AND COALESCE(sku, '') = COALESCE(?, '') AND COALESCE(size, '') = COALESCE(?, '')""",
        (kind, ref_id, sku, size),
    ).fetchone()


def _cash_after_pending(conn: sqlite3.Connection, extra: float) -> dict:
    balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
    pending = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM pending_approvals WHERE status = 'pending'").fetchone()[0]
    return {
        "checking_balance": balance,
        "already_pending_total": round(pending, 2),
        "cash_after_this": round(balance - extra, 2),
        "cash_after_all_pending": round(balance - pending - extra, 2),
        "fits_with_all_pending": balance - pending - extra >= 0,
    }


@mcp.tool
def prepare_payment(kind: str, ref_id: int, reason: str, ticket_id: int | None = None, requested_by: str = "") -> dict:
    """Prepare (do NOT make) a payment for a human to approve in the dashboard.

    kind is 'invoice' (ref_id = invoice id) or 'rent' (ref_id = lease id). The amount
    always comes from the database. No cash moves; a pending approval is created and
    its id returned, along with what cash would be left after it and every other
    pending approval. Refuses duplicates, paid invoices, and missing records.
    """
    if kind not in {"invoice", "rent"}:
        return {"ok": False, "error": "kind must be 'invoice' or 'rent' (use prepare_purchase for restock orders)"}
    if not reason.strip():
        return {"ok": False, "error": "a reason is required"}
    with _connect() as conn:
        today = _today(conn)
        if kind == "invoice":
            row = conn.execute(
                "SELECT i.amount, i.status, i.vendor_id, v.name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ref_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": f"invoice {ref_id} not found"}
            if row["status"] != "open":
                return {"ok": False, "error": f"invoice {ref_id} is already '{row['status']}'"}
            amount, vendor_id, payee = row["amount"], row["vendor_id"], row["name"]
        else:
            row = conn.execute("SELECT monthly_rent, landlord FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": f"lease {ref_id} not found"}
            amount, vendor_id, payee = row["monthly_rent"], None, row["landlord"]
        if dup := _pending_duplicate(conn, kind, ref_id):
            return {"ok": False, "error": f"already pending as approval {dup['id']}", "approval_id": dup["id"]}
        cash = _cash_after_pending(conn, amount)
        if not cash["fits_with_all_pending"]:
            return {"ok": False, "error": "would overdraw checking once every pending approval is paid; nothing prepared", **cash}
        cur = conn.execute(
            """INSERT INTO pending_approvals (kind, ref_id, vendor_id, amount, payee, reason, ticket_id, requested_by, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (kind, ref_id, vendor_id, amount, payee, reason.strip(), ticket_id, requested_by or "agent", today),
        )
    return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "kind": kind, "ref_id": ref_id,
            "payee": payee, "amount": amount, **cash, "note": "No money moved. A human must click Approve."}


@mcp.tool
def prepare_purchase(vendor_id: int, sku: str, size: str, qty: int, reason: str,
                     ticket_id: int | None = None, requested_by: str = "") -> dict:
    """Prepare (do NOT place) a restock purchase for a human to approve in the dashboard.

    The amount is qty x pricing.unit_cost. Reports whether the vendor is currently
    blocked by an open invoice (approval will be refused until it is paid) and the
    cash left after this and every other pending approval. No cash moves.
    """
    if qty <= 0 or not reason.strip():
        return {"ok": False, "error": "qty must be > 0 and a reason is required"}
    with _connect() as conn:
        today = _today(conn)
        vendor = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"ok": False, "error": f"vendor {vendor_id} not found"}
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return {"ok": False, "error": f"no pricing for {sku}"}
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return {"ok": False, "error": f"{sku} size {size} is not a stocked item"}
        if dup := _pending_duplicate(conn, "purchase", None, sku, size):
            return {"ok": False, "error": f"already pending as approval {dup['id']}", "approval_id": dup["id"]}
        amount = round(price["unit_cost"] * qty, 2)
        blocking = [r["id"] for r in conn.execute(
            "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open'", (vendor_id,)).fetchall()]
        cash = _cash_after_pending(conn, amount)
        if not cash["fits_with_all_pending"]:
            return {"ok": False, "error": "would overdraw checking once every pending approval is paid; nothing prepared", **cash}
        cur = conn.execute(
            """INSERT INTO pending_approvals (kind, ref_id, vendor_id, sku, size, qty, amount, payee, reason, ticket_id, requested_by, status, created_at)
               VALUES ('purchase', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (vendor_id, sku, size, qty, amount, vendor["name"], reason.strip(), ticket_id, requested_by or "agent", today),
        )
    return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "kind": "purchase", "vendor": vendor["name"],
            "sku": sku, "size": size, "qty": qty, "unit_cost": price["unit_cost"], "amount": amount,
            "lead_days": vendor["lead_days"], "vendor_blocked_by_invoices": blocking, **cash,
            "note": "No money moved. A human must click Approve."}


@mcp.tool
def list_pending_approvals(status: str = "pending") -> dict:
    """List prepared payments/purchases. status: 'pending', 'approved', 'rejected', or 'all'."""
    with _connect() as conn:
        if status == "all":
            rows = conn.execute("SELECT * FROM pending_approvals ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM pending_approvals WHERE status = ? ORDER BY id", (status,)).fetchall()
    return {"count": len(rows), "approvals": [dict(r) for r in rows],
            "total_amount": round(sum(r["amount"] for r in rows), 2)}


@mcp.tool
def execute_approval(approval_id: int, approved_by: str, account: str = "checking") -> dict:
    """HUMAN-ONLY. Carry out a pending approval: the only tool that changes the cash balance.

    Called by the dashboard's Approve route, never by an agent. Re-checks every money
    rule (open invoice, no double rent, vendor not blocked, enough cash) and, in one
    transaction, records the payment, updates the invoice/lease, lowers cash, and
    marks the approval approved.
    """
    if problem := _approver_problem(approved_by):
        return {"ok": False, "error": problem}
    with _connect() as conn:
        appr = conn.execute("SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)).fetchone()
        if appr is None:
            return {"ok": False, "error": f"approval {approval_id} not found"}
        if appr["status"] != "pending":
            return {"ok": False, "error": f"approval {approval_id} is already '{appr['status']}'"}
        today = _today(conn)
        name = approved_by.strip()
        if appr["kind"] == "invoice":
            result = _pay_invoice(conn, appr["ref_id"], name, today, account)
        elif appr["kind"] == "rent":
            result = _pay_rent(conn, appr["ref_id"], name, today, account)
        else:
            result = _pay_purchase(conn, appr, name, today, account)
        if result["ok"]:
            conn.execute(
                "UPDATE pending_approvals SET status = 'approved', decided_by = ?, decided_at = ?, payment_id = ? WHERE id = ?",
                (name, today, result["payment_id"], approval_id),
            )
    return {**result, "approval_id": approval_id, "approved_by": name, "paid_at": today}


@mcp.tool
def reject_approval(approval_id: int, rejected_by: str, reason: str) -> dict:
    """HUMAN-ONLY. Decline a pending approval. No money moves."""
    if problem := _approver_problem(rejected_by):
        return {"ok": False, "error": problem.replace("approved_by", "rejected_by")}
    with _connect() as conn:
        appr = conn.execute("SELECT status FROM pending_approvals WHERE id = ?", (approval_id,)).fetchone()
        if appr is None:
            return {"ok": False, "error": f"approval {approval_id} not found"}
        if appr["status"] != "pending":
            return {"ok": False, "error": f"approval {approval_id} is already '{appr['status']}'"}
        today = _today(conn)
        conn.execute(
            "UPDATE pending_approvals SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (rejected_by.strip(), today, reason.strip(), approval_id),
        )
    return {"ok": True, "approval_id": approval_id, "status": "rejected"}


# ------------------------------------------------------------------------ pricing


@mcp.tool
def get_sku_pricing_and_margin(sku: str) -> dict:
    """Look up unit cost and list price for a SKU, plus the per-unit margin at list price."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if row is None:
        return {"found": False, "sku": sku}
    margin = row["list_price"] - row["unit_cost"]
    return {
        "found": True,
        **dict(row),
        "margin_per_unit": round(margin, 2),
        "margin_pct": round(margin / row["list_price"] * 100, 1),
    }


@mcp.tool
def quote_bulk_discount(sku: str, qty: int, discount_pct: float) -> dict:
    """Price a bulk order of one SKU at a given % off list and check it against house policy.

    Returns per-unit and total price, cost, and margin, whether the margin stays at or
    above the 40% floor, and whether the discount is large enough (>15%) to need a human.
    Also returns the deepest discount that still meets the margin floor.
    """
    if qty <= 0 or not 0 <= discount_pct < 100:
        return {"ok": False, "error": "qty must be > 0 and discount_pct must be between 0 and 100"}
    with _connect() as conn:
        row = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"ok": False, "error": f"no pricing for {sku}"}
    unit_price = round(row["list_price"] * (1 - discount_pct / 100), 2)
    unit_margin = round(unit_price - row["unit_cost"], 2)
    margin_pct = round(unit_margin / unit_price * 100, 1) if unit_price else 0.0
    max_ok_pct = round((1 - row["unit_cost"] / (row["list_price"] * (1 - MIN_MARGIN_PCT / 100))) * 100, 1)
    return {
        "ok": True,
        "sku": sku,
        "qty": qty,
        "discount_pct": discount_pct,
        "list_price": row["list_price"],
        "unit_cost": row["unit_cost"],
        "unit_price": unit_price,
        "unit_margin": unit_margin,
        "margin_pct": margin_pct,
        "order_total": round(unit_price * qty, 2),
        "order_cost": round(row["unit_cost"] * qty, 2),
        "order_margin": round(unit_margin * qty, 2),
        "meets_margin_floor": margin_pct >= MIN_MARGIN_PCT,
        "margin_floor_pct": MIN_MARGIN_PCT,
        "max_discount_pct_at_floor": max(0.0, max_ok_pct),
        "needs_human_approval": discount_pct > MAX_DISCOUNT_PCT_WITHOUT_HUMAN,
    }


if __name__ == "__main__":
    mcp.run()
