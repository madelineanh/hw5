# Campus Customs MCP Server

This server gives the Campus Customs agent team (Boss, Inventory, Accounting, Facilities, Customer Service) access to the shop's database through tools. Agents never query the database directly; they call these tools instead.

**Database:** `data/campus_customs_new.db` (the working copy). The original `data/campus_customs.db` is never modified, so it can be used to reset. Set `CAMPUS_CUSTOMS_DB` to point the server at a scratch copy for testing.

## Tools

| Tool | Reads / writes | What it returns |
|---|---|---|
| `get_shop_date()` | `desk` | The shop's "today" (`date_today`) used for all due-date math |
| `list_open_tickets()` | `tickets` | Every ticket that is not resolved |
| `list_all_tickets()` | `tickets` | Every ticket with an `is_resolved` flag (for the dashboard) |
| `get_ticket(ticket_id)` | `tickets` | One ticket with its SKU, size, qty, lease and invoice links |
| `update_ticket_status(ticket_id, status, note)` | **writes** `tickets` | Sets status and appends a dated note |
| `check_inventory_stock(sku, size)` | `inventory` | Units on hand and aisle for one SKU/size, plus whether it's in stock |
| `list_sku_sizes(sku)` | `inventory` | Every size of a SKU and the total on hand |
| `list_vendors()` | `vendors` | Vendors, specialty, and lead days |
| `get_vendor_open_invoices(vendor_id)` | `vendors`, `invoices` | Unpaid invoices and whether the vendor can ship |
| `get_invoice(invoice_id)` | `invoices`, `vendors` | One invoice with days overdue |
| `get_lease_rent_due(lease_id)` | `leases`, `desk` | Rent amount, landlord, next due date, and days until due from the shop's "today" |
| `get_cash_balance(account)` | `cash_accounts` | Current checking balance |
| `list_payments()` | `payments` | Every payment already made |
| `get_sku_pricing_and_margin(sku)` | `pricing` | Unit cost, list price, and per-unit margin ($ and %) |
| `quote_bulk_discount(sku, qty, discount_pct)` | `pricing` | Discounted totals and margin, the 40% margin-floor check, the deepest safe discount, and whether a human must approve (>15%) |
| `prepare_payment(kind, ref_id, reason)` | **writes** `pending_approvals` (reads `invoices`/`leases`, `cash_accounts`) | Queues an invoice or rent payment for a human. No cash moves. Refuses duplicates and anything that would overdraw once all pending items are paid |
| `prepare_purchase(vendor_id, sku, size, qty, reason)` | **writes** `pending_approvals` (reads `vendors`, `pricing`, `inventory`, `invoices`, `cash_accounts`) | Queues a restock order at `qty × unit_cost` for a human. Flags a vendor blocked by an open invoice |
| `list_pending_approvals(status)` | `pending_approvals` | Prepared items: pending, approved, rejected, or all |
| `execute_approval(approval_id, approved_by)` | **writes** `payments`, `invoices`, `leases`, `cash_accounts`, `pending_approvals` | **Human-only** (called by the dashboard's Approve route, blocked for agents). The only tool that changes cash. Re-checks every money rule in one transaction |
| `reject_approval(approval_id, rejected_by, reason)` | **writes** `pending_approvals` | **Human-only.** Declines a prepared item; no money moves |

`pending_approvals` is a workflow table the server creates in the working database on first connection.

## Run

```bash
pip install -r mcp_server/requirements.txt
python mcp_server/server.py
```
