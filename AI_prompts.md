# AI Prompts Log: Homework 5, Campus Customs Multi-Agent Operations

## Problem 1: Vibe coder prompts

**Prompt I typed:**
> Create AI_prompts.md at the start of the assignment and keep it updated as you work. This file is the log of what you typed to your vibe coder. there should be one for each section. every section should include: problem # and title, at least 1 prompt i typed, one follow up prompt if needed (and 1 sentence on what was lacking after the 1st).

---

## Problem 2: Study the Campus Customs database

**Prompt I typed:**
> open the data/campus_customs.db, look through all of the tables and fields. copy original file to data/campus_customs_new.db. In future problems we'll have to update that copy. look at the 3 currently open tickets so you can understand how they link to other tables. start output/harness.md. for each table, list fields and a short line on why table matters for the agents.

---

## Problem 3: Build the MCP server

**Prompt I typed:**
> lets move onto problem 3. write an MCP serve in mcp_server/ using FastMCP, which will talk to data/campus_customs_new.db. you dont have to connect or run it in this problem. all the agents in this assignment uses tools in this mcp server. write 3 tools you will for sure need for tickets in this database. make sure the names are very clear. DO NOT invent or hallucinate any data. just use the data that is provided in the database. in output/harness.md list each of your 3 mcp tools. for each include: which table it reads, which ticket it helps unlock (101,102,or103), and 1 sentence on why that specific tool is right for that specific ticket. make it cutomized, not vague like "reads inventory". tie each tool to the ticket. add short mcp_service/READSME.md file explaining what the mcp server is for, which database file it uses, and the 3 tools it has.

---

## Problem 4: Add the MCP server to vibe coder and test each tool

**Prompt I typed:**
> lets move onto problem 4. for each tool include: prompt you asked claude, tool name, tool output (must match values in data/campus_customs_new.db)

**Follow-up:**
> finish Problem 4: test each of the 3 campus-customs MCP tools by actually calling them through the MCP connection (not by running Python directly). Run these three tests: (1) Use the campus-customs MCP tool to check stock for CC-TEE-WHITE size S. (2) Use the campus-customs MCP tool to get the rent due for lease 1. (3) Use the campus-customs MCP tool to get pricing and margin for CC-HOOD-NAVY. Save the evidence in output/mcp_smoke.json. For each tool include: the prompt I asked, the tool name, and the exact tool output. Then confirm each output matches the values in data/campus_customs_new.db.

**What was lacking after the first prompt:** The MCP server couldn't be tested in the original session because Claude Code only loads `.mcp.json` when a session starts, so I had to restart and ask for real tool calls in a new session.

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt I typed:**
> build the agentic team for campus customs using pydanticAI: boss, inventory accounting, facilities, and customer service. include prompts, models, and agent loops so they can delegate work to one another with full connectivity. include all the agent prompts in backend/prompts/. make one file per agent. put data types in backend/models/py, and put the agent files in backend/. the layout can vary but make sure the 5 roles are very clear. use my portkey_api_key and only gpt-6-luna for every agent. write all of the prompts with the shop rules that each of the agents need. the prompts should cover all aspects of each agents work will earn a higher score than a shorter generic prompt. make it very specific and customized. add any relevant tools the agents need to the mcp server so they can work on open tickets. shop facts come from mcp server over data/campus_customs_new.db. do not invent a 2nd shop-tools layer that bypasses mcp. wire agents such that they append to output/audit_trail.json when they run. for all the agent-loop steps, record enough to audit later. append to this file, dont wipe after every run. in output/harness.md, list all agends and each mcp tool (including ones you all in this problem). also include which table the tool uses. include a brief safety section: guardrails a real company would have when agents interact with real customers and money, plus limits that keep token use in check. update mcp_server/README.md so the tool list matches what you have now.

