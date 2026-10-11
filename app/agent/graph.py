"""One agent, six fixed steps. The LLM is used in two places only: to understand the request
and to write the words. Solve, validate, compare and the number check are plain code."""

from __future__ import annotations

import json
import operator
import re
import time
import traceback
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.llm import call_structured, call_text, llm_status
from app.agent.prompts import CLASSIFY_SYSTEM, WRITE_SYSTEM, ParsedIntent, write_user_prompt
from app.config import get_settings
from app.core.numbers import build_facts, check_numbers, template_brief, template_summary
from app.core.scenario import normalise_scenario
from app.core.solver import DEFAULT_WEIGHTS, solve_allocation
from app.db import get_session, load_tables
from app.models import AgentRun, PlanAllocation, PlanRun

KNOWN_PLANTS = {"A", "B", "C"}
DEFAULT_CUTS = (0, 5, 10, 15, 20)


class AgentState(TypedDict, total=False):
    run_id: str
    request: str
    weights_in: dict | None
    scenario_in: dict | None
    intent: dict
    weights: dict
    scenario: dict
    base_plan: dict | None
    plan: dict | None
    baseline: dict | None
    check: dict
    comparison: dict | None
    tradeoff: list | None
    explanation: dict | None
    recommendations: list
    facts: dict
    draft: str
    summary: str
    number_check: dict
    rewrites: int
    answer_type: str
    steps: Annotated[list, operator.add]
    llm_calls: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    assumptions: list
    limitations: list


def _step(state, agent, tool, t0, inp=None, out=None, **extra) -> list:
    n = len(state.get("steps") or []) + 1
    entry = {"step": n, "agent": agent, "tool": tool, "input": inp or {}, "output": out or {}}
    entry["ms"] = int((time.time() - t0) * 1000)
    entry.update(extra)
    return [entry]


# --- Node 1: classify --------------------------------------------------------------------------

REFUSE_RE = re.compile(
    r"ignore (the )?(capacity|rules|limits)|exceed (the )?capacity|over capacity|make up|invent|"
    r"ignore capacity|fake|change the numbers",
    re.I,
)


def _order_id(text: str) -> str | None:
    m = re.search(r"\bO-?(\d{1,4})\b", text, re.I) or re.search(
        r"\border\s*#?\s*(\d{1,4})\b", text, re.I
    )
    return f"O-{int(m.group(1)):03d}" if m else None


def _weights_from_text(text: str) -> dict | None:
    found = {}
    for key in ("cost", "carbon", "lateness"):
        m = re.search(rf"{key}\s*(?:weight)?\s*[:=]?\s*(\d*\.?\d+)\s*(%)?", text, re.I)
        if m:
            value = float(m.group(1))
            found[key] = value / 100 if (m.group(2) or value > 1) else value
    return found or None


