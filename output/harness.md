# Campus Customs — Agent Harness Notes

- **Original DB (do not modify):** `data/campus_customs.db`
- **Working copy (agents read/write here):** `data/campus_customs_new.db`
- **Shop "today":** `desk.date_today` = **2026-08-31**

**Contents:** [Tables](#tables) · [Starting state](#starting-state-snapshot-2026-08-31) · [Tickets](#the-3-open-tickets-and-how-they-link) · [First 3 MCP tools](#first-3-mcp-tools-and-the-tickets-they-unlock-problem-3) · [Agent team](#agent-team-backend-pydanticai) · [All MCP tools](#all-mcp-tools-mcp_serverserverpy-20-tools) · [Safety](#safety-and-limits) · [API routes](#api-routes-backendmainpy-fastapi) · [Dashboard](#dashboard-frontend-react--vite--typescript) · [Run results](#run-results-problem-9)

---

## Tables

### `desk`
| Field | Type | Notes |
|---|---|---|
| date_today | TEXT | The shop's "today" |
| notes | TEXT | Free-form desk notes (currently empty) |

**Why it matters:** Every agent uses `date_today` as "now" to decide what's overdue or coming due. Never use the real clock.

### `tickets`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Ticket number |
| type | TEXT | `customer_order`, `rent_notice`, `price_override`, … |
| requester | TEXT | Who opened it (customer, landlord, student org) |
| subject | TEXT | Short title |
| sku | TEXT | → `inventory.sku` / `pricing.sku` (optional) |
| size | TEXT | → `inventory.size` (optional) |
| qty | INTEGER | Units requested (optional) |
| lease_id | INTEGER | FK → `leases.id` (optional) |
| invoice_id | INTEGER | FK → `invoices.id` (optional) |
| status | TEXT | `open`, … |
| notes | TEXT | Request details |
| created_at | TEXT | ISO timestamp |

**Why it matters:** This is the work board. The Boss reads each open ticket and routes it, and its foreign keys tell the agents which other tables to check.

### `inventory`
| Field | Type | Notes |
|---|---|---|
| sku | TEXT | Product code (PK with size) |
| name | TEXT | Product name |
| size | TEXT | S/M/L/XL or OS (one size) |
| qty | INTEGER | Units on hand |
| location | TEXT | Aisle |

**Why it matters:** Inventory checks stock by SKU and size and spots shortfalls (for example, tee S = 0 and hoodie M = 8).

### `pricing`
| Field | Type | Notes |
|---|---|---|
| sku | TEXT PK | Product code |
| unit_cost | REAL | What the shop pays |
| list_price | REAL | What the shop charges |

**Why it matters:** Accounting uses cost vs. list to check margins and decide how big a discount the shop can afford.

### `vendors`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Vendor ID |
| name | TEXT | Vendor name |
| specialty | TEXT | What they supply |
| lead_days | INTEGER | Days from order to delivery |

**Why it matters:** Inventory picks a vendor for restocking based on specialty and gives ETAs from `lead_days`. A vendor with an open unpaid invoice won't ship.

### `invoices`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Invoice number |
| vendor_id | INTEGER | FK → `vendors.id` |
| amount | REAL | Amount owed |
| due_date | TEXT | Overdue if before `date_today` |
| status | TEXT | `open` / `paid` |
| description | TEXT | What it was for |

**Why it matters:** Accounting tracks what's owed and overdue. Open invoices block vendor shipments, so Inventory must check this table too.

### `leases`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Lease ID |
| space_name | TEXT | Shop location |
| landlord | TEXT | Who gets paid |
| monthly_rent | REAL | Rent amount |
| next_due | TEXT | Next rent due date |
| notes | TEXT | |

**Why it matters:** Facilities handles rent and space issues and hands rent payments to Accounting.

### `cash_accounts`
| Field | Type | Notes |
|---|---|---|
| name | TEXT PK | Account (`checking`) |
| balance | REAL | Current cash |
| date | TEXT | As-of date |

**Why it matters:** This is the only cash source, and no revenue comes in. The pay tool must refuse any payment larger than the balance, and the balance must be reduced after every approved payment.

### `payments`
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Payment ID |
| kind | TEXT | e.g. `invoice`, `rent` |
| ref_id | INTEGER | ID of the invoice/lease paid |
| amount | REAL | Amount paid |
| account | TEXT | → `cash_accounts.name` |
| paid_at | TEXT | Date paid |
| approved_by | TEXT | Human approver (required) |

**Why it matters:** This is the record of every payment made. It starts empty, and each row must name the human approver. When a payment is made, also update `invoices.status` and/or `leases.next_due` and `cash_accounts.balance`.

### `pending_approvals` (workflow table, added by the MCP server)
| Field | Type | Notes |
|---|---|---|
| id | INTEGER PK | Approval id shown in the dashboard |
| kind | TEXT | `invoice` / `rent` / `purchase` |
| ref_id | INTEGER | Invoice id or lease id |
| vendor_id, sku, size, qty | | For restock purchases |
| amount | REAL | From the database, never from an email |
| payee | TEXT | Vendor or landlord |
| reason, ticket_id, requested_by | | Why, for which ticket, and which agent prepared it |
| status | TEXT | `pending` / `approved` / `rejected` |
| created_at, decided_by, decided_at, decision_note, payment_id | | The human decision and the resulting `payments` row |

**Why it matters:** Agents can only write here (prepare). The human Approve button turns a row into a real payment. It is not shop data: the original database doesn't have it, and the server creates it on first connection.

---

## Starting state snapshot (2026-08-31)

- **Cash:** checking = **$3,400**
- **Open invoice:** #501, Bulldog Print Co, **$840**, due 2026-08-28 → **overdue**
- **Lease:** Chapel Street shop, **$2,400** due 2026-09-02
- **Zero stock:** CC-TEE-WHITE S, CC-MUG-CREST OS

---

## The 3 open tickets and how they link

### Ticket 101: `customer_order` (Tauhid Zaman, Bulldog tee S × 1)
- `sku/size` → **inventory**: CC-TEE-WHITE S has **qty 0**, so it's out of stock.
- Restocking a tee is apparel → **vendors** #1 Bulldog Print Co (5 lead days).
- `invoice_id = 501` → **invoices**: Bulldog Print has an open $840 invoice that's **overdue** (due 8/28). **The vendor won't ship until it's paid.**
- Paying it needs **human approval** → **payments** row + invoice status `paid` + reduce **cash_accounts**.
- Customer Service drafts an update for the customer with an ETA (about 5 days after the vendor is paid).
- **Agents involved:** Boss → Inventory → Accounting → Customer Service

### Ticket 102: `rent_notice` (Elm City Properties, rent due)
- `lease_id = 1` → **leases**: $2,400 due 2026-09-02, which is 2 days out and not overdue yet.
- Payment → Accounting checks **cash_accounts** ($3,400 ≥ $2,400), then human approval → **payments** row, reduce the balance, and move `next_due` forward.
- **Agents involved:** Boss → Facilities → Accounting

### Ticket 103: `price_override` (Yale AI Club, 20 hoodies M, bulk discount)
- `sku/size` → **inventory**: CC-HOOD-NAVY M has **qty 8**, so it's **12 short**.
- → **pricing**: cost $22, list $58 ($36 margin per unit, 62%). Accounting sizes a discount that keeps a healthy margin.
- Restock comes from **vendors** #1 Bulldog Print Co, which is **also blocked by invoice 501**.
- Customer Service drafts a quote/reply; the Boss makes the final call on the discount.
- **Agents involved:** Boss → Inventory → Accounting → Customer Service

### Cross-ticket cash constraint
Paying invoice 501 ($840) and rent ($2,400) together costs **$3,240**, which leaves **$160** of the $3,400. Both can be paid, but there's almost nothing left over, so the agents must check the balance before every payment.

---

## First 3 MCP tools and the tickets they unlock (Problem 3)

The full, current list of 20 tools is under [All MCP tools](#all-mcp-tools-mcp_serverserverpy-20-tools). These three read-only tools read from `data/campus_customs_new.db` and return only what's in the database. If a row isn't there, they return `found: false` instead of guessing.

### 1. `check_inventory_stock(sku, size)`
- **Reads:** `inventory`
- **Unlocks:** Ticket **101** (Tauhid Zaman, Bulldog tee S × 1)
- **Why:** Tauhid's order depends on whether a size S CC-TEE-WHITE is on the shelf. This tool returns qty **0**, which tells the Boss the order can't ship today and sends Inventory down the restock path (Bulldog Print Co, blocked by overdue invoice 501).

### 2. `get_lease_rent_due(lease_id)`
- **Reads:** `leases` (plus `desk.date_today`)
- **Unlocks:** Ticket **102** (Elm City Properties rent notice)
- **Why:** The landlord's email only says "rent due in 2 days." This tool checks that against lease 1 and confirms **$2,400** due **2026-09-02**, **2 days** from the shop's today and not yet overdue, so Facilities can hand Accounting an exact amount and deadline for human approval.

### 3. `get_sku_pricing_and_margin(sku)`
- **Reads:** `pricing`
- **Unlocks:** Ticket **103** (Yale AI Club, 20 hoodies M, bulk discount)
- **Why:** The AI Club is asking for a discount, and Accounting can't judge one without knowing the floor. This tool shows CC-HOOD-NAVY costs **$22** and lists at **$58** (**$36 / 62%** margin per unit), so the Boss can approve a discount that stays well above cost.

---

## Agent team (`backend/`, PydanticAI)

Every agent runs on **`gpt-6-luna`** through Portkey (`PORTKEY_API_KEY` in the parent folder's `.env`), via the OpenAI Responses API. Each agent has its own prompt file in `backend/prompts/`, a typed output from `backend/models.py`, and only the MCP tools its role needs. Every agent also has a `delegate(to, task)` tool, so **any agent can hand work to any other agent**, including specialists escalating back to the Boss (full connectivity). Each specialist prompt has a teammate roster saying when to call whom. Run it from the dashboard API (`backend/main.py`, below) or the CLI: `.venv/bin/python backend/run_team.py --ticket 101` (or `--all-open`). Agents never move money; they prepare payments for a person to approve.

| Agent | File / prompt | Output type | MCP tools it can call | Typically delegates to |
|---|---|---|---|---|
| **Boss** | `backend/boss.py` / `prompts/boss.md` | `BossDecision` | `get_shop_date`, `list_open_tickets`, `get_ticket`, `update_ticket_status`, `get_cash_balance`, `list_pending_approvals` | all four specialists |
| **Inventory** | `backend/inventory.py` / `prompts/inventory.md` | `SpecialistReport` | `get_shop_date`, `get_ticket`, `check_inventory_stock`, `list_sku_sizes`, `list_vendors`, `get_vendor_open_invoices`, `get_sku_pricing_and_margin` | accounting (blocked vendor), boss (customer must choose) |
| **Accounting** | `backend/accounting.py` / `prompts/accounting.md` | `SpecialistReport` | `get_shop_date`, `get_ticket`, `get_cash_balance`, `list_payments`, `get_invoice`, `get_vendor_open_invoices`, `get_sku_pricing_and_margin`, `quote_bulk_discount`, `prepare_payment`, `prepare_purchase`, `list_pending_approvals` | facilities, inventory, boss (priority call) |
| **Facilities** | `backend/facilities.py` / `prompts/facilities.md` | `SpecialistReport` | `get_shop_date`, `get_ticket`, `get_lease_rent_due`, `list_payments` | accounting (rent payment), customer_service, boss (notice mismatch) |
| **Customer Service** | `backend/customer_service.py` / `prompts/customer_service.md` | `CustomerServiceReport` (with a `draft`) | `get_shop_date`, `get_ticket`, `check_inventory_stock`, `list_sku_sizes`, `list_vendors` | inventory, accounting (missing facts), boss (out-of-policy asks) |

**Agent loop:** `backend/team.py → run_agent()` drives each agent with `agent.iter()`: model call → tool calls (MCP or `delegate`) → tool results → model call … → typed output. A delegation starts the other agent's own loop and returns its report as the tool result; if that agent fails, the caller gets an error result and carries on (`delegation_failed`). When the Boss's run completes, the ticket is marked **resolved**: the team has done everything agents may do, and anything that still needs a person waits in the approval queue. `backend/run_team.py` starts one Boss run per ticket, one ticket at a time, so each ticket sees the cash left by the previous one.

**Audit trail:** every step is appended to `output/audit_trail.json` (never wiped): `run_started` (model, database, limits), `agent_started`, `prompt`, `model_response` (tool calls with args, text, tokens), `tool_result`, `tool_retry`, `delegation_sent` / `delegation_returned` / `delegation_refused`, `guardrail_block`, `db_write_attempt`, `agent_finished` (typed output, usage so far), `agent_error`, `harness_status_sync`, `run_finished` (stop reason). Human actions from the dashboard are appended too: `human_approved`, `human_approve_refused`, `human_rejected`, `database_reset`. Each event has `run_id`, `seq`, `ticket_id`, `agent`, the `chain` (e.g. `boss > inventory > accounting`), and `depth`.

---

## All MCP tools (`mcp_server/server.py`, 20 tools)

The agents and the API get shop facts **only** through these tools; there is no second tool layer. Tools 1–3 are from Problem 3; 4–14 were added in Problem 5; 15–20 in Problem 7, when direct payment tools were replaced by a prepare → human-approve flow.

| # | Tool | Tables | Read / write | Used by | What it does |
|---|---|---|---|---|---|
| 1 | `check_inventory_stock(sku, size)` | `inventory` | read | Inventory, Customer Service | Units on hand for one SKU/size |
| 2 | `get_lease_rent_due(lease_id)` | `leases`, `desk` | read | Facilities | Rent, landlord, next due, days until due |
| 3 | `get_sku_pricing_and_margin(sku)` | `pricing` | read | Accounting, Inventory | Cost, list price, margin $/% |
| 4 | `get_shop_date()` | `desk` | read | all agents | The shop's "today" |
| 5 | `list_open_tickets()` | `tickets` | read | Boss, CLI runner | Every non-resolved ticket |
| 6 | `get_ticket(ticket_id)` | `tickets` | read | all agents, API | One ticket with its linked ids |
| 7 | `update_ticket_status(ticket_id, status, note)` | `tickets`, `desk` | **write** | Boss | Set status, append a dated note |
| 8 | `list_sku_sizes(sku)` | `inventory` | read | Inventory, Customer Service | All sizes of a SKU (alternatives, totals) |
| 9 | `list_vendors()` | `vendors` | read | Inventory, Customer Service | Vendors, specialty, lead days |
| 10 | `get_vendor_open_invoices(vendor_id)` | `vendors`, `invoices`, `desk` | read | Inventory, Accounting | Unpaid invoices and `can_ship` (unlocks 101/103) |
| 11 | `get_invoice(invoice_id)` | `invoices`, `vendors`, `desk` | read | Accounting | One invoice, overdue days |
| 12 | `get_cash_balance(account)` | `cash_accounts` | read | Boss, Accounting, API | Current checking balance |
| 13 | `list_payments()` | `payments` | read | Accounting, Facilities | Payments already made (no double-pay) |
| 14 | `quote_bulk_discount(sku, qty, discount_pct)` | `pricing` | read | Accounting | Discounted totals, 40% margin floor, max safe discount, >15% needs human (ticket 103) |
| 15 | `list_all_tickets()` | `tickets` | read | API | All tickets with an `is_resolved` flag |
| 16 | `prepare_payment(kind, ref_id, reason)` | `invoices` or `leases`, `cash_accounts`, `pending_approvals` | **write (pending only)** | Accounting | Queues an invoice or rent payment for a human; no cash moves; refuses duplicates and anything that would overdraw after all pending items |
| 17 | `prepare_purchase(vendor_id, sku, size, qty, reason)` | `vendors`, `pricing`, `inventory`, `invoices`, `cash_accounts`, `pending_approvals` | **write (pending only)** | Accounting | Queues a restock order (`qty × unit_cost`) for a human; flags a vendor blocked by an open invoice |
| 18 | `list_pending_approvals(status)` | `pending_approvals` | read | Boss, Accounting, API | Prepared items by status |
| 19 | `execute_approval(approval_id, approved_by)` | `pending_approvals`, `payments`, `invoices`, `leases`, `cash_accounts`, `vendors` | **write (cash)** | **API only (human)** | The only tool that changes cash: re-checks every money rule, records the payment, updates invoice/lease, lowers the balance |
| 20 | `reject_approval(approval_id, rejected_by, reason)` | `pending_approvals` | write | **API only (human)** | Declines a prepared item; no money moves |

`pending_approvals` is a workflow table the server creates in the working database when it first connects. It holds the agents' prepared payments; it is not shop data, and a reset removes it until the next connection.

---

## Safety and limits

**Guardrails for real customers and real money**

- **Agents prepare, a human approves.** Agents can only queue payments and purchases (`prepare_payment` / `prepare_purchase`). Cash changes only when a person clicks Approve, which calls `POST /approvals/{id}/approve` → `execute_approval`. The harness hard-blocks `execute_approval` / `reject_approval` for every agent, and stamps `requested_by` with the real agent name. The server rejects blank or agent-role approver names.
- **Money rules live in the data layer, not just the prompt.** Preparing refuses duplicates and anything that would overdraw checking once every pending item is paid. Approving re-checks everything: never overdraw, never pay an invoice twice or rent twice in a month, never buy from a vendor with an open invoice, always pay the database amount (not an amount from an email), and write the payment, invoice/lease update, and balance change in one transaction.
- **Least privilege.** Each role sees only its own tools (table above), and the harness re-checks the allowlist on every call. Only Accounting can prepare payments, no agent can execute them, and only the top-level Boss can change ticket status (an escalated Boss call cannot).
- **No outbound messages.** Customer Service only drafts, and lists every promise in `commitments` for a human to check before sending. Drafts may not mention internal details (invoices, cash, vendors' names, agents).
- **Pricing policy.** Never below cost; a 40% margin floor; discounts above 15% need a human.
- **No invented data.** Every fact in a report must cite the MCP tool it came from. Tools return `found: false` instead of guessing.
- **Full audit trail.** Every model call, tool call, result, delegation, guardrail block, and database write is appended to `output/audit_trail.json`.
- **Safe testing.** `POST /reset` restores the working database from the untouched original (blocked while a run is in progress); `--db` / `CAMPUS_CUSTOMS_DB` points everything at a scratch copy. The API runs one ticket at a time so cash checks never race.
- What a real company would add: two-person approval above a dollar threshold, a daily payment cap, vendor/landlord bank-detail verification out of band, PII redaction in logs, and an immutable (append-only) audit store.

**Limits that keep token use in check**

- One shared usage budget per ticket across the Boss and every agent it delegates to: **40 model requests, 60 tool calls, 400,000 total tokens**. Going over stops the run and is logged as `agent_error` / `run_finished: error`.
- **Max output** of 16,000 tokens per model response (reasoning tokens count toward it; 6,000 proved too tight for a long nested call).
- **Delegation limits:** max depth 3 (Boss → A → B → C), max 8 delegations per ticket, no delegating to yourself, and no bouncing a task straight back to the agent that called you (prevents ping-pong loops). Refusals come back to the agent as a tool result and are logged.
- **Tight prompts and typed outputs:** agents are told to ask for the smallest thing that answers the question and not to re-query facts they were given. Structured outputs keep replies short.
- **2 retries** per tool/output validation error. MCP tool lists are cached so they are not re-sent each call.
- **Trust-but-don't-re-verify:** prompts tell agents that facts passed by a teammate are already tool-verified, and never to delegate just to re-confirm them. An early test without this rule spiraled into Boss › Customer Service › Accounting › Boss re-verification and was stopped by the limits.
- For reference, in testing ticket 101 used ~62k tokens, 102 ~38k, and 103 ~83k.

---

## API routes (`backend/main.py`, FastAPI)

Start from `backend/`: `uvicorn main:app --reload --port 8000` → `http://localhost:8000` (interactive docs at `/docs`). CORS allows the Vite dashboard at `http://localhost:5173` (and any other local port). All shop data goes through the MCP server.

- `GET http://localhost:8000/tickets`: returns all three tickets with their status, whether each is `open` or `resolved`, whether it is running now, and how many approvals it has waiting.
- `POST http://localhost:8000/tickets/{ticket_id}/run`: starts the agent team on one ticket in the background and returns a `run_id` (409 if another run is in progress, 404 if the ticket doesn't exist).
- `GET http://localhost:8000/tickets/{ticket_id}/summary`: returns the latest run on a ticket: the Boss's decision, and for each agent a short summary, the MCP tools it used, and who it handed off to (feeds the dashboard's agent cards).
- `GET http://localhost:8000/runs/{run_id}`: returns a run's status (`running` / `completed` / `error`) and the Boss's final decision.
- `GET http://localhost:8000/activity?limit=100&ticket_id=&run_id=`: returns recent agent activity, newest first, including runs still in progress: each event's agent, call chain, what it `said`, and which `tools` it used.
- `GET http://localhost:8000/approvals?status=pending`: lists the payments and purchases agents prepared that are waiting for a human.
- `POST http://localhost:8000/approvals/{approval_id}/approve` (body `{"approved_by": "Name"}`): a human approves a prepared payment or purchase; **the only route that changes the cash balance**.
- `POST http://localhost:8000/approvals/{approval_id}/reject` (body `{"rejected_by": "Name", "reason": "..."}`): a human declines a prepared item; no money moves.
- `GET http://localhost:8000/cash`: returns the current checking balance from `cash_accounts`, plus the total pending and the balance if everything pending is approved.
- `POST http://localhost:8000/reset`: copies `data/campus_customs.db` over `data/campus_customs_new.db` to restore the original values for a fresh test run (the audit trail is kept).

---

## Dashboard (`frontend/`, React + Vite + TypeScript)

Start the backend first (`cd backend && uvicorn main:app --reload --port 8000`), then `cd frontend && npm run dev` → `http://localhost:5173` (`?ticket=101` opens a ticket directly). Full layout and visual rationale: `output/design.md`.

- **Left: tickets.** All three with Open / Working / ✓ Resolved pills and an "awaiting your approval" chip.
- **Center: the selected ticket.** Ticket facts and **Run agent team** (`POST /tickets/{id}/run`). After the run: the Boss's decision, one card per agent that took part (summary, MCP tools, hand-offs, from `GET /tickets/{id}/summary`), and the customer draft. Below: the **live agent activity** feed (`GET /activity`, polled every 1.5 s while running), color-coded per agent and indented by delegation depth.
- **Right: money.** **Checking balance** (`GET /cash`) with pending total and balance-if-approved, and **Needs your approval** (`GET /approvals`) with Approve / Decline. Approve (`POST /approvals/{id}/approve`) is the only action that moves cash, and it requires the name typed in "Approving as".
- **Reset data** (`POST /reset`) restores the original database for a fresh run; disabled while a run is in progress.

---

## Run results (Problem 9)

The database was reset from the dashboard (`POST /reset`, logged as `database_reset`), then tickets 101, 102, and 103 were run one at a time from the dashboard. The two payments were approved by Madeline Ganey with the dashboard's Approve button. Details: `output/resolved_tickets.json`, `output/resolved_board.html` (dashboard screenshots), `output/desk_tickets.html` (Actual and Cash tabs), and the appended runs in `output/audit_trail.json`.

| Ticket | Agents | Delegations | Human approval | Checking after |
|---|---|---|---|---|
| — | | | Start, after reset | **$3,400.00** |
| 101 | Boss, Inventory, Accounting, Customer Service | Boss → Inventory, Boss → Accounting, Boss → Customer Service | #1 invoice 501, −$840.00 | $2,560.00 |
| 102 | Boss, Facilities, Accounting | Boss → Facilities, Boss → Accounting | #2 rent lease 1, −$2,400.00 | $160.00 |
| 103 | Boss, Inventory, Accounting, Customer Service | Boss → Inventory, Boss → Accounting, Boss → Customer Service ×2 | none (invoice already approved via 101; restock $264 > $160) | **$160.00** |

Final balance **$160.00** = `cash_accounts.balance` in `data/campus_customs_new.db`. All three tickets are `resolved`, and Facilities was only used where a lease was involved (102).
