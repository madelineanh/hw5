# Campus Customs Service Desk: dashboard design

`frontend/` (React + Vite + TypeScript). Start the backend from `backend/` with `uvicorn main:app --reload --port 8000`, then the dashboard from `frontend/` with `npm run dev` → `http://localhost:5173`.

## Design direction

The shop is a small, warm, Yale-town storefront, so the desk should feel like a well-run front counter, not a server console. I followed an Ina Garten-inspired brief: **warm, welcoming, polished, simple, elegant**. Every decorative choice also has to make the operator's job faster.

- **Palette:** cream background (`#faf6ee`), linen panels, off-white cards, deep **navy** for primary actions and headings, **sage** for "done", **butter** for "open", and a muted brick red used *only* for things that need a human (approvals, errors). Color carries meaning, so it is used sparingly.
- **Type:** Georgia serif for headings, ticket titles, money, and anything an agent *says* (it reads like a person talking). A clean sans-serif for labels, metadata, and controls. Monospace only for tool names and arguments, so "machine" content is instantly distinguishable from "speech".
- **Shape:** soft 14–16 px rounded cards, hairline borders, very light shadows. No heavy chrome or dark mode by default.

## Layout: three columns, left to right in the order you work

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Campus Customs · The Service Desk      Shop date · Approving as [ ] · Reset │
├──────────────┬────────────────────────────────────────────┬──────────────────┤
│ TICKETS      │ TICKET HERO  #102 Rent due  [Run agent team]│ CHECKING BALANCE │
│ #101  Open   │  item / lease / invoice / status            │   $3,400.00      │
│ #102 ✓ Resol.│────────────────────────────────────────────│ awaiting · after │
│ #103 Working │ BOSS'S DECISION + approvals it created      ├──────────────────┤
│              │ AGENT CARDS (one per agent: summary + tools)│ NEEDS YOUR       │
│              │ DRAFT REPLY (for a human to send)           │ APPROVAL  (1)    │
│              │────────────────────────────────────────────│ $2,400 to Elm…   │
│              │ AGENT ACTIVITY (live timeline)              │ [Approve][Decline│
└──────────────┴────────────────────────────────────────────┴──────────────────┘
```

1. **Left: the queue.** All three tickets as cards: number, subject, type, requester, and a status pill.
2. **Center: the work.** The selected ticket, its Run button, the outcome summary, and the live activity feed.
3. **Right: money.** Cash balance and the approval queue are always visible and sticky, so a human never has to hunt for them.

Both side rails are sticky, so the cash balance and approvals stay on screen while you scroll a long activity feed. Under 1180 px the money rail drops below the work area as two side-by-side cards; under 760 px everything stacks.

## How resolved tickets are shown

A resolved ticket looks *finished* at a glance, without reading words:

- **Ticket card:** turns sage-tinted with a sage left edge, a white-on-sage **✓ Resolved** pill, and a softened title. Open tickets have a butter edge and **Open** pill. A ticket being worked on gets a gold edge and a pulsing **Working** pill.
- **Ticket hero:** gets a sage top border and a slightly rotated **✓ Resolved** "stamp" (like a paid-invoice stamp), and the Run button changes to "Run again".
- The rail header counts "2 open · 1 resolved".
- When a run finishes, a toast says "Ticket 102 resolved by the agent team." A run is complete when the agents have done everything agents may do. Anything still needing a person (a payment) is shown separately as a pending approval, and the ticket card says "1 awaiting your approval" in red so it is never forgotten.

## How agent activity is shown

**Live timeline (Agent activity card).** While a run is going, the dashboard polls `/activity` every 1.5 s and the feed auto-scrolls, with a pulsing **Live** pill and a "typing" indicator.

- **Every agent has its own color and initial avatar:** Boss navy, Inventory sage, Accounting gold, Facilities terracotta, Customer Service rose. Each event has a left rule in that color, so you can follow one agent down the feed.
- **Delegation is shown as indentation.** Work done by a delegated agent is indented one step per level, with the call chain (e.g. *Boss › Inventory › Accounting*) next to the name. The structure of the team's conversation is visible at a glance.
- **Different kinds of steps look different:**
  - What an agent **says**: serif quote.
  - **Tool calls**: monospace chip with the arguments (e.g. `check_inventory_stock` sku=CC-TEE-WHITE, size=S).
  - **Tool results**: a one-line preview that expands to the full JSON.
  - **Hand-offs**: "→ hands off to Accounting" plus the task text.
  - **Reports**: a linen box with the agent's final summary.
  - **Guardrail blocks / failures**: a red note.
  - **Completion**: green "✓ Run complete".
- Plumbing events (raw prompts, delegation receipts) are hidden to keep the feed readable; they are still in `output/audit_trail.json`.

**After the run (summary).** Above the feed, the dashboard shows:

1. **The Boss's decision** in large serif, with each approval it created (amount, and cash left if approved).
2. **One card per agent that took part**, top-bordered in the agent's color: a short summary of what it did, the MCP tools it used as chips, and who it handed off to. Agents the Boss didn't need simply don't appear, which makes "not every specialist on every ticket" visible.
3. **The customer draft**, if any, labeled as a draft for a person to review and send.
4. Model calls, tool calls, and tokens used, for cost awareness.

## How cash and approvals are shown

- **Checking balance** is the largest number on the page (42 px serif) at the top of the right rail. Under it: amount awaiting approval, the balance *if everything pending is approved* (red if that would go negative), and the as-of shop date.
- When the balance changes after an approval, the card briefly flashes terracotta (money out), so the change is noticed.
- **Needs your approval** sits directly under the balance. When something is waiting, the card gets a gold outline and halo plus a red count badge. Each item shows the kind (Rent / Vendor invoice / Restock purchase), the amount in large serif, the payee, the agent's reason, who prepared it, and **Approve** / **Decline** buttons.
- Approving requires a name in **Approving as** (top right, remembered in the browser). That name is recorded as the human approver; agent names are rejected by the server. Approve is the only path that moves money (`POST /approvals/{id}/approve`). After approving, a toast confirms "Checking $3,400.00 → $1,000.00" and the balance, queue, and ticket badges refresh.

## Why this design

- **Follows the operator's path:** pick a ticket (left), run and watch it (center), approve money (right).
- **Puts money and approvals where they can't be missed.** They are the only things that need a human, so they get the strongest visual weight and never scroll away.
- **Makes multi-agent behavior auditable by eye.** Per-agent colors and indentation by delegation depth turn a long log into a readable conversation, and the per-agent summary cards answer "who did what" without reading the log.
- **Status is redundant on purpose:** color, pill text, a stamp, and counts all agree, so it works for color-blind users and at a glance.
- **Warm and calm, not alarming.** Red is reserved for "a human must act", so it keeps its meaning.

## Creative choices that make it feel special

I wanted the desk to feel like a place people *enjoy* sitting at, not another admin panel:

- **It reads like a conversation, not a log.** Agents "speak" in serif quotes with a colored initial avatar, as if each were a colleague at the counter. Hand-offs read "→ hands off to Accounting" with the actual task. When the Boss delegates, the reply is indented under it, so you can watch the team talk to each other.
- **A rubber "✓ Resolved" stamp.** Resolved tickets get a slightly tilted, outlined stamp, like the PAID stamp on a paper invoice, plus a calm sage tint. Finishing a ticket feels satisfying, and it's obvious from across the room.
- **Cash that reacts.** The balance is the biggest number on the screen. When you approve a payment, the card briefly blushes terracotta as money goes out, and a toast spells it out ("Checking $3,400.00 → $2,560.00"). You *feel* the money move, which is the point of human approval.
- **Approvals that ask politely but firmly.** "Needs your approval" glows with a soft gold halo and a red count badge only when something is waiting. When nothing is, it says so gently ("Agents prepare payments here; only you can approve them").
- **Warm, kitchen-table palette.** Cream, linen, butter, sage, and navy instead of default blue-on-white. Each agent has its own color: Boss navy, Inventory sage, Accounting gold, Facilities terracotta, Customer Service rose. After one run you recognize who's talking without reading names.
- **Small hospitality touches.** The approver's name is remembered between visits, a live pulsing dot and typing dots show the agents are working, the customer reply is shown as a real letter ("Warmly, The Campus Customs Team") for a human to send, and the footer of each run shows its token cost so the desk stays honest about expense.

## Other details

- **Reset data** (top right, confirmation required, disabled while a run is in progress) restores the original database for a fresh test; the audit trail is kept.
- **One run at a time:** while any ticket is running, the other Run buttons are disabled, matching the backend's one-run rule so cash checks never race.
- If the backend is down, a banner explains how to start it.
- API base URL defaults to `http://localhost:8000` (override with `VITE_API_URL`). The backend allows `http://localhost:5173` via CORS.
