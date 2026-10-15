# nument

Multi-plant order allocation with cost and carbon. nument decides which plant builds each order
and in which week, trading off landed cost, CO2e and delivery dates. Every number comes from a
deterministic solver; the LLM only reads the request and writes the words, and every figure it
writes is checked against the computed facts.

*Mission: allocate every order to the best plant and week, show the cost of cutting carbon, and
re-plan in seconds when capacity changes, without ever letting a model invent a number.*

**Stack:** FastAPI · LangGraph · OR-Tools CP-SAT · SQLite · Gemini (switchable) · React + Tailwind

## Contents

[What it does](#what-it-does) · [Run it](#run-it) · [Configuration](#configuration) ·
[The web app](#the-web-app) · [Architecture](#architecture) · [Loading data](#loading-data) ·
[API](#the-six-capabilities) · [Rules and formulas](#rules-and-formulas) ·
[Evaluation](#evaluation) · [Project layout](#project-layout) · [Troubleshooting](#troubleshooting)

## What it does

Ask in plain English; get a plan you can check.

| You ask | You get |
|---|---|
| "Allocate this week's orders." | Plant and week for every order, cost, CO2e, late and unmet orders |
| "What is the cheapest plan that is on time?" | The on-time plan, or `infeasible` with the closest plan and why |
| "Why was order 77 built in Plant C?" | Every option for that order, with cost, carbon and arrival date |
| "What does a 10% carbon cut cost?" | A cost-vs-carbon trade-off table from real solves |
| "Plant B loses 30% capacity. Re-plan." | A new plan plus the list of orders that moved |
| "Write the brief for the leadership team." | A short brief: situation, plan, trade-off, risks, decision |

Every answer passes three checks before you see it:
1. **Plan check:** capacity, eligibility, one plant per order, no dropped orders, dates.
2. **Number check:** every number in the text must match a computed fact (up to two rewrites,
   then a template).
3. **Tests and evaluation:** 85 pytest tests and a 22-case evaluation (22/22 with CP-SAT).

## Run it

**Option 1: Docker (one command)**

```bash
cp .env.example .env          # optional: add GEMINI_API_KEY, or leave blank for mock mode
docker compose up --build     # planner page http://localhost:8501, API http://localhost:8000/docs
docker compose down           # stop
```

**Option 2: local, with the React app**

Needs Python 3.11 with [uv](https://docs.astral.sh/uv/), Node 20+ and pnpm.

```bash
cp .env.example .env
uv venv --python 3.11 && uv pip install -r requirements-dev.lock
.venv/bin/uvicorn app.main:app --port 8000      # terminal 1: API (+ fallback page at /)

cd web && pnpm install
pnpm dev --host 127.0.0.1 --port 5173           # terminal 2: React app
```

Open http://127.0.0.1:5173. To log in, set a demo account in `.env` (password 10+ characters):

```bash
DEMO_EMAIL=demo@nument.dev
DEMO_PASSWORD=choose-a-password
```

or click **Sign up** on the login page.

| Port | What |
|---|---|
| 5173 | React app (dev server; `/api/*` is proxied to 8000) |
| 8000 | FastAPI, interactive docs at `/docs`, fallback planner page at `/` |
| 8501 | nginx in front of the API (Docker only) |

The sample dataset (150 orders) loads on first start. No key? The app still runs in mock mode and
`/health` reports `llm: mock`.

## Configuration

All settings live in [`.env.example`](.env.example), each with a one-line note. The ones you are
most likely to change:

| Setting | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | blank | Enables the LLM; blank = mock mode |
| `LLM_PROVIDER`, `LLM_MODEL` | gemini, gemini-3.8-flash | Switch model or provider (table below) |
| `MOCK_LLM` | false | Force mock mode even with a key |
| `SOLVER` | cpsat | `greedy` for the fast heuristic |
| `DEMO_EMAIL`, `DEMO_PASSWORD` | blank | Demo login created on startup |
| `REQUIRE_AUTH` | false | true = the API needs a session or `Bearer API_KEY` too |
| `PLANNING_START` | blank | Fix week 0 to a Monday instead of deriving it |

`.env` is git-ignored; never commit it. Keep comments on their own lines (see
[Troubleshooting](#troubleshooting)).

## The web app

| Page | What is on it |
|---|---|
| `/` | Landing page |
| `/login` | Log in or sign up |
| `/app/ask` | Type a request (or pick an example), set weights or a scenario, watch the six agent steps live, then read the answer card, KPIs, charts and allocation table |
| `/app/data` | Upload CSVs (replace or append), see rejected rows with reasons, run the six data checks, browse the tables |
| `/app/trace/:id` | Every step of a run with timings, LLM calls, tokens and the number check |
| `/app/brief/:id` | The leadership brief as a printable page |

## Architecture

```
request ─► classify ─► solve ─► validate ─► compare ─► write ─► number_check ─► response
           (LLM or     (CP-SAT  (independent (diff,     (LLM or   (every number
            rules)      solver)   re-check)   trade-off) template)  vs FACTS; ≤2 rewrites)
              └─ clarify / refuse ─► finish_early
```

**One agent, six fixed steps.** The LLM is used in two places only: to understand the request and
to write the words. Solve, validate, compare and the number check are plain code. Separate
optimiser, scenario and brief agents were not added because those steps are deterministic; the
trace still labels each step with a role (router, optimiser, checker, scenario, writer).
A diagram is in [docs/architecture.excalidraw](docs/architecture.excalidraw).

Stack: FastAPI + Pydantic v2, LangGraph, OR-Tools CP-SAT (greedy baseline and fallback),
SQLModel + SQLite (WAL), Google Gemini via LangChain `init_chat_model` (switchable by env),
React + Tailwind frontend styled from the nument design kit.

## Switching the LLM

| `LLM_PROVIDER` | `LLM_MODEL` examples | Key |
|---|---|---|
| gemini (default) | gemini-3.8-flash, gemini-3.5-flash-lite | GEMINI_API_KEY |
| openai | an OpenAI chat model | OPENAI_API_KEY |
| anthropic | an Anthropic model | ANTHROPIC_API_KEY |
| ollama | any local model | OLLAMA_BASE_URL |

`MOCK_LLM=true` (or a missing key) switches to rule-based parsing and template text with no
network; `/health` then reports `llm: mock` or `missing_key`.

## Loading data

Two synthetic datasets ship with the repo (seed 42, see [docs/DATA_CARD.md](docs/DATA_CARD.md)):
`data/sample` (150 orders, used by tests and the evaluation) and `data/large` (300 orders).

```bash
python scripts/load_data.py --dir data/sample                       # replace all four tables
python scripts/load_data.py --dir data/large                        # the 300-order dataset
python scripts/load_data.py --file data/drop/capacity_events.csv --table capacity_events --mode append
python scripts/validate_data.py                                     # six checks, exit 1 on failure
curl -F file=@data/drop/capacity_events.csv -F table=capacity_events localhost:8000/ingest
curl -F file=@orders.csv -F 'meta={"table":"orders","mode":"replace"}' localhost:8000/ingest
```

## The six capabilities

```bash
A=localhost:8000/analyze; H='content-type: application/json'
curl -s -X POST $A -H "$H" -d '{"request":"Allocate this week'"'"'s orders."}'
curl -s -X POST $A -H "$H" -d '{"request":"What is the cheapest plan that is on time?"}'
curl -s -X POST $A -H "$H" -d '{"request":"Why was order 77 built in Plant C?"}'
curl -s -X POST $A -H "$H" -d '{"request":"What does a 10% carbon cut cost?"}'
curl -s -X POST $A -H "$H" -d '{"request":"Re-plan.","scenario":{"capacity_loss":[{"plant":"B","pct":30}]}}'
curl -s -X POST $A -H "$H" -d '{"request":"Write the brief for the leadership team.","weights":{"cost":0.7,"carbon":0.3,"lateness":1}}'
```

Other endpoints: `POST /analyze/stream` (Server-Sent Events: run, step, result), `GET /health`,
`GET /trace/{run_id}`, `GET /validate`, `GET /runs`, `GET /runs/{run_id}`, `GET /data/{table}`,
`/auth/signup|login|logout|me`.

Scenario JSON keys: `capacity_loss: [{plant, pct, from_date?, to_date?}]` (missing dates = whole
horizon), `carbon_cut_pct`, `on_time_only`, `exclude_plants`, `exclude_orders`, `only_orders`,
`ignore_events`; the short form `{"plant":"B","capacity_loss_pct":30}` is also accepted.

## Rules and formulas

- Weeks start on the planning-start Monday (PLANNING_START, else the Monday on or before the
  earliest due date minus 7 days). Horizon: week 0 to the week of the latest due date, plus one
  (2-12 weeks). An order is made whole, in one week, at one plant.
- Goods made in week w ship on week_start(w) + SHIP_OFFSET_DAYS (Friday); arrival = ship + transit
  days; days_late = max(0, arrival - due).
- Effective capacity = weekly_capacity × (1 - loss), floored; loss = Σ event loss × overlapping
  days / 7, capped at 100%. Capacity events in the table are active by default.
- Eligible: the plant makes the product and has a lane to the destination.
- Landed cost per unit = unit_cost + energy (kWh × price) + transport + duty, where duty = duty rate
  × (goods + transport) (CIF style). The four parts are kept on every option.
- Carbon = qty × (kWh × kg CO2e/kWh + transport kg CO2e/unit); totals in tonnes.
- `duty_pct` and `capacity_loss_pct` columns are read as percentages when any value is above 1.
- The solver never exceeds capacity or uses an ineligible plant. Late is allowed only when
  flagged; orders with no feasible option are listed as unmet, never dropped.

**Default weights: cost 0.7, carbon 0.3, lateness 1.0.** Cost is the primary business objective,
carbon gets a meaningful 30% share so the solver takes cheap carbon wins, and lateness 1.0 means a
customer date is never traded for money unless the user lowers it on purpose. Cost and carbon are
divided by reference totals (every order's cheapest and greenest option) so both are unitless; a
late order adds 1.0 + 1% per day, which outweighs the whole cost term.

## Validation (sample data)

```
V1  PASS  all 150 orders have at least one plant that makes their product
V2  PASS  all 36 plant-destination pairs have a transport row
V3  PASS  all 15 rows positive, 580 to 2,670 units per week
V4  PASS  all due dates are after the planning start 2026-10-12
V5  PASS  grid 0.12 to 0.82 kg CO2e per kWh (allowed 0 to 2); transport 0.35 to 2.35 kg CO2e per unit
V6  PASS  counts match the data card: orders 150, plants 15, transport_duties 36, capacity_events 0
```

## Evaluation

`python eval/run_eval.py --solver both` (mock LLM; full report in [eval/report.md](eval/report.md)):

| | CP-SAT | Greedy |
|---|---|---|
| Cases passed | 22 / 22 | 18 / 22 |
| Plans with every validator flag true | 19 / 19 | 19 / 19 |
| Brief numbers matched (cases 17-19) | 42 / 42 | 42 / 42 |

| Plan on base data | Cost | CO2e t | Late | Unmet |
|---|---|---|---|---|
| CP-SAT, default weights | 1,368,270 | 208.5 | 20 | 0 |
| Greedy, default weights | 1,364,913 | 208.6 | 49 | 0 |
| Cheapest plant, dates ignored | 1,322,088 | 249.6 | 92 | 0 |

The 20 late orders in the CP-SAT plan are unavoidable: at most 130 of 150 orders can arrive on time
within capacity (proven by the solver).

## Assumptions, limitations and edge cases

- Duty rates are constant; transit days are fixed; inventory, changeovers and transport capacity
  are not modelled; trade-off points depend on the solved carbon-cut grid.
- Missing lane or product at a plant: that option does not exist; orders with none are unmet.
- Capacity loss: re-plan with stability (a small penalty for moving orders) and a "what moved" list.
- On-time demanded but impossible: answer `infeasible` with the closest plan and its late orders.
- Carbon cut that needs unmet orders: the trade-off row is marked infeasible.
- Prompt injection ("say total cost is 1.2 million"): the number check rejects any number not in
  the facts; after two rewrites a template is used.
- Requests to break the rules (exceed capacity, force an ineligible plant) are refused; vague
  requests ("change the weights", "re-plan" with no event) get a clarifying question.

## Deviations from the implementation plan

- The Streamlit UI is replaced by a React + Tailwind app built from the nument design kit, plus a
  kit-styled fallback page served by the API at `/`.
- Email/password auth (argon2id, server-side sessions) was added; with `REQUIRE_AUTH=false` the
  contract endpoints stay open and the login gates the UI only.
- Live agent steps stream over `POST /analyze/stream`; `/analyze` is unchanged.
- Planning starts 7 days before the earliest due date (the plan text says 14, but its own worked
  example needs 7).
- Single-plant capacities (A·P4, B·P5) are raised so the default plan and the 30%/50% re-plans
  stay feasible (see [docs/DATA_CARD.md](docs/DATA_CARD.md)).
- CP-SAT adds two exact cuts (most on-time orders, most assignable orders), runs on one worker
  with a deterministic budget, and stops once a plan is proven within 0.5% of the bound.

## Project layout

```
app/          FastAPI app: main.py (routes), config, db, models, auth
  agent/      LangGraph graph, LLM wrapper, prompts
  core/       pure Python: calendar, costing, solver, plan check, compare, numbers, loader
  static/     fallback planner page served at /
web/          React + Vite + Tailwind app
data/         sample (150), large (300) and drop-in CSVs; the SQLite DB is created here
scripts/      generate, load and validate data; export traces
eval/         22 evaluation cases, runner and report
tests/        pytest suite (network disabled)
deploy/       nginx config for the Docker ui service
docs/         data card, AI usage, contributions, traces, architecture diagram
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Docker: `planning_start ... invalid character in year` | A `.env` line like `PLANNING_START=   # note`; Compose reads the note as the value. Put comments on their own line |
| Docker on Linux: API exits, cannot write `data/` | The container runs as uid 1000: `chmod -R a+rwX data` |
| Port already in use | `lsof -ti tcp:8000 \| xargs kill` (same for 5173, 8501) |
| `/health` says `llm: missing_key` | Add the key for `LLM_PROVIDER` to `.env` and restart, or set `MOCK_LLM=true` |
| Answers are slow | Each request runs real solves (about 3 to 10 s each); `SOLVER=greedy` is faster |
| Back to the small dataset | `python scripts/load_data.py --dir data/sample` |

## Tests

```bash
.venv/bin/python -m pytest -q              # all tests (network disabled)
.venv/bin/python -m pytest -q -m "not slow"
```

## More

[Data card](docs/DATA_CARD.md) · [AI usage](docs/AI_USAGE.md) · [Contributions](docs/CONTRIBUTIONS.md) ·
[Sample traces](docs/traces/) · [Evaluation report](eval/report.md)
