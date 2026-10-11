// Sample answer data used to show real-looking results without calling the API.

// Demo fixtures in the exact AnalyzeResponse shape. Used by the landing page showcase and by
// fixture mode (VITE_USE_FIXTURES=true) before the API is running. scripts/export_fixtures.py
// replaces the values with real backend output.

import type {
  AllocationRow,
  AnalyzeResponse,
  CapacityCell,
  RunSummary,
  TradeoffRow,
} from "@/lib/types";

const PLANTS = ["A", "B", "C"] as const;
const PRODUCTS = ["P1", "P2", "P3", "P4", "P5"];
const DESTS = ["Germany", "France", "UK", "USA", "India", "Japan", "Brazil", "UAE", "Singapore"];

// Small deterministic generator so the fixtures never change between builds.
function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

function iso(day: number): string {
  const d = new Date(Date.UTC(2026, 9, 12 + day));
  return d.toISOString().slice(0, 10);
}

function makeRows(): AllocationRow[] {
  const r = rng(42);
  const rows: AllocationRow[] = [];
  for (let i = 1; i <= 150; i++) {
    const product = PRODUCTS[Math.floor(r() * PRODUCTS.length)];
    const plant = product === "P4" ? "A" : product === "P5" ? "B" : PLANTS[Math.floor(r() * 3)];
    const qty = 50 + Math.floor(r() * 56) * 10;
    const week = Math.floor(r() * 4);
    const due = 7 + Math.floor(r() * 21);
    const arrival = week * 7 + 4 + 2 + Math.floor(r() * 10);
    const late = i % 8 === 0 ? 1 + Math.floor(r() * 6) : 0;
    const unit = plant === "A" ? 26 : plant === "B" ? 29 : 33;
    const production = Math.round(qty * (unit - 4) * 100) / 100;
    const energy = Math.round(qty * 0.6 * 100) / 100;
    const transport = Math.round(qty * (1.5 + r() * 2) * 100) / 100;
    const duty = Math.round(qty * r() * 1.5 * 100) / 100;
    rows.push({
      order_id: `O-${String(i).padStart(3, "0")}`,
      plant,
      week,
      cost: Math.round((production + energy + transport + duty) * 100) / 100,
      carbon_kg: Math.round(qty * (plant === "A" ? 6.2 : plant === "B" ? 3.6 : 1.4) * 1000) / 1000,
      arrival: iso(late ? due + late : Math.min(arrival, due)),
      on_time: late === 0,
      days_late: late,
      moved: false,
      base_plant: null,
      production,
      energy,
      transport,
      duty,
      qty,
      product,
      destination: DESTS[Math.floor(r() * DESTS.length)],
      due: iso(due),
    });
  }
  return rows;
}

const rows = makeRows();
const totalCost = Math.round(rows.reduce((s, x) => s + x.cost, 0) * 100) / 100;
const totalCarbon = Math.round(rows.reduce((s, x) => s + x.carbon_kg, 0)) / 1000;
const late = rows.filter((x) => x.days_late > 0);

const capacity: CapacityCell[] = [];
for (const plant of PLANTS) {
  for (const product of plant === "A"
    ? ["P1", "P2", "P3", "P4"]
    : plant === "B"
      ? ["P1", "P2", "P3", "P5"]
      : ["P1", "P2", "P3"]) {
    for (let week = 0; week < 5; week++) {
      const base = plant === "A" ? 2170 : plant === "B" ? 1500 : 580;
      const used = rows
        .filter((x) => x.plant === plant && x.product === product && x.week === week)
        .reduce((s, x) => s + (x.qty ?? 0), 0);
      capacity.push({
        plant,
        product,
        week,
        week_start: iso(week * 7),
        base,
        effective: base,
        used: Math.min(used, base),
      });
    }
  }
}

const tradeoff: TradeoffRow[] = [0, 5, 10, 15, 20].map((cut) => {
  const extra = cut === 0 ? 0 : Math.round(cut * cut * 210 + cut * 1400);
  return {
    carbon_cut_pct: cut,
    cost: Math.round(totalCost + extra),
    carbon_t: Math.round(totalCarbon * (1 - cut / 100) * 10) / 10,
    late_orders: late.length + Math.floor(cut / 5),
    unmet_orders: cut >= 20 ? 3 : 0,
    extra_cost: extra,
    extra_cost_pct: Math.round((extra / totalCost) * 1000) / 10,
    cost_per_tonne_saved: cut === 0 ? null : Math.round(extra / ((totalCarbon * cut) / 100)),
    feasible: cut < 20,
  };
});

const money = (x: number) => Math.round(x).toLocaleString("en-US");

