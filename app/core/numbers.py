"""Facts for the writer, and the number check that keeps the LLM honest.

The writer only sees FACTS: a flat dict of pre-formatted strings built from tool outputs.
Every number in the text it returns must appear in those facts (or in the user's request);
anything else fails the check and triggers a rewrite, then a template.
"""

from __future__ import annotations

import re

# --- Formatting (the UI uses the same rules so tiles match the text) --------------------------


def fmt_money(x: float) -> str:
    return f"{round(x):,}"


def fmt_t(x: float) -> str:
    return f"{x:,.1f}"


def fmt_pct(x: float) -> str:
    return f"{x:.1f}"


def fmt_int(x: int) -> str:
    return f"{int(x):,}"


def fmt_signed_money(x: float) -> str:
    return ("+" if x > 0 else "") + fmt_money(x)


def yes_no(flag: bool) -> str:
    return "yes" if flag else "no"


# --- Facts ---------------------------------------------------------------------------------


def build_facts(state: dict) -> dict[str, str]:
    """Flat facts from tool outputs only, every value already a display string."""
    facts: dict[str, str] = {}
    plan = state.get("plan") or {}
    k = plan.get("kpis") or {}
    if k:
        facts["orders_total"] = fmt_int(k["orders_total"])
        facts["total_cost"] = fmt_money(k["total_cost"])
        facts["total_carbon_t"] = fmt_t(k["total_carbon_t"])
        facts["late_orders"] = fmt_int(k["late_orders"])
        facts["unmet_orders"] = fmt_int(k["unmet_orders"])
        facts["on_time_orders"] = fmt_int(k["orders_total"] - k["late_orders"] - k["unmet_orders"])
        plants = sorted(k.get("plant_share", {}))
        facts["plants_total"] = fmt_int(len(plants))
        for p in plants:
            facts[f"plant_{p}_share_pct"] = fmt_pct(k["plant_share"][p] * 100)
            facts[f"plant_{p}_utilisation_pct"] = fmt_pct(k["plant_utilisation"][p] * 100)
            facts[f"plant_{p}_orders"] = fmt_int(
                sum(1 for r in plan.get("rows", []) if r["plant"] == p)
            )
        facts["solver_status"] = plan.get("status", "")
    weights = state.get("weights") or {}
    if weights:
        total = (weights["cost"] + weights["carbon"]) or 1.0
        facts["weight_cost_pct"] = fmt_pct(weights["cost"] / total * 100).removesuffix(".0")
        facts["weight_carbon_pct"] = fmt_pct(weights["carbon"] / total * 100).removesuffix(".0")
        facts["weight_lateness"] = f"{weights.get('lateness', 1.0):g}"
    check = state.get("check") or {}
    for flag in ("capacity_ok", "eligibility_ok", "delivery_ok", "complete_ok", "numbers_ok"):
        if flag in check:
            facts[flag] = yes_no(check[flag])
    late_ids = [r["order_id"] for r in plan.get("rows", []) if r["days_late"] > 0]
    if late_ids:
        facts["late_order_ids"] = ", ".join(late_ids[:10])
    if plan.get("unmet"):
        facts["unmet_order_ids"] = ", ".join(plan["unmet"][:10])
    for event in plan.get("events", []):
        facts.setdefault("capacity_events", "")
        facts["capacity_events"] += (
            f"{'; ' if facts['capacity_events'] else ''}Plant {event['plant']} "
            f"-{fmt_pct(event['loss_pct']).removesuffix('.0')}% from {event['from_date']} "
            f"to {event['to_date']}"
        )

    comparison = state.get("comparison")
    if comparison:
        facts["extra_cost"] = fmt_signed_money(comparison["extra_cost"])
        facts["extra_cost_pct"] = fmt_pct(comparison["extra_cost_pct"])
        facts["extra_carbon_t"] = ("+" if comparison["extra_carbon_t"] > 0 else "") + fmt_t(
            comparison["extra_carbon_t"]
        )
        facts["moved_count"] = fmt_int(comparison["moved_count"])
        facts["stability_pct"] = fmt_pct(comparison["stability_pct"])
        facts["late_orders_change"] = f"{comparison['late_orders_change']:+d}"
        facts["unmet_change"] = f"{comparison['unmet_change']:+d}"
        top = comparison["moved"][:5]
        if top:
            facts["top_moves"] = "; ".join(
                f"{m['order_id']} {m['from_plant'] or 'unmet'} to {m['to_plant'] or 'unmet'}"
                for m in top
            )
        base_k = (state.get("base_plan") or {}).get("kpis") or {}
        if base_k:
            facts["base_total_cost"] = fmt_money(base_k["total_cost"])
            facts["base_total_carbon_t"] = fmt_t(base_k["total_carbon_t"])
            facts["base_late_orders"] = fmt_int(base_k["late_orders"])

    for row in state.get("tradeoff") or []:
        cut = fmt_pct(row["carbon_cut_pct"]).removesuffix(".0")
        prefix = f"tradeoff_{cut}pct"
        facts[f"{prefix}_cut_pct"] = cut
        facts[f"{prefix}_cost"] = fmt_money(row["cost"])
        facts[f"{prefix}_carbon_t"] = fmt_t(row["carbon_t"])
        facts[f"{prefix}_extra_cost"] = fmt_signed_money(row["extra_cost"])
        facts[f"{prefix}_extra_cost_pct"] = fmt_pct(row["extra_cost_pct"])
        facts[f"{prefix}_late_orders"] = fmt_int(row["late_orders"])
        facts[f"{prefix}_feasible"] = yes_no(row["feasible"])
        if row.get("cost_per_tonne_saved") is not None:
            facts[f"{prefix}_cost_per_tonne_saved"] = fmt_money(row["cost_per_tonne_saved"])
    cut = (state.get("intent") or {}).get("carbon_cut_pct")
    if cut is not None:
        facts["requested_carbon_cut_pct"] = fmt_pct(cut).removesuffix(".0")

    explanation = state.get("explanation")
    if explanation and explanation.get("found"):
        facts["explain_order_id"] = explanation["order_id"]
        facts["explain_chosen_plant"] = explanation.get("chosen_plant") or "none (unmet)"
        for row in explanation["rows"]:
            if not row.get("eligible"):
                facts[f"explain_{row['plant']}_eligible"] = "no"
                continue
            p = f"explain_{row['plant']}"
            facts[f"{p}_cost"] = fmt_money(row["cost"])
            facts[f"{p}_carbon_kg"] = fmt_money(row["carbon_kg"])
            facts[f"{p}_arrival"] = row["arrival"]
            facts[f"{p}_days_late"] = fmt_int(row["days_late"])
            facts[f"{p}_duty"] = fmt_money(row["duty"])
        codes = explanation.get("reason_codes") or []
        if codes:
            facts["explain_reasons"] = "; ".join(c.get("detail") or c["code"] for c in codes)
        facts["explain_due"] = explanation.get("due", "")

    baseline = state.get("baseline")
    if baseline:
        facts["baseline_cost"] = fmt_money(baseline["kpis"]["total_cost"])
        facts["baseline_late_orders"] = fmt_int(baseline["kpis"]["late_orders"])
    return {key: value for key, value in facts.items() if value != ""}


