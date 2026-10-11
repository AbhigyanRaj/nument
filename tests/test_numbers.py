from app.core.numbers import check_numbers, extract_numbers, template_brief, template_summary

FACTS = {
    "orders_total": "150",
    "total_cost": "1,368,270",
    "total_carbon_t": "208.5",
    "late_orders": "20",
    "unmet_orders": "0",
    "on_time_orders": "130",
    "plants_total": "3",
    "weight_cost_pct": "70",
    "weight_carbon_pct": "30",
    "late_order_ids": "O-003, O-077",
    "explain_C_arrival": "2026-10-21",
}


def test_text_using_only_fact_numbers_passes():
    text = "All 150 orders cost 1,368,270 with 208.5 t CO2e; 20 are late."
    result = check_numbers(text, FACTS, "Allocate this week's orders.")
    assert result["ok"] and result["checked"] == 4 == result["matched"]
    assert {"token": "1368270", "facts": ["total_cost"]} in result["matches"]


def test_an_invented_number_fails_and_is_listed():
    result = check_numbers("Total cost is 999,999.", FACTS, "")
    assert not result["ok"]
    assert result["unmatched"] == ["999999"]


def test_order_ids_products_and_known_dates_are_not_numbers():
    assert extract_numbers("O-077 (P1) arrives 2026-10-21.", {"2026-10-21"}) == []
    assert check_numbers("O-077 arrives 2026-10-21 from Plant C.", FACTS, "")["ok"]


def test_numbers_from_the_request_are_allowed():
    assert check_numbers("A 10% cut", FACTS, "What does a 10% carbon cut cost?")["ok"]


def test_rounding_tolerance_accepts_trailing_zeros():
    assert check_numbers("Carbon 208.50 t", FACTS, "")["ok"]


def test_templates_pass_by_construction():
    summary = template_summary("allocation", FACTS)
    brief = template_brief(FACTS)
    assert check_numbers(summary, FACTS, "")["ok"], summary
    assert check_numbers(brief, FACTS, "")["ok"], brief
    for heading in ("Situation", "Plan", "Trade-off", "Risks", "Decision needed"):
        assert heading in brief