def rule_classify(request: str, scenario_in: dict | None = None) -> dict:
    text = request.strip()
    low = text.lower()
    intent: dict = {"intent": "clarify", "capacity_loss": []}
    weights = _weights_from_text(text) if "weight" in low else None
    if REFUSE_RE.search(low):
        return {
            "intent": "refuse",
            "refuse_reason": "That would break the planning rules (capacity, eligibility or the numbers).",
            "capacity_loss": [],
        }
    if re.search(r"\bwhy\b", low) and ("order" in low or re.search(r"\bO-?\d+", text)):
        oid = _order_id(text)
        return {
            "intent": "explain_order" if oid else "clarify",
            "order_id": oid,
            "capacity_loss": [],
            "clarify_question": None if oid else "Which order should I explain?",
        }
    if re.search(r"brief|leadership|management summary", low):
        return {"intent": "brief", "capacity_loss": []}
    if "weight" in low and not weights:
        return {
            "intent": "clarify",
            "clarify_question": "What weights should I use for cost, carbon and lateness (for example cost 0.7, carbon 0.3)?",
            "capacity_loss": [],
        }
    m = re.search(r"(\d+(?:\.\d+)?)\s*%[^.]*carbon|carbon[^.]*?(\d+(?:\.\d+)?)\s*%", low)
    if m or "carbon cut" in low:
        pct = float(m.group(1) or m.group(2)) if m else None
        return {
            "intent": "tradeoff",
            "carbon_cut_pct": pct if pct is not None else 10.0,
            "capacity_loss": [],
        }
    loss = re.search(r"plant\s*([a-z])\b.*?(loses?|down|lost|drops?).*?(\d+(?:\.\d+)?)\s*%", low)
    if loss:
        intent = {
            "intent": "replan",
            "capacity_loss": [{"plant": loss.group(1).upper(), "pct": float(loss.group(3))}],
        }
    elif re.search(r"re-?plan", low):
        intent = {"intent": "replan", "capacity_loss": []}
    elif re.search(r"cheapest.*on.?time|on.?time.*cheapest", low):
        intent = {"intent": "cheapest_on_time", "capacity_loss": []}
    elif re.search(r"allocate|\bplan\b|assign|schedule", low) or weights:
        intent = {"intent": "allocate", "capacity_loss": []}
    if weights:
        intent["weights"] = weights
    if intent["intent"] == "clarify":
        intent["clarify_question"] = (
            "I can allocate orders, price a carbon cut, re-plan after a capacity loss, explain an order or write a brief. What would you like?"
        )
    return intent


def _valid_weights(w: dict | None) -> dict | None:
    if not w:
        return None
    out = dict(DEFAULT_WEIGHTS)
    for key in ("cost", "carbon", "lateness"):
        if w.get(key) is not None:
            v = float(w[key])
            v = v / 100 if v > 1 else v
            if not 0 <= v <= 1:
                return {"invalid": True}
            out[key] = v
    if out["cost"] + out["carbon"] <= 0:
        return {"invalid": True}
    return out