export const allocationFixture: AnalyzeResponse = {
  run_id: "al-demo01",
  request: "Allocate this week's orders.",
  answer_type: "allocation",
  summary: `All 150 orders are planned for ${money(totalCost)} and ${totalCarbon.toFixed(1)} t CO2e. ${late.length} orders arrive late because no plant can reach them by their due date; every capacity, eligibility and delivery check passed.`,
  allocation: rows,
  kpis: {
    total_cost: totalCost,
    total_carbon_t: totalCarbon,
    late_orders: late.length,
    plant_utilisation: { A: 0.48, B: 0.64, C: 0.69 },
    unmet_orders: 0,
    orders_total: 150,
    plant_share: { A: 0.41, B: 0.38, C: 0.21 },
  },
  tradeoff,
  weights_used: { cost: 0.7, carbon: 0.3, lateness: 1 },
  validator: {
    capacity_ok: true,
    eligibility_ok: true,
    delivery_ok: true,
    complete_ok: true,
    numbers_ok: true,
  },
  assumptions: [
    "Weights: cost 70%, carbon 30%, lateness 1.0. Cost is the primary objective; carbon gets a meaningful share.",
    "Duty is charged on goods plus freight (CIF-style).",
    "Energy price comes from plants.csv; blank values use the default of 0.10 per kWh.",
    "Each order is produced whole, in one week, at one plant.",
    "Goods ship on the Friday of their production week.",
  ],
  limitations: [
    "Duty rates are constant for the period.",
    "Transit days are fixed; inventory and changeovers are not modelled.",
    "Trade-off points depend on the carbon-cut grid.",
  ],
  recommendations: [
    {
      action: `Notify customers of ${late.length} late orders`,
      rationale: "No plant can deliver them by their due date at any cost.",
      evidence_refs: [
        "tool:solve_allocation",
        `orders:${late
          .slice(0, 4)
          .map((x) => x.order_id)
          .join(",")}`,
      ],
      confidence: "high",
      estimated_impact: {},
      requires_approval: false,
    },
    {
      action: "Consider a 10% carbon cut",
      rationale: "The cheapest cut per tonne on the trade-off curve.",
      evidence_refs: ["tool:tradeoff_table"],
      confidence: "high",
      estimated_impact: { cost: tradeoff[2].extra_cost, carbon_t: -Math.round(totalCarbon * 0.1) },
      requires_approval: true,
    },
  ],
  comparison: null,
  unmet_orders: [],
  late_orders_list: late.map((x) => x.order_id),
  explanation: null,
  brief: null,
  capacity_grid: capacity,
  meta: {
    solver: "cpsat",
    solver_status: "OPTIMAL",
    solve_ms: 2987,
    latency_ms: 6420,
    llm_calls: 2,
    tokens: 2310,
    number_check: {
      checked: 4,
      matched: 4,
      matches: [
        { token: "150", facts: ["orders_total"] },
        { token: money(totalCost), facts: ["total_cost"] },
        { token: totalCarbon.toFixed(1), facts: ["total_carbon_t"] },
        { token: String(late.length), facts: ["late_orders"] },
      ],
    },
  },
};

const movedRows = rows.map((row, i) =>
  i % 11 === 3 && row.plant === "B"
    ? { ...row, plant: i % 2 ? "A" : "C", moved: true, base_plant: "B" }
    : row,
);
const moved = movedRows.filter((x) => x.moved);

export const scenarioFixture: AnalyzeResponse = {
  ...allocationFixture,
  run_id: "al-demo02",
  request: "Plant B loses 30% capacity. Re-plan.",
  answer_type: "scenario",
  allocation: movedRows,
  summary: `With Plant B at 70% capacity, ${moved.length} orders move to other plants. The re-plan costs 18,420 more and adds 4.1 t CO2e; nothing is left unmet.`,
  comparison: {
    extra_cost: 18420,
    extra_cost_pct: 1.3,
    extra_carbon_t: 4.1,
    extra_carbon_pct: 2,
    late_orders_change: 1,
    unmet_change: 0,
    moved_count: moved.length,
    stability_pct: Math.round((1 - moved.length / 150) * 1000) / 10,
    moved: moved.map((x, i) => ({
      order_id: x.order_id,
      from_plant: "B",
      to_plant: x.plant,
      cost_change: 1800 - i * 90,
      carbon_change_kg: x.plant === "A" ? 520 - i * 10 : -180 + i * 5,
      became_late: i === 2,
    })),
  },
  recommendations: [
    {
      action: `Approve re-plan: move ${moved.length} orders off Plant B`,
      rationale: "Keeps every order within capacity after the loss.",
      evidence_refs: [
        "tool:compare_plans",
        `orders:${moved
          .slice(0, 3)
          .map((x) => x.order_id)
          .join(",")}`,
      ],
      confidence: "high",
      estimated_impact: { cost: 18420, carbon_t: 4.1 },
      requires_approval: true,
    },
  ],
};