**Follow-up:**
> did you follow these below instructions for problem 5? make any adjustments necessary and then update the prompt log with these ones:
>
> Build the Campus Customs Agent Team
> Create a fully connected agent team for Campus Customs with five roles: Boss, Inventory, Accounting, Facilities, and Customer Service. Use PydanticAI. Define each agent's prompt, model, and agent loop so agents can delegate work to one another.
>
> Files and models
> - Put each agent's prompt in its own file under `backend/prompts/`.
> - Define the data models and types in `backend/models.py`.
> - Put the agent implementation files under `backend/`. The specific file layout is flexible as long as all five roles are clearly represented.
> - Use the `PORTKEY_API_KEY` environment variable for API access.
> - Use `gpt-6-luna` for every agent. Do not use a different model for any role.
>
> Write a detailed prompt for each agent in your own words. Include the shop rules and the information that agent needs to do its job. Prompts that clearly explain each agent's responsibilities and limits score better than brief, generic prompts.
>
> MCP tools and shop data
> Add any tools agents need to resolve the open tickets to the MCP server. Get shop facts from the MCP server using `data/campus_customs_new.db`.
> Do not create a separate shop-tools layer that bypasses the MCP server. Agents must access shop data and tools through MCP.
>
> Audit trail
> Configure the agents to append their run activity to `output/audit_trail.json`. Record enough information at each agent-loop step to audit what happened later. Append new records; do not erase the file's existing contents on each run.
>
> Harness documentation
> In `output/harness.md`, list every agent and every MCP tool, including tools added for this problem. For each tool, identify which table it uses.
> Add a short safety section that describes:
> - Guardrails for agents interacting with real customers and real money.
> - Limits to keep token usage under control.
>
> MCP server documentation
> Update `mcp_server/README.md` so its tool list matches the tools currently available.

**What was lacking after the first prompt:** The team wasn't truly fully connected, because specialists could never hand work back to the Boss and their prompts only named one or two teammates.

---

## Problem 6: Plan the three tickets

**Prompt I typed:**
> lets move onto problem 6.
>
> Before implementing the backend or running any agents, create `output/desk_tickets.html`. The file must open by double-clicking and contain a separate tab for each open ticket: 101, 102, and 103.
> For each ticket tab:
> 1. Add an Expected section describing what you predict the team will do to resolve that ticket.
> 2. Leave space for an Actual section. Do not fill it in until after you run the agents.
> 3. In the Expected section, specify:
>    - Which agent the Boss should contact first, and why.
>    - Every agent delegation you expect, including which agent is assigned to each task. Do not write only that the Boss contacts everyone.
>    - Which MCP tools you expect each agent to use.
>
> Also add Cash and Reflection tabs for later problems. Leave them blank or add a short "coming later" note.
> Do not send every specialist to every ticket; plans that do this will receive a low score. After the agents resolve the tickets, compare their actual actions with your predictions.

---

## Problem 7: Backend routes

**Prompt I typed:**
> should we do problem 7 first? or run it? here are the problem 7 instructions:
>
> Create `backend/main.py` using FastAPI. The React dashboard needs a backend at `http://localhost:8000` with routes that support these actions:
> 1. Return all three tickets and indicate whether each ticket is open or resolved.
> 2. Accept a ticket ID and run the agent team on that ticket.
> 3. Return recent agent activity, including what each agent said and which tools it used, so the dashboard can refresh.
> 4. Approve a payment or purchase after a human clicks Approve. Agents may prepare a payment, but only this route should make the change to the cash balance.
> 5. Return the current checking balance from the `cash_accounts` table.
> 6. Reset the database to its original values so a fresh run can be tested.
>
> Document each route in `output/harness.md` using one line per route. For each line, include the URL and what the route does.
> To start the server, run this command from the `backend/` directory:
>
> uvicorn main:app --reload --port 8000.
>
> The server should then be available at http://localhost:8000 for the frontend dashboard to call.

---

## Problem 8: Agent dashboard