def classify(state: AgentState) -> dict:
    t0 = time.time()
    request = state["request"]
    llm_calls = tokens = 0
    fallback = None
    if llm_status() == "configured":
        parsed, tokens = call_structured(ParsedIntent, CLASSIFY_SYSTEM, request)
        llm_calls = 1
        if parsed is None:
            intent, fallback = rule_classify(request, state.get("scenario_in")), "rules"
        else:
            intent = parsed.model_dump()
            if intent.get("weights"):
                intent["weights"] = {
                    k: v for k, v in intent["weights"].items() if v is not None
                } or None
    else:
        intent = rule_classify(request, state.get("scenario_in"))
    # A deterministic refusal or explain id from the rules always wins over the LLM.
    rules = rule_classify(request, state.get("scenario_in"))
    if rules["intent"] == "refuse":
        intent = rules
    if intent.get("order_id"):
        intent["order_id"] = _order_id(intent["order_id"]) or intent["order_id"]

    scenario_in = normalise_scenario(state.get("scenario_in")) if state.get("scenario_in") else None
    tables = load_tables()
    clarify = None

    if scenario_in and scenario_in["capacity_loss"] and intent["intent"] == "allocate":
        intent["intent"] = "replan"
    weights = (
        _valid_weights(state.get("weights_in"))
        or _valid_weights(intent.get("weights"))
        or dict(DEFAULT_WEIGHTS)
    )
    if weights.get("invalid"):
        clarify = (
            "Weights must be between 0 and 1 (or 0-100%), and cost plus carbon must be above zero."
        )
        weights = dict(DEFAULT_WEIGHTS)

    losses = list(intent.get("capacity_loss") or []) + (
        scenario_in["capacity_loss"] if scenario_in else []
    )
    if intent["intent"] == "replan" and not losses and tables["capacity_events"].empty:
        clarify = "Which plant lost capacity, and by what percentage?"
    for loss in losses:
        plant = str(loss["plant"]).upper().removeprefix("PLANT").strip()
        if plant not in set(tables["plants"]["plant"]) | KNOWN_PLANTS:
            clarify = f"Plant {plant} is not in the loaded data."
        if not 0 < float(loss["pct"]) <= 100:
            clarify = "A capacity loss must be between 0 and 100%."
    if intent["intent"] == "explain_order":
        oid = intent.get("order_id")
        if not oid or oid not in set(tables["orders"]["order_id"]):
            clarify = (
                f"Order {oid} is not in the loaded data."
                if oid
                else "Which order should I explain?"
            )

    # Eligibility refusal by code: forcing an order onto a plant that cannot make it.
    force = re.search(
        r"(force|move|assign|put)\b.*?\bO-?(\d+).*?(to|in|at)\s+plant\s+([a-z])", request, re.I
    )
    if force:
        oid, plant = f"O-{int(force.group(2)):03d}", force.group(4).upper()
        orders = tables["orders"].set_index("order_id")
        if oid in orders.index:
            product = orders.loc[oid, "product"]
            makers = set(tables["plants"].loc[tables["plants"]["product"] == product, "plant"])
            if plant not in makers:
                intent = {
                    "intent": "refuse",
                    "capacity_loss": [],
                    "refuse_reason": f"Plant {plant} cannot make {product}, which order {oid} needs; only {', '.join(sorted(makers))} can.",
                }
            else:
                clarify = f"Plant {plant} can make {oid}, but pinning single orders is not supported; I can re-plan with a scenario instead."

    if clarify and intent["intent"] != "refuse":
        intent["intent"] = "clarify"
        intent["clarify_question"] = clarify
    scenario = scenario_in or normalise_scenario(None)
    if intent.get("capacity_loss"):
        scenario["capacity_loss"] = (
            scenario["capacity_loss"]
            + normalise_scenario({"capacity_loss": intent["capacity_loss"]})["capacity_loss"]
        )
    if intent["intent"] == "cheapest_on_time":
        weights = {"cost": 1.0, "carbon": 0.0, "lateness": 1.0}
    steps = _step(
        state,
        "router",
        "classify_request",
        t0,
        {"request": request[:200]},
        {"intent": intent["intent"], "weights": weights},
        **({"fallback": fallback} if fallback else {}),
    )
    return {
        "intent": intent,
        "weights": weights,
        "scenario": scenario,
        "steps": steps,
        "llm_calls": llm_calls,
        "tokens": tokens,
        "rewrites": 0,
    }


def route_after_classify(state: AgentState) -> str:
    return "finish_early" if state["intent"]["intent"] in ("clarify", "refuse") else "solve"


# --- Node 2: solve ---------------------------------------------------------------------------


