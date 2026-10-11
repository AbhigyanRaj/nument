# AI usage

Most of the code in this repository (backend, solver, agent graph, frontend, evaluation and docs)
was written with an AI coding assistant, working from the team's implementation plan and design
kit, with the team reviewing and directing the work.

## How it was verified

- **Unit tests** for every core module: the cost model (including the plan's hand-computed
  example: 246.40 cost and 30 kg CO2e), calendar and capacity rules, loader, dataset checks,
  solver, plan checker, comparison and the number check. The suite runs with network disabled.
- **An independent plan validator** (`app/core/plan_check.py`) recomputes capacity, eligibility,
  delivery flags, completeness and every row's cost and carbon from the raw tables on every run.
- **The 22-case evaluation** (`eval/run_eval.py`): answer types, validator flags, trap orders,
  cross-case cost and carbon ordering, refusal and clarification, and prompt-injection cases.
- **Manual review** of the formulas against the hand-computed example, of the generator's planted
  traps (asserted in code), and of solver behaviour across scenarios.

## Changes made because the installed library versions differ from the plan

- LangChain 1.x / LangGraph 1.x: the step list uses an additive state reducer; `run_request`
  streams graph updates and values; message text is read from `.text` (content may be a list).
- OR-Tools 9.15: snake_case CP-SAT API and `num_workers`.
- pandas 3: missing dates are coerced explicitly so they stay `None` instead of `NaT`.
- Exit check 0 no longer imports Streamlit, which the React frontend replaces.
