// API contract types. Field names match the backend's AnalyzeResponse exactly.

export type AnswerType =
  "allocation" | "scenario" | "infeasible" | "clarification_needed" | "refused" | "brief";

export interface Weights {
  cost: number;
  carbon: number;
  lateness: number;
}

export interface CapacityLoss {
  plant: string;
  pct: number;
  from_date?: string | null;
  to_date?: string | null;
}

export interface Scenario {
  capacity_loss?: CapacityLoss[];
  ignore_events?: boolean;
  exclude_plants?: string[];
  on_time_only?: boolean;
  carbon_cut_pct?: number;
}

export interface AllocationRow {
  order_id: string;
  plant: string | null;
  cost: number;
  carbon_kg: number;
  arrival: string | null;
  on_time: boolean;
  week: number | null;
  days_late: number;
  moved: boolean;
  base_plant: string | null;
  production?: number;
  energy?: number;
  transport?: number;
  duty?: number;
  qty?: number;
  product?: string;
  destination?: string;
  due?: string;
}

export interface Kpis {
  total_cost: number;
  total_carbon_t: number;
  late_orders: number;
  plant_utilisation: Record<string, number>;
  unmet_orders: number;
  orders_total: number;
  plant_share: Record<string, number>;
}

export interface TradeoffRow {
  carbon_cut_pct: number;
  cost: number;
  late_orders: number;
  carbon_t: number;
  unmet_orders: number;
  extra_cost: number;
  extra_cost_pct: number;
  cost_per_tonne_saved: number | null;
  feasible: boolean;
}

export interface Validator {
  capacity_ok: boolean;
  eligibility_ok: boolean;
  delivery_ok: boolean;
  complete_ok: boolean;
  numbers_ok: boolean;
}

export interface Recommendation {
  action: string;
  rationale: string;
  evidence_refs: string[];
  confidence: string;
  estimated_impact: Record<string, number>;
  requires_approval: boolean;
}

export interface MovedOrder {
  order_id: string;
  from_plant: string | null;
  to_plant: string | null;
  cost_change: number;
  carbon_change_kg: number;
  became_late: boolean;
}

export interface Comparison {
  extra_cost: number;
  extra_cost_pct: number;
  extra_carbon_t: number;
  extra_carbon_pct: number;
  late_orders_change: number;
  unmet_change: number;
  moved_count: number;
  stability_pct: number;
  moved: MovedOrder[];
}

export interface ExplanationRow {
  plant: string;
  eligible: boolean;
  cost: number | null;
  production: number | null;
  energy: number | null;
  transport: number | null;
  duty: number | null;
  carbon_kg: number | null;
  arrival: string | null;
  on_time: boolean | null;
  days_late: number | null;
  week: number | null;
  capacity_left_in_week: number | null;
  chosen: boolean;
}

export interface ReasonCode {
  code: string;
  plant?: string | null;
  detail?: string;
}

export interface Explanation {
  found: boolean;
  order_id?: string;
  rows?: ExplanationRow[];
  reason_codes?: ReasonCode[];
}

export interface CapacityCell {
  plant: string;
  product: string;
  week: number;
  week_start: string;
  base: number;
  effective: number;
  used: number;
}

export interface NumberMatch {
  token: string;
  facts: string[];
}

export interface Meta {
  solver: string;
  solver_status: string;
  solve_ms: number;
  latency_ms: number;
  llm_calls: number;
  tokens: number;
  number_check: { checked: number; matched: number; matches?: NumberMatch[] };
}

export interface AnalyzeResponse {
  run_id: string;
  answer_type: AnswerType;
  summary: string;
  allocation: AllocationRow[];
  kpis: Kpis;
  tradeoff: TradeoffRow[];
  weights_used: Partial<Weights>;
  validator: Validator;
  assumptions: string[];
  limitations: string[];
  recommendations: Recommendation[];
  comparison: Comparison | null;
  unmet_orders: string[];
  late_orders_list: string[];
  explanation: Explanation | null;
  brief: string | null;
  capacity_grid?: CapacityCell[];
  meta: Meta;
  request?: string;
}

export interface TraceStep {
  step: number;
  agent: string;
  tool: string;
  input?: unknown;
  output?: unknown;
  ms: number;
}

export interface Trace {
  run_id: string;
  request: string;
  answer_type: AnswerType;
  steps: TraceStep[];
  llm_calls: number;
  tokens: number;
  latency_ms: number;
  number_check: { checked: number; matched: number };
  data_used?: unknown;
  created_at: string;
}

export interface RunSummary {
  run_id: string;
  request: string;
  answer_type: AnswerType;
  created_at: string;
  latency_ms?: number;
}

export interface Health {
  status: string;
  api: string;
  data_store: string;
  llm: string;
  provider?: string;
  model?: string;
  rows?: Record<string, number>;
}

export interface ValidationCheck {
  id: string;
  name: string;
  ok: boolean;
  detail: string;
}

export interface ValidationReport {
  ok: boolean;
  checks: ValidationCheck[];
  units: Record<string, string>;
  planning_start?: string;
  row_counts?: Record<string, number>;
}

export interface IngestResult {
  table: string;
  rows_loaded: number;
  rows_rejected: number;
  status: "ok" | "partial" | "error";
  rejects: { row: number; reason: string }[];
  ignored_columns: string[];
  errors?: string[];
  validation?: ValidationReport;
}

export interface DataPage {
  columns: string[];
  rows: Record<string, string | number | null>[];
  total: number;
}

export interface StepEvent {
  step: number;
  agent: string;
  tool: string;
  ms?: number;
  output?: Record<string, unknown>;
}