def solve(state: AgentState) -> dict:
    from app.core.compare import baseline_cheapest_plan, explain_order, tradeoff_table

    t0 = time.time()
    settings = get_settings()
    tables = load_tables()
    if tables["orders"].empty or tables["plants"].empty or tables["transport_duties"].empty:
        return {
            "answer_type": "clarification_needed",
            "summary": "No data loaded. Use POST /ingest or the loader first.",
            "steps": _step(state, "optimiser", "solve_allocation", t0, out={"error": "no data"}),
        }
    intent = state["intent"]["intent"]
    weights, scenario = state["weights"], dict(state["scenario"])
    out: dict = {"base_plan": None, "tradeoff": None, "explanation": None, "baseline": None}
    if intent == "cheapest_on_time":
        scenario["on_time_only"] = True
        plan = solve_allocation(tables, settings, weights, scenario)
        if plan["unmet"]:  # closest plan: allow lateness, report what would be late
            out["base_plan"] = plan
            closest = dict(scenario, on_time_only=False)
            plan = solve_allocation(tables, settings, weights, closest)
    elif intent == "replan":
        from_db = not state["intent"].get("capacity_loss") and not scenario["capacity_loss"]
        base_scenario = dict(
            scenario, capacity_loss=[], ignore_events=True if from_db else scenario["ignore_events"]
        )
        base = solve_allocation(tables, settings, weights, base_scenario)
        base_assignment = {r["order_id"]: r["plant"] for r in base["rows"]}
        plan = solve_allocation(tables, settings, weights, scenario, base_assignment)
        out["base_plan"] = base
    else:
        plan = solve_allocation(tables, settings, weights, scenario)
    if intent in ("allocate", "tradeoff", "brief"):
        cuts = list(DEFAULT_CUTS)
        cut = state["intent"].get("carbon_cut_pct")
        if cut is not None and cut not in cuts:
            cuts = sorted(set(cuts) | {cut})
        out["tradeoff"] = tradeoff_table(tables, settings, weights, scenario, tuple(cuts))
    if intent == "explain_order":
        out["explanation"] = explain_order(
            state["intent"]["order_id"], plan, tables, settings, scenario
        )
    if intent == "brief":
        out["baseline"] = baseline_cheapest_plan(tables, settings, scenario)
    out["plan"] = plan
    k = plan["kpis"]
    out["steps"] = _step(
        state,
        "optimiser",
        "solve_allocation",
        t0,
        {"intent": intent, "weights": weights},
        {
            "status": plan["status"],
            "total_cost": k["total_cost"],
            "total_carbon_t": k["total_carbon_t"],
            "late_orders": k["late_orders"],
            "unmet_orders": k["unmet_orders"],
        },
    )
    return out


def route_after_solve(state: AgentState) -> str:
    return "finish_early" if state.get("answer_type") == "clarification_needed" else "validate"


# --- Node 3: validate ------------------------------------------------------------------------


def validate(state: AgentState) -> dict:
    from app.core.plan_check import validate_plan

    t0 = time.time()
    settings, tables = get_settings(), load_tables()
    plan, scenario = state["plan"], state["scenario"]
    check = validate_plan(plan, tables, settings, scenario)
    if not (check["capacity_ok"] and check["eligibility_ok"]) and plan["solver"] == "cpsat":
        plan = solve_allocation(tables, settings, state["weights"], scenario, solver="greedy")
        check = validate_plan(plan, tables, settings, scenario)
    intent = state["intent"]["intent"]
    cut = state["intent"].get("carbon_cut_pct")
    cut_row = next((r for r in state.get("tradeoff") or [] if r["carbon_cut_pct"] == cut), None)
    if (
        plan["unmet"]
        or not (check["capacity_ok"] and check["eligibility_ok"])
        or intent == "cheapest_on_time"
        and state.get("base_plan")
        and state["base_plan"]["unmet"]
        or intent == "tradeoff"
        and cut_row is not None
        and not cut_row["feasible"]
    ):
        answer = "infeasible"
    else:
        answer = {
            "allocate": "allocation",
            "cheapest_on_time": "allocation",
            "explain_order": "allocation",
            "tradeoff": "scenario",
            "replan": "scenario",
            "brief": "brief",
        }[intent]
    flags = {k: v for k, v in check.items() if k.endswith("_ok")}
    return {
        "plan": plan,
        "check": check,
        "answer_type": answer,
        "steps": _step(state, "checker", "validate_plan", t0, out={**flags, "answer_type": answer}),
    }


# --- Node 4: compare -------------------------------------------------------------------------