export const explainFixture: AnalyzeResponse = {
  ...allocationFixture,
  run_id: "al-demo03",
  request: "Why was order 77 built in Plant C?",
  summary:
    "O-077 goes to Plant B because Plant A, though cheapest at 14,212, would arrive on 30 Oct, 3 days after the 27 Oct due date. B delivers on 26 Oct for 14,601.",
  explanation: {
    found: true,
    order_id: "O-077",
    rows: [
      {
        plant: "A",
        eligible: true,
        cost: 14212.4,
        production: 10075,
        energy: 164.4,
        transport: 2000,
        duty: 492.6,
        carbon_kg: 2873.5,
        arrival: "2026-10-30",
        on_time: false,
        days_late: 3,
        week: 0,
        capacity_left_in_week: 640,
        chosen: false,
      },
      {
        plant: "B",
        eligible: true,
        cost: 14601.0,
        production: 12090,
        energy: 216.7,
        transport: 820,
        duty: 0,
        carbon_kg: 1072.4,
        arrival: "2026-10-26",
        on_time: true,
        days_late: 0,
        week: 1,
        capacity_left_in_week: 410,
        chosen: true,
      },
      {
        plant: "C",
        eligible: true,
        cost: 17210.0,
        production: 15770,
        energy: 264.6,
        transport: 1100,
        duty: 0,
        carbon_kg: 616.8,
        arrival: "2026-10-21",
        on_time: true,
        days_late: 0,
        week: 0,
        capacity_left_in_week: 80,
        chosen: false,
      },
    ],
    reason_codes: [
      {
        code: "CHEAPEST_OPTION_LATE",
        plant: "A",
        detail: "Plant A is cheapest but arrives 3 days late.",
      },
      { code: "LOWER_CARBON", plant: "B", detail: "B emits less than A." },
      {
        code: "CAPACITY_FULL_AT_CHEAPER_PLANT",
        plant: "C",
        detail: "C has 80 units left in week 0.",
      },
    ],
  },
};

export const briefFixture: AnalyzeResponse = {
  ...allocationFixture,
  run_id: "al-demo04",
  request: "Write the brief for the leadership team.",
  answer_type: "brief",
  brief: [
    "Situation",
    `We have 150 orders across three plants due between 19 Oct and 8 Nov. ${late.length} of them cannot reach their customers on time from any plant.`,
    "Plan",
    `The recommended plan costs ${money(totalCost)} and emits ${totalCarbon.toFixed(1)} t CO2e. Every capacity, eligibility and delivery check passed.`,
    "Trade-off",
    `A 10% carbon cut costs ${money(tradeoff[2].extra_cost)} more, about ${money(tradeoff[2].cost_per_tonne_saved ?? 0)} per tonne saved.`,
    "Risks",
    "Plant B's grid is dirtier in the week of 26 Oct, and a capacity loss at B would push work to A.",
    "Decision needed",
    "Approve the plan, and decide whether to fund the 10% carbon cut.",
  ].join("\n"),
};

export const runsFixture: RunSummary[] = [
  {
    run_id: "al-demo04",
    request: briefFixture.request!,
    answer_type: "brief",
    created_at: "2026-10-11T15:42:00Z",
    latency_ms: 9120,
  },
  {
    run_id: "al-demo03",
    request: explainFixture.request!,
    answer_type: "allocation",
    created_at: "2026-10-11T15:38:00Z",
    latency_ms: 4410,
  },
  {
    run_id: "al-demo02",
    request: scenarioFixture.request!,
    answer_type: "scenario",
    created_at: "2026-10-11T15:31:00Z",
    latency_ms: 7890,
  },
  {
    run_id: "al-demo01",
    request: allocationFixture.request!,
    answer_type: "allocation",
    created_at: "2026-10-11T15:20:00Z",
    latency_ms: 6420,
  },
];

export const fixturesById: Record<string, AnalyzeResponse> = {
  "al-demo01": allocationFixture,
  "al-demo02": scenarioFixture,
  "al-demo03": explainFixture,
  "al-demo04": briefFixture,
};

export function fixtureFor(request: string): AnalyzeResponse {
  const text = request.toLowerCase();
  if (/brief|leadership/.test(text)) return briefFixture;
  if (/why|order\s*\d+/.test(text)) return explainFixture;
  if (/loses|re-?plan/.test(text)) return scenarioFixture;
  if (/carbon cut|%/.test(text))
    return { ...allocationFixture, run_id: "al-demo05", answer_type: "scenario" };
  return allocationFixture;
}