**Prompt I typed:**
> should we do problem 8 now? the instructions are below? or should i make a decision about the questions you asked.
>
> Create a React dashboard in `frontend/` using Vite and TypeScript. The dashboard must call the backend routes from Problem 7 at `http://localhost:8000`.
> Dashboard behavior
> The dashboard must:
> 1. Display all three tickets.
> 2. Let a user select one ticket and start the agent team on it.
> 3. Show each agent's activity while the ticket is being processed, including what each agent says or does.
> 4. Mark the ticket as resolved when the run completes.
> 5. Show a brief summary of what each agent did for the ticket.
> 6. Let a human approve a payment or purchase when approval is requested.
> 7. Display the checking balance and update it after an approved payment.
>
> Backend access
> Configure the backend to allow requests from the Vite frontend origin, usually `http://localhost:5173`. This allows the dashboard to call the backend routes from the browser.
> Visual design and documentation
> Give the dashboard a polished, intentional design suitable for a real service desk. Use a clear layout that makes it easy to follow each agent's activity and distinguish resolved tickets. Make the cash balance and any approval request easy to find.
> In `output/design.md`, describe the dashboard's layout and visual choices. Explain how agent activity, resolved tickets, and cash are displayed, and why you chose that design.
> Run the dashboard
> From the `frontend/` directory, run:
>
> npm run dev
>
> This starts the React dashboard in the browser so the user can select tickets and watch the agents.

---

## Problem 9: Resolve the tickets

**Prompt I typed:**
> should i do what you just told me to do? or move onto problem 9? the instructions are below. tell me what youd suggest
>
> 1. Reset the working database
> Before running the agents on all three tickets, reset `data/campus_customs_new.db` to its original state. Record the starting checking balance after the reset.
> 2. Resolve the tickets
> Use the dashboard to run tickets 101, 102, and 103. Continue until all three tickets are resolved.
> 3. Record actual agent activity
> Open `output/desk_tickets.html`, created in Problem 6. On each ticket's tab, complete the Actual section based on the runs. Record:
> - Which agents worked on the ticket
> - What work the agents delegated to one another
> - Which tools the agents used
>
> Keep the Expected section unchanged so the predictions can be compared with what actually happened.
> 4. Reconcile the cash balance
> On the Cash tab of `output/desk_tickets.html`, record:
> - The checking balance after the database reset
> - For each ticket, how the balance changed when it was resolved, including the payment or purchase and dollar amount
> - The final checking balance
>
> Verify that the final balance matches the `cash_accounts` table in the working database. Incorrect cash calculations lose points even if all tickets are marked resolved.
> 5. Save the run results
> Create `output/resolved_tickets.json`. For each ticket, include its ID, final status, a short outcome summary, each agent's contribution, and any human approvals.
> Create `output/resolved_board.html` as a page that opens by double-clicking. Include a screenshot of the React dashboard for each resolved ticket: 101, 102, and 103.
> Append the actual runs to `output/audit_trail.json`. Preserve existing records; do not replace the file.
> 6. Finish the harness documentation
> Complete `output/harness.md`. Ensure it documents the database tables, MCP tools, all five agents, API routes, dashboard, and safety rules.

**Follow-up:**
> do as much as you can now

**What was lacking after the first prompt:** It wasn't clear who should click through the dashboard, so I had Claude reset the database and run all three tickets, leaving only the two payment approvals for me to click as the human approver.

---

## Problem 10: Reflection

**Prompt I typed:**
> lets move onto problem 10. here are instructions:
>
> Open `output/desk_tickets.html` and fill in the Reflection tab. Write detailed answers in your own voice to each question:
> 1. How well did the agents perform on each of the three tickets? Explain your assessment using specific examples.
> 2. For each ticket, compare what the agents actually did with the Expected plan you wrote before running them.
> 3. Which parts of the work could have been handled more simply by one agent using tools? Explain why.
> 4. Describe three new problems Campus Customs could face that this agent team could solve with the tools already built.
> 5. Describe three new problems this team could not solve with its current tools. For each, explain what agents or tools would need to be added.
>
> Support every answer with details from this Campus Customs app and the three tickets you ran. Use the ticket tabs and the Cash tab as evidence. Keep the reflection specific to your actual runs; generic answers without Campus Customs details will score poorly.

---

## Problem 11: Submit to GitHub

**Prompt I typed:**
> lets do problem 11.

**Follow-up:**
> are you following the problem 11 instructions exactly?

**What was lacking after the first prompt:** My first prompt didn't check the repo against Problem 11's exact requirements, so I asked Claude to confirm the expected file layout, both database files, the README contents, and that my real `.env` wasn't pushed.