def compare(state: AgentState) -> dict:
    from app.core.compare import compare_plans, recommendations

    t0 = time.time()
    settings = get_settings()
    comparison = None
    if state.get("base_plan") and state["intent"]["intent"] == "replan":
        comparison = compare_plans(state["base_plan"], state["plan"])
    merged = {**state, "comparison": comparison}
    facts = build_facts(merged)
    recs = recommendations(state["plan"], comparison, state.get("tradeoff"), state.get("check"))
    w = state["weights"]
    plan = state["plan"]
    events = plan.get("events") or []
    assumptions = [
        f"Weights: cost {w['cost']:g}, carbon {w['carbon']:g}, lateness {w['lateness']:g}. Cost is the main business objective, carbon gets a meaningful share, and a lateness weight of 1 means a customer date is never traded for money.",
        "Duty is charged on goods value plus freight (CIF style).",
        f"Energy price per kWh comes from plants.csv when given, otherwise {settings.default_energy_price_per_kwh:g}.",
        "Each order is made whole, in one week, at one plant (no splitting).",
        f"Goods made in a week ship on day {settings.ship_offset_days} of that week (Friday); arrival = ship date + transit days.",
        "duty_pct and capacity_loss_pct are read as percentages when any value in the column is above 1, otherwise as fractions.",
        "Active capacity events: "
        + (
            "; ".join(
                f"Plant {e['plant']} -{e['loss_pct']:g}% {e['from_date']} to {e['to_date']}"
                for e in events
            )
            if events
            else "none"
        )
        + ".",
    ]
    limitations = [
        "Duty rates are constant for the period.",
        "One production week per order; transit days are fixed.",
        "Inventory, changeovers and transport capacity are not modelled.",
        "Trade-off points depend on the carbon-cut grid that was solved.",
        f"CP-SAT stops once a plan is proven within 0.5% of the best bound (this plan: {plan.get('gap_pct')}%).",
    ]
    out = {
        "comparison": comparison,
        "facts": facts,
        "recommendations": recs,
        "assumptions": assumptions,
        "limitations": limitations,
    }
    summary_out = {"facts": len(facts)}
    if comparison:
        summary_out.update(
            moved_count=comparison["moved_count"], extra_cost=comparison["extra_cost"]
        )
    out["steps"] = _step(state, "scenario", "compare_plans", t0, out=summary_out)
    return out


# --- Nodes 5 and 6: write and check numbers --------------------------------------------------


def write(state: AgentState) -> dict:
    t0 = time.time()
    mode = "brief" if state["answer_type"] == "brief" else "summary"
    facts = state["facts"]
    note = ""
    if state.get("rewrites"):
        note = (
            "Your previous text used numbers that are not in FACTS: "
            f"{state['number_check']['unmatched']}. Rewrite using only FACTS numbers."
        )
    draft, tokens, calls = None, 0, 0
    if llm_status() == "configured":
        draft, tokens = call_text(
            WRITE_SYSTEM, write_user_prompt(mode, state["request"], facts, note)
        )
        calls = 1
    fallback = None
    if not draft:
        draft = (
            template_brief(facts)
            if mode == "brief"
            else template_summary(state["answer_type"], facts)
        )
        fallback = "template"
    # The streamed step never carries the draft: unchecked text must not reach the screen.
    return {
        "draft": draft,
        "llm_calls": calls,
        "tokens": tokens,
        "steps": _step(
            state,
            "writer",
            f"write_{mode}",
            t0,
            out={"attempt": (state.get("rewrites") or 0) + 1, "tokens": tokens},
            **({"fallback": fallback} if fallback else {}),
        ),
    }


def number_check(state: AgentState) -> dict:
    t0 = time.time()
    nc = check_numbers(state["draft"], state["facts"], state["request"])
    out: dict = {"number_check": nc}
    if nc["ok"]:
        out["summary"] = state["draft"]
    elif (state.get("rewrites") or 0) < 2:
        out["rewrites"] = (state.get("rewrites") or 0) + 1
    else:
        mode_brief = state["answer_type"] == "brief"
        out["summary"] = (
            template_brief(state["facts"])
            if mode_brief
            else template_summary(state["answer_type"], state["facts"])
        )
        out["number_check"] = check_numbers(out["summary"], state["facts"], state["request"])
    out["steps"] = _step(
        state,
        "checker",
        "check_numbers",
        t0,
        out={"checked": nc["checked"], "matched": nc["matched"], "unmatched": nc["unmatched"][:10]},
        **({"fallback": "template"} if "summary" in out and not nc["ok"] else {}),
    )
    return out


