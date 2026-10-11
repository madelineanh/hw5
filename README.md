# Campus Customs Multi-Agent Operations (MGT 409 Homework 5)

A five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) that works the shop's open tickets. The agents are built with PydanticAI on `gpt-6-luna` via Portkey. All shop data goes through a FastMCP server over SQLite, a FastAPI backend serves the agents, and a React dashboard lets a human watch the agents and approve payments.

| Folder | What's in it |
|---|---|
| `data/` | `campus_customs.db` (original, never modified) and `campus_customs_new.db` (working copy the agents use) |
| `mcp_server/` | FastMCP server: the only way agents read or change shop data (`server.py`, tool list in `README.md`) |
| `backend/` | Agents (`boss.py`, `inventory.py`, `accounting.py`, `facilities.py`, `customer_service.py`), shared loop and guardrails (`team.py`), data types (`models.py`), prompts (`prompts/`), FastAPI routes (`main.py`), CLI runner (`run_team.py`) |
| `frontend/` | React + Vite + TypeScript service-desk dashboard |
| `output/` | `harness.md` (full documentation), `mcp_smoke.json`, `desk_tickets.html`, `design.md`, `resolved_tickets.json`, `resolved_board.html`, `audit_trail.json`, `github_url.txt` |
| `AI_prompts.md` | Log of the prompts I gave my vibe coder, per problem |

## Setup (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then put your PORTKEY_API_KEY in .env
cd frontend && npm install && cd ..
```

## Get a clean working database

The agents only touch `data/campus_customs_new.db`. To start over from the original values, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

(Or click **Reset data** in the dashboard, which calls `POST /reset` and does the same copy.)

## Start the MCP server

```bash
.venv/bin/python mcp_server/server.py
```

You usually don't need to start it yourself:
- The backend starts its own MCP server process on launch, and all agent and API data access goes through it.
- Claude Code connects to it automatically through `.mcp.json`.

## Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

API on `http://localhost:8000` (interactive docs at `/docs`). Routes are listed in `output/harness.md`.

## Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Full three-ticket run

1. **Reset the database first:** click **Reset data** (or run the `cp` command above). Checking should read **$3,400.00**.
2. Type your name in **Approving as**.
3. Select ticket 101 → **Run agent team**, and wait for ✓ Resolved. Then do the same for 102 and 103, one at a time.
4. Approve or decline each prepared payment under **Needs your approval**. Agents only prepare payments; the Approve button is the only thing that moves cash.

Every run appends to `output/audit_trail.json`. The submitted run ended at **$160.00** in checking: $3,400 − $840 (invoice #501, ticket 101) − $2,400 (rent, ticket 102). See the Cash tab in `output/desk_tickets.html`.

You can also run tickets without the dashboard: `.venv/bin/python backend/run_team.py --ticket 101` (or `--all-open`).