# --- Number check ---------------------------------------------------------------------------

NUMBER = re.compile(r"\d[\d,]*\.?\d*")
ORDER_ID = re.compile(r"\bO-\d+\b")
CODE = re.compile(r"\b[A-Za-z]+\d+[A-Za-z0-9]*\b")  # P1, CO2e: digits inside words
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _clean(token: str) -> str:
    return token.rstrip(".,").replace(",", "")


def extract_numbers(text: str, known_dates: set[str] | None = None) -> list[str]:
    known_dates = known_dates or set()

    def mask(match: re.Match) -> str:
        return " " * len(match.group(0))

    masked = ORDER_ID.sub(mask, text)
    masked = CODE.sub(mask, masked)
    masked = ISO_DATE.sub(lambda m: mask(m) if m.group(0) in known_dates else m.group(0), masked)
    return [t for t in (_clean(m.group(0)) for m in NUMBER.finditer(masked)) if t]


def _fact_numbers(facts: dict[str, str]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for name, value in facts.items():
        for token in extract_numbers(str(value), _dates(facts)):
            index.setdefault(token, set()).add(name)
    return index


def _dates(facts: dict[str, str]) -> set[str]:
    return {d for value in facts.values() for d in ISO_DATE.findall(str(value))}


def allowed_numbers(facts: dict[str, str], request: str) -> set[str]:
    return set(_fact_numbers(facts)) | set(extract_numbers(request))


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return False


def check_numbers(text: str, facts: dict[str, str], request: str) -> dict:
    """Every number in `text` must be a fact (or come from the request)."""
    index = _fact_numbers(facts)
    from_request = set(extract_numbers(request))
    tokens = extract_numbers(text, _dates(facts))
    matches, unmatched = [], []
    for token in tokens:
        names = sorted({n for known, ns in index.items() if _same(token, known) for n in ns})
        if names:
            matches.append({"token": token, "facts": names})
        elif any(_same(token, r) for r in from_request):
            matches.append({"token": token, "facts": ["request"]})
        else:
            unmatched.append(token)
    return {
        "checked": len(tokens),
        "matched": len(tokens) - len(unmatched),
        "unmatched": unmatched,
        "ok": not unmatched,
        "matches": matches,
    }


# --- Templates (mock mode and the fallback; they pass the check by construction) ------------


def template_summary(answer_type: str, facts: dict[str, str]) -> str:
    f = facts.get
    if answer_type in ("clarification_needed", "refused"):
        return ""
    parts: list[str] = []
    if f("explain_order_id"):
        parts.append(
            f"Order {f('explain_order_id')} is planned at Plant {f('explain_chosen_plant')}."
        )
        if f("explain_reasons"):
            parts.append(f"Why: {f('explain_reasons')}.")
    if f("moved_count") is not None:
        parts.append(
            f"The re-plan moves {f('moved_count')} orders and changes cost by "
            f"{f('extra_cost')} ({f('extra_cost_pct')}%) and carbon by {f('extra_carbon_t')} t; "
            f"{f('stability_pct')}% of orders keep their plant."
        )
    cut = f("requested_carbon_cut_pct")
    if cut and f(f"tradeoff_{cut}pct_cost"):
        feasible = f(f"tradeoff_{cut}pct_feasible") == "yes"
        if feasible:
            parts.append(
                f"A {cut}% carbon cut costs {f(f'tradeoff_{cut}pct_extra_cost')} "
                f"({f(f'tradeoff_{cut}pct_extra_cost_pct')}%), for a total of "
                f"{f(f'tradeoff_{cut}pct_cost')} and {f(f'tradeoff_{cut}pct_carbon_t')} t."
            )
        else:
            parts.append(
                f"A {cut}% carbon cut is not reachable without leaving orders unmet within "
                "current capacity."
            )
    if f("total_cost"):
        parts.append(
            f"The plan covers {f('orders_total')} orders for a landed cost of "
            f"{f('total_cost')} and {f('total_carbon_t')} t CO2e, with {f('late_orders')} late "
            f"and {f('unmet_orders')} unmet."
        )
    if f("unmet_order_ids"):
        parts.append(f"Unmet orders: {f('unmet_order_ids')}.")
    return " ".join(parts)


def template_brief(facts: dict[str, str]) -> str:
    f = facts.get
    situation = (
        f"Situation\n{f('orders_total')} orders across {f('plants_total')} plants"
        + (f", with capacity events: {f('capacity_events')}" if f("capacity_events") else "")
        + "."
    )
    plan = (
        f"Plan\nLanded cost {f('total_cost')} and {f('total_carbon_t')} t CO2e. "
        f"{f('on_time_orders')} orders arrive on time, {f('late_orders')} late and "
        f"{f('unmet_orders')} unmet. Weights: cost {f('weight_cost_pct')}%, carbon "
        f"{f('weight_carbon_pct')}%."
    )
    if f("baseline_cost"):
        plan += (
            f" The cheapest-plant rule would cost {f('baseline_cost')} but leave "
            f"{f('baseline_late_orders')} orders late."
        )
    trade = "Trade-off\n"
    if f("tradeoff_10pct_cost"):
        trade += (
            f"A 10% carbon cut costs {f('tradeoff_10pct_extra_cost')} "
            f"({f('tradeoff_10pct_extra_cost_pct')}%)."
        )
    else:
        trade += "No trade-off points were computed for this request."
    risks = "Risks\n" + (
        f"Late orders: {f('late_order_ids')}." if f("late_order_ids") else "No late orders."
    )
    if f("unmet_order_ids"):
        risks += f" Unmet orders: {f('unmet_order_ids')}."
    decision = (
        "Decision needed\nApprove the plan, or ask for a carbon cut or a re-plan before release."
    )
    return "\n\n".join([situation, plan, trade, risks, decision])