def route_after_check(state: AgentState) -> str:
    return "end" if state.get("summary") else "write"


# --- finish_early ----------------------------------------------------------------------------


def finish_early(state: AgentState) -> dict:
    t0 = time.time()
    intent = state.get("intent") or {}
    if state.get("answer_type") == "clarification_needed":
        return {
            "steps": _step(
                state, "router", "finish_early", t0, out={"answer_type": "clarification_needed"}
            )
        }
    if intent.get("intent") == "refuse":
        answer = "refused"
        summary = (intent.get("refuse_reason") or "I can't do that.") + (
            " I can allocate orders within capacity, price a carbon cut, re-plan after a capacity loss, explain an order or write a brief."
        )
    else:
        answer = "clarification_needed"
        summary = intent.get("clarify_question") or "Could you say a bit more about what you need?"
    return {
        "answer_type": answer,
        "summary": summary,
        "steps": _step(state, "router", "finish_early", t0, out={"answer_type": answer}),
    }


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [
        ("classify", classify),
        ("solve", solve),
        ("validate", validate),
        ("compare", compare),
        ("write", write),
        ("number_check", number_check),
        ("finish_early", finish_early),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify", route_after_classify, {"solve": "solve", "finish_early": "finish_early"}
    )
    g.add_conditional_edges(
        "solve", route_after_solve, {"validate": "validate", "finish_early": "finish_early"}
    )
    g.add_edge("validate", "compare")
    g.add_edge("compare", "write")
    g.add_edge("write", "number_check")
    g.add_conditional_edges("number_check", route_after_check, {"write": "write", "end": END})
    g.add_edge("finish_early", END)
    return g.compile()


_graph = None


def graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


# --- run_request -----------------------------------------------------------------------------

STEP_NAMES = {
    "classify": "router",
    "solve": "optimiser",
    "validate": "checker",
    "compare": "scenario",
    "write": "writer",
    "number_check": "checker",
    "finish_early": "router",
}


def run_request(
    request: str, weights: dict | None = None, scenario: dict | None = None, on_event=None
) -> dict:
    run_id = "al-" + uuid.uuid4().hex[:6]
    t0 = time.time()
    if on_event:
        on_event("run", {"run_id": run_id})
    state: dict = {
        "run_id": run_id,
        "request": request,
        "weights_in": weights,
        "scenario_in": scenario,
        "steps": [],
        "llm_calls": 0,
        "tokens": 0,
    }
    try:
        for mode, chunk in graph().stream(
            state, {"recursion_limit": 20}, stream_mode=["updates", "values"]
        ):
            if mode == "values":
                state = chunk
            elif on_event:
                for _node, update in chunk.items():
                    for step in (update or {}).get("steps", []):
                        on_event("step", step)
    except Exception as exc:  # never a 500 for a planning error
        traceback.print_exc()
        state["answer_type"] = "clarification_needed"
        state["summary"] = f"Internal error while planning: {type(exc).__name__}"
    response = build_response(state, run_id, int((time.time() - t0) * 1000))
    persist(state, response)
    return response


def build_response(state: dict, run_id: str, latency_ms: int) -> dict:
    plan = state.get("plan") or {}
    answer = state.get("answer_type") or "clarification_needed"
    early = answer in ("clarification_needed", "refused") and not plan
    rows = plan.get("rows", []) if not early else []
    kpis = plan.get("kpis") or {
        "total_cost": 0.0,
        "total_carbon_t": 0.0,
        "late_orders": 0,
        "plant_utilisation": {},
        "unmet_orders": 0,
        "orders_total": 0,
        "plant_share": {},
    }
    check = state.get("check") or {}
    nc = state.get("number_check") or {"checked": 0, "matched": 0, "matches": []}
    return {
        "run_id": run_id,
        "answer_type": answer,
        "summary": state.get("summary", ""),
        "allocation": rows,
        "kpis": kpis,
        "tradeoff": state.get("tradeoff") or [],
        "weights_used": state.get("weights") or dict(DEFAULT_WEIGHTS),
        "validator": {
            k: bool(check.get(k, False))
            for k in ("capacity_ok", "eligibility_ok", "delivery_ok", "complete_ok", "numbers_ok")
        },
        "assumptions": state.get("assumptions") or [],
        "limitations": state.get("limitations") or [],
        "recommendations": state.get("recommendations") or [],
        "comparison": state.get("comparison"),
        "unmet_orders": plan.get("unmet", []),
        "late_orders_list": [r["order_id"] for r in rows if r["days_late"] > 0],
        "explanation": state.get("explanation"),
        "brief": state.get("summary") if answer == "brief" else None,
        "capacity_grid": plan.get("capacity", []),
        "meta": {
            "solver": plan.get("solver"),
            "solver_status": plan.get("status"),
            "solve_ms": plan.get("solve_ms"),
            "gap_pct": plan.get("gap_pct"),
            "latency_ms": latency_ms,
            "llm_calls": state.get("llm_calls", 0),
            "tokens": state.get("tokens", 0),
            "llm": llm_status(),
            "number_check": {
                "checked": nc.get("checked", 0),
                "matched": nc.get("matched", 0),
                "matches": nc.get("matches", []),
            },
            "steps": state.get("steps", []),
            "planning_start": plan.get("start"),
            "events": plan.get("events", []),
        },
    }


def persist(state: dict, response: dict) -> None:
    try:
        with get_session() as session:
            plan = state.get("plan")
            if plan:
                plan_id = response["run_id"] + "-main"
                k, check = plan["kpis"], state.get("check") or {}
                session.add(
                    PlanRun(
                        plan_id=plan_id,
                        run_id=response["run_id"],
                        kind="scenario" if state.get("base_plan") else "base",
                        weights_json=json.dumps(state.get("weights")),
                        scenario_json=json.dumps(plan.get("scenario")),
                        solver=plan["solver"],
                        solver_status=plan["status"],
                        total_cost=k["total_cost"],
                        total_carbon_kg=round(k["total_carbon_t"] * 1000, 3),
                        late_orders=k["late_orders"],
                        unmet_orders=k["unmet_orders"],
                        capacity_ok=bool(check.get("capacity_ok")),
                        eligibility_ok=bool(check.get("eligibility_ok")),
                        delivery_ok=bool(check.get("delivery_ok")),
                    )
                )
                for r in plan["rows"]:
                    session.add(
                        PlanAllocation(
                            plan_id=plan_id,
                            order_id=r["order_id"],
                            plant=r["plant"],
                            week=r["week"],
                            cost=r["cost"],
                            carbon_kg=r["carbon_kg"],
                            arrival=__import__("datetime").date.fromisoformat(r["arrival"]),
                            on_time=r["on_time"],
                            days_late=r["days_late"],
                            moved=r.get("moved", False),
                            base_plant=r.get("base_plant"),
                        )
                    )
            nc = response["meta"]["number_check"]
            session.add(
                AgentRun(
                    run_id=response["run_id"],
                    request=state.get("request", ""),
                    answer_type=response["answer_type"],
                    steps_json=json.dumps(state.get("steps", []), default=str),
                    response_json=json.dumps(response, default=str),
                    llm_calls=state.get("llm_calls", 0),
                    tokens=state.get("tokens", 0),
                    latency_ms=response["meta"]["latency_ms"],
                    numbers_checked=nc["checked"],
                    numbers_matched=nc["matched"],
                )
            )
            session.commit()
    except Exception:
        traceback.print_exc()
