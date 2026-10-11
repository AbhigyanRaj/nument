// The main planner screen: ask a question, watch the steps live,
// then see the plan, numbers, checks, charts and tables.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Check,
  FileText,
  MessageSquareQuote,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";

import {
  AllocationTable,
  AnswerBadge,
  CheckedSummary,
  ExplainTable,
  KpiMosaic,
  MovedTable,
  Recommendations,
  ValidatorBadges,
} from "@/components/app/result";
import { CapacityHeatmap, TradeoffChart, UtilisationChart } from "@/components/app/viz";
import { Ornament } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  Slider,
  SoftAccordion,
  Textarea,
} from "@/components/ui/controls";
import { api } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import type { AnalyzeResponse, Scenario, StepEvent, Weights } from "@/lib/types";
import { cn } from "@/lib/utils";

export const EXAMPLES = [
  "Allocate this week's orders.",
  "What is the cheapest plan that is on time?",
  "Why was order 77 built in Plant C?",
  "What does a 10% carbon cut cost?",
  "Plant B loses 30% capacity. Re-plan.",
  "Write the brief for the leadership team.",
];

const STEPS = [
  { key: "classify", label: "Understand", agent: "router" },
  { key: "solve", label: "Optimise", agent: "optimiser" },
  { key: "validate", label: "Validate", agent: "checker" },
  { key: "compare", label: "Compare", agent: "scenario" },
  { key: "write", label: "Write", agent: "writer" },
  { key: "number_check", label: "Check numbers", agent: "checker" },
];

type StepState = { status: "idle" | "running" | "done"; ms?: number; count: number };

function stepIndex(event: StepEvent): number {
  const tool = event.tool ?? "";
  if (/classify/.test(tool)) return 0;
  if (/solve/.test(tool)) return 1;
  if (/validate/.test(tool)) return 2;
  if (/compare/.test(tool)) return 3;
  if (/write/.test(tool)) return 4;
  if (/check_numbers|number/.test(tool)) return 5;
  if (/finish|early/.test(tool)) return 5;
  return Math.min(5, Math.max(0, event.step - 1));
}

const DEFAULT_WEIGHTS: Weights = { cost: 0.7, carbon: 0.3, lateness: 1 };

function WeightsPopover({
  weights,
  onChange,
}: {
  weights: Weights | null;
  onChange: (w: Weights | null) => void;
}) {
  const w = weights ?? DEFAULT_WEIGHTS;
  return (
    <Popover>
      <PopoverTrigger className={cn("prompt-chip", weights && "prompt-chip--set")}>
        <SlidersHorizontal className="size-3.5" strokeWidth={1.75} />
        Weights {Math.round(w.cost * 100)}/{Math.round(w.carbon * 100)}
      </PopoverTrigger>
      <PopoverContent>
        <p className="text-caption font-medium text-tx">Objective weights</p>
        <p className="mt-1 text-[13px] text-tx-tertiary">
          Cost and carbon share 100%. Lateness 1.0 never trades a date for money.
        </p>
        <div className="mt-5 flex flex-col gap-5">
          <label className="flex flex-col gap-2 text-caption text-tx-secondary">
            <span className="flex justify-between">
              Cost <span className="tabular">{Math.round(w.cost * 100)}%</span>
            </span>
            <Slider
              label="Cost weight"
              value={w.cost}
              onValueChange={(v) =>
                onChange({ ...w, cost: v, carbon: Math.round((1 - v) * 100) / 100 })
              }
            />
          </label>
          <p className="-mt-3 text-[13px] text-tx-tertiary">Carbon {Math.round(w.carbon * 100)}%</p>
          <label className="flex flex-col gap-2 text-caption text-tx-secondary">
            <span className="flex justify-between">
              Lateness <span className="tabular">{w.lateness.toFixed(2)}</span>
            </span>
            <Slider
              label="Lateness weight"
              value={w.lateness}
              onValueChange={(v) => onChange({ ...w, lateness: v })}
            />
          </label>
          <button
            className="self-start text-caption text-indigo-700 hover:text-indigo-900"
            onClick={() => onChange(null)}
          >
            Use defaults
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ScenarioPopover({
  scenario,
  onChange,
}: {
  scenario: Scenario | null;
  onChange: (s: Scenario | null) => void;
}) {
  const loss = scenario?.capacity_loss?.[0];
  const [plant, setPlant] = useState(loss?.plant ?? "none");
  const [pct, setPct] = useState(loss?.pct ?? 30);
  const apply = (p: string, value: number) => {
    setPlant(p);
    setPct(value);
    onChange(p === "none" ? null : { capacity_loss: [{ plant: p, pct: value }] });
  };
  return (
    <Popover>
      <PopoverTrigger className={cn("prompt-chip", scenario && "prompt-chip--set")}>
        {scenario ? `Plant ${plant} −${pct}%` : "Scenario"}
      </PopoverTrigger>
      <PopoverContent>
        <p className="text-caption font-medium text-tx">Capacity loss</p>
        <p className="mt-1 text-[13px] text-tx-tertiary">
          Applied to the whole horizon on top of loaded events.
        </p>
        <div className="mt-4 flex flex-col gap-4">
          <Select
            label="Plant"
            value={plant}
            onValueChange={(v) => apply(v, pct)}
            options={[
              { value: "none", label: "No scenario" },
              { value: "A", label: "Plant A" },
              { value: "B", label: "Plant B" },
              { value: "C", label: "Plant C" },
            ]}
          />
          <label className="flex flex-col gap-2 text-caption text-tx-secondary">
            <span className="flex justify-between">
              Loss <span className="tabular">{pct}%</span>
            </span>
            <Slider
              label="Capacity loss"
              min={5}
              max={100}
              step={5}
              value={pct}
              onValueChange={(v) => apply(plant, v)}
            />
          </label>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Stepper({ states }: { states: StepState[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-y-3">
      {STEPS.map((step, i) => {
        const s = states[i];
        return (
          <li
            key={step.key}
            className={cn("flex items-center", s.status === "idle" && "max-md:hidden")}
          >
            {i > 0 && <span className="mx-1.5 hidden h-0.5 w-6 rounded-full bg-st md:block" />}
            <span
              className={cn(
                "inline-flex items-center gap-2 rounded-full border border-st bg-white py-1.5 pr-3.5 pl-1.5 text-[13px] transition-all duration-300",
                s.status === "idle" && "text-tx-tertiary",
                s.status === "running" && "animate-jump text-tx shadow-[0_8px_26px_rgba(0,0,0,.1)]",
                s.status === "done" && "text-tx",
              )}
            >
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full text-[11px] font-medium",
                  s.status === "done"
                    ? "bg-green-100 text-green-800"
                    : s.status === "running"
                      ? "bg-indigo-100 text-indigo-800"
                      : "bg-sf-tertiary text-tx-tertiary",
                )}
              >
                {s.status === "done" ? <Check className="size-3.5" strokeWidth={2.5} /> : i + 1}
              </span>
              {step.label}
              {s.count > 1 && <span className="text-tx-tertiary">×{s.count}</span>}
              {s.status === "done" && s.ms !== undefined && (
                <span className="text-tx-tertiary tabular">{s.ms}ms</span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 animate-fade-up">
      <div className="flex items-end justify-between gap-3">
        <h2 className="text-xl font-medium tracking-[-0.015em] text-tx">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

const HEADLINE: Record<AnalyzeResponse["answer_type"], string> = {
  allocation: "Your plan is ready",
  scenario: "Your what-if plan is ready",
  brief: "Your leadership brief is ready",
  infeasible: "Not fully possible: here is the closest plan",
  clarification_needed: "I need one more detail",
  refused: "I can't do that",
};

const PLANT_COLOUR: Record<string, string> = {
  A: "bg-indigo-700",
  B: "bg-orange-700",
  C: "bg-green-600",
};

function StackBar({
  title,
  parts,
}: {
  title: string;
  parts: { label: string; value: number; colour: string }[];
}) {
  const total = parts.reduce((sum, p) => sum + p.value, 0) || 1;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-caption font-medium text-tx">{title}</p>
      <div className="flex h-3 overflow-hidden rounded-full bg-sf-tertiary">
        {parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <span
              key={p.label}
              className={cn("h-full transition-[width] duration-700", p.colour)}
              style={{ width: `${(p.value / total) * 100}%` }}
              title={`${p.label}: ${p.value}`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-1.5 text-caption text-tx-secondary">
            <span className={cn("size-2.5 rounded-full", p.colour)} />
            {p.label} <span className="text-tx tabular">{p.value}</span>
            <span className="text-tx-tertiary tabular">
              ({Math.round((p.value / total) * 100)}%)
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** The plan at a glance: where the orders go and how they arrive. */
function PlanSnapshot({ data }: { data: AnalyzeResponse }) {
  const byPlant = new Map<string, number>();
  for (const row of data.allocation) {
    if (row.plant) byPlant.set(row.plant, (byPlant.get(row.plant) ?? 0) + 1);
  }
  const plants = [...byPlant.keys()].sort();
  const late = data.allocation.filter((r) => r.days_late > 0).length;
  const unmet = data.unmet_orders?.length ?? 0;
  return (
    <div className="grid gap-5 rounded-2xl border border-st-secondary p-5 sm:grid-cols-2">
      <StackBar
        title="Where the orders go"
        parts={plants.map((p) => ({
          label: `Plant ${p}`,
          value: byPlant.get(p) ?? 0,
          colour: PLANT_COLOUR[p] ?? "bg-grey-500",
        }))}
      />
      <StackBar
        title="How they arrive"
        parts={[
          { label: "On time", value: data.allocation.length - late, colour: "bg-green-600" },
          { label: "Late", value: late, colour: "bg-orange-700" },
          { label: "Unmet", value: unmet, colour: "bg-red-500" },
        ]}
      />
    </div>
  );
}

function Report({ data }: { data: AnalyzeResponse }) {
  const nc = data.meta?.number_check;
  const planned = data.allocation.length > 0;
  return (
    <div className="flex flex-col gap-12">
      {/* Answer card in the events double bezel: the page's one featured item. */}
      <div className="animate-fade-up rounded-[28px] border border-st-secondary bg-sf p-2">
        <div className="grid gap-6 rounded-[20px] bg-white p-6 md:grid-cols-[1fr_260px] md:p-8">
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap items-center gap-3">
              <AnswerBadge type={data.answer_type} />
              <h2 className="text-[22px] leading-tight font-medium tracking-[-0.015em] text-tx">
                {HEADLINE[data.answer_type]}
              </h2>
            </div>
            {data.request && (
              <p className="flex items-start gap-2 text-caption text-tx-tertiary">
                <MessageSquareQuote className="mt-0.5 size-4 shrink-0" strokeWidth={1.5} />
                <span>
                  You asked: <span className="text-tx-secondary">{data.request}</span>
                </span>
              </p>
            )}
            <div className="rounded-2xl border border-st-secondary bg-sf p-5">
              <p className="mb-2 flex items-center gap-1.5 text-label font-medium tracking-[0.08em] text-tx-tertiary uppercase">
                <ShieldCheck className="size-3.5 text-green-700" strokeWidth={2} />
                nument's answer · every number verified
              </p>
              <CheckedSummary text={data.summary} matches={nc?.matches} />
            </div>
            {planned && <PlanSnapshot data={data} />}
            {data.brief && (
              <Button asChild variant="app" size="sm" className="self-start">
                <Link to={`/app/brief/${data.run_id}`}>
                  <FileText className="size-4" strokeWidth={1.75} /> Open the brief
                </Link>
              </Button>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 self-start rounded-2xl bg-sf-secondary p-4 text-caption md:grid-cols-1">
            {[
              ["Run", data.run_id],
              ["Solver", `${data.meta?.solver ?? "—"} · ${data.meta?.solver_status ?? "—"}`],
              ["Latency", `${((data.meta?.latency_ms ?? 0) / 1000).toFixed(1)} s`],
              ["LLM calls", `${data.meta?.llm_calls ?? 0} · ${data.meta?.tokens ?? 0} tokens`],
              ["Numbers checked", nc ? `${nc.matched} of ${nc.checked} matched` : "—"],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-label text-tx-tertiary">{k}</dt>
                <dd className="text-tx tabular">{v}</dd>
              </div>
            ))}
            <div className="col-span-2 md:col-span-1">
              <Link
                to={`/app/trace/${data.run_id}`}
                className="text-caption text-indigo-700 hover:text-indigo-900"
              >
                Open trace →
              </Link>
            </div>
          </dl>
        </div>
      </div>

      {planned && (
        <>
          <KpiMosaic data={data} />
          <Section title="Plan checks">
            <ValidatorBadges validator={data.validator} />
          </Section>
        </>
      )}

      {data.recommendations?.length > 0 && (
        <Section title="Recommendations">
          <Recommendations items={data.recommendations} />
        </Section>
      )}

      {data.explanation && (
        <Section title={`Why ${data.explanation.order_id ?? "this order"} went where it did`}>
          <ExplainTable explanation={data.explanation} />
        </Section>
      )}

      {data.comparison && (
        <Section title="What moved">
          <MovedTable comparison={data.comparison} />
        </Section>
      )}

      {planned && (
        <div className="grid gap-2 xl:grid-cols-2">
          {data.tradeoff?.length > 0 && <TradeoffChart rows={data.tradeoff} />}
          <UtilisationChart kpis={data.kpis} />
        </div>
      )}

      {data.tradeoff?.length > 0 && (
        <Section title="Carbon trade-off">
          <div className="overflow-hidden rounded-[20px] border border-st-secondary bg-white">
            <div className="no-scrollbar overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-st-secondary bg-sf-secondary/40">
                  <tr>
                    {[
                      "Carbon cut",
                      "Cost",
                      "Extra cost",
                      "Carbon t",
                      "Late",
                      "Unmet",
                      "Per tonne saved",
                    ].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-2.5 text-left text-label font-medium tracking-[0.08em] whitespace-nowrap text-tx-tertiary uppercase"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-st-secondary">
                  {data.tradeoff.map((r) => (
                    <tr key={r.carbon_cut_pct} className={cn(!r.feasible && "text-tx-tertiary")}>
                      <td className="px-4 py-3 text-caption font-medium">{r.carbon_cut_pct}%</td>
                      <td className="px-4 py-3 text-caption tabular">
                        {Math.round(r.cost).toLocaleString("en-US")}
                      </td>
                      <td className="px-4 py-3 text-caption tabular">
                        {Math.round(r.extra_cost).toLocaleString("en-US")} (
                        {fmtPct(r.extra_cost_pct)}%)
                      </td>
                      <td className="px-4 py-3 text-caption tabular">{r.carbon_t.toFixed(1)}</td>
                      <td className="px-4 py-3 text-caption tabular">{r.late_orders}</td>
                      <td className="px-4 py-3 text-caption tabular">
                        {r.unmet_orders > 0 ? (
                          <span className="text-red-500">{r.unmet_orders} dropped</span>
                        ) : (
                          0
                        )}
                      </td>
                      <td className="px-4 py-3 text-caption tabular">
                        {r.cost_per_tonne_saved == null
                          ? "—"
                          : Math.round(r.cost_per_tonne_saved).toLocaleString("en-US")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Section>
      )}

      {data.capacity_grid && data.capacity_grid.length > 0 && (
        <CapacityHeatmap cells={data.capacity_grid} />
      )}

      {planned && (
        <Section title="Allocation">
          <AllocationTable data={data} />
        </Section>
      )}

      <Section title="Assumptions and limits">
        <SoftAccordion
          items={[
            {
              id: "a",
              title: "Assumptions",
              body: (
                <ul className="list-disc space-y-1.5 pl-5">
                  {data.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              ),
            },
            {
              id: "l",
              title: "Limitations",
              body: (
                <ul className="list-disc space-y-1.5 pl-5">
                  {data.limitations.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              ),
            },
            {
              id: "j",
              title: "Raw JSON",
              body: (
                <pre className="max-h-96 overflow-auto rounded-xl border border-st bg-[#fafafa] p-4 font-mono text-[12px] leading-relaxed text-tx">
                  {JSON.stringify(data, null, 2)}
                </pre>
              ),
            },
          ]}
        />
      </Section>
    </div>
  );
}

export default function Ask() {
  const [params, setParams] = useSearchParams();
  const runParam = params.get("run");
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [weights, setWeights] = useState<Weights | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [running, setRunning] = useState(false);
  const [asked, setAsked] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepState[]>(STEPS.map(() => ({ status: "idle", count: 0 })));
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  const stored = useQuery({
    queryKey: ["run", runParam],
    queryFn: () => api.run(runParam!),
    enabled: !!runParam && !running,
  });
  useEffect(() => {
    if (stored.data && runParam && !running) {
      setResult(stored.data);
      setAsked(stored.data.request ?? null);
    }
  }, [stored.data, runParam, running]);

  const run = async (request: string) => {
    const trimmed = request.trim();
    if (!trimmed || running) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setRunning(true);
    setAsked(trimmed);
    setResult(null);
    setError(null);
    setSteps(STEPS.map((_, i) => ({ status: i === 0 ? "running" : "idle", count: 0 })));
    const mark = (event: StepEvent, status: "running" | "done") =>
      setSteps((prev) => {
        const next = [...prev];
        const i = stepIndex(event);
        const cur = next[i];
        next[i] = {
          status,
          ms: status === "done" ? event.ms : cur.ms,
          count: status === "running" ? cur.count + 1 : Math.max(cur.count, 1),
        };
        // The backend may only send completions: show the following step as running.
        if (status === "done" && i + 1 < next.length && next[i + 1].status === "idle" && i < 5) {
          next[i + 1] = { ...next[i + 1], status: "running" };
        }
        // A rewrite loops back to "write": clear a stale "check numbers" running state.
        if (status === "done" && i === 5) {
          for (let k = 0; k < 5; k++)
            if (next[k].status === "running") next[k] = { ...next[k], status: "done" };
        }
        return next;
      });
    try {
      const response = await api.analyzeStream(
        { request: trimmed, weights, scenario },
        { onStepStarted: (e) => mark(e, "running"), onStep: (e) => mark(e, "done") },
        abort.current.signal,
      );
      setResult({ ...response, request: response.request ?? trimmed });
      setParams({ run: response.run_id }, { replace: true });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    } catch (e) {
      const message = e instanceof Error ? e.message : "The run failed";
      setError(message);
      toast.error(message);
    } finally {
      setRunning(false);
    }
  };

  const empty = !asked && !result;

  return (
    <div className="relative mx-auto flex max-w-[1180px] flex-col gap-10">
      {/* Faint sunrise behind the empty state, fading once there is a result. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -top-40 left-1/2 h-[420px] w-[900px] -translate-x-1/2 rounded-full opacity-60 blur-[90px] transition-opacity duration-700",
          !empty && "opacity-0",
        )}
        style={{
          background:
            "radial-gradient(ellipse at 50% 40%, #ffb05366 0%, #a5bbfc66 40%, transparent 70%)",
        }}
      />
      <div
        className={cn(
          "relative flex flex-col gap-3",
          empty ? "items-center pt-6 text-center md:pt-12" : "",
        )}
      >
        {empty && <Ornament className="text-indigo-300" />}
        <h1 className="font-display text-[28px] font-normal tracking-[-0.02em] text-tx md:text-[32px]">
          {empty ? "What should we plan?" : "Ask"}
        </h1>
        {empty && (
          <p className="max-w-xl text-body text-tx-tertiary">
            Ask in plain English. The solver computes every number; the model only reads your
            request and writes the summary.
          </p>
        )}
      </div>

      {/* Prompt card: the api-tts playground bezel when empty, a slim 6px frame once running. */}
      <div
        className={cn(
          "relative transition-all duration-500",
          empty ? "rounded-[40px] p-3 md:rounded-[56px] md:p-8" : "rounded-[22px] p-1.5",
        )}
        style={{
          background: "linear-gradient(180deg, #a7c0f1 0%, #f2f8eb 100%)",
          boxShadow: "inset 0 0 25px 10px rgba(255,255,255,.5), 0 0 0 3px rgba(0,0,0,.04)",
        }}
      >
        <form
          className={cn(
            "rounded-[18px] border border-st-secondary bg-sf",
            empty ? "p-5 md:p-8" : "p-4",
          )}
          onSubmit={(e) => {
            e.preventDefault();
            run(text);
          }}
        >
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, 2000))}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                run(text);
              }
            }}
            rows={empty ? 3 : 2}
            placeholder="Allocate this week's orders, re-plan a capacity loss, or ask why an order went where it did…"
            aria-label="Planning request"
            className={cn(empty ? "text-xl leading-relaxed md:text-2xl" : "text-lg")}
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <WeightsPopover weights={weights} onChange={setWeights} />
              <ScenarioPopover scenario={scenario} onChange={setScenario} />
              <span className="text-label text-tx-tertiary tabular">{text.length}/2000</span>
            </div>
            <button
              type="submit"
              disabled={!text.trim() || running}
              aria-label="Run"
              className="grid size-12 place-items-center rounded-full bg-ink-app text-white shadow-[inset_0_1px_0_rgba(255,255,255,.18),inset_0_-2px_0_rgba(0,0,0,.35)] transition-[transform,background-color] duration-150 hover:bg-black active:scale-95 disabled:bg-sf-tertiary disabled:text-tx-muted"
            >
              <ArrowUp className="size-5" strokeWidth={2} />
            </button>
          </div>
        </form>
        {empty && (
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                onClick={() => {
                  setText(example);
                  run(example);
                }}
                className="chip border-white/60 bg-white/70 backdrop-blur hover:bg-white"
              >
                {example}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Live run, staged like the voice-agents demo console. */}
      {asked && (running || error) && (
        <div className="dot-grid flex flex-col gap-5 rounded-2xl border border-st-secondary bg-sf-secondary p-5 md:p-7">
          <Stepper states={steps} />
          <div className="flex flex-col gap-3">
            <p className="max-w-[75%] self-end rounded-2xl rounded-br-sm bg-orange-100 px-[18px] py-3.5 text-[15px] leading-snug text-tx shadow-[inset_0_2px_8px_rgba(249,115,22,.18)]">
              {asked}
            </p>
            {running && (
              <p className="inline-flex max-w-[75%] items-center gap-3 self-start rounded-2xl rounded-bl-sm bg-indigo-100 px-[18px] py-3.5 text-[15px] text-tx shadow-[inset_0_2px_8px_rgba(99,102,241,.2)]">
                {steps.find((s) => s.status === "running")
                  ? `${STEPS[steps.findIndex((s) => s.status === "running")].label}…`
                  : "Starting…"}
                <span className="inline-flex gap-1" aria-hidden>
                  {[0, 1, 2].map((d) => (
                    <span
                      key={d}
                      className="size-1.5 animate-typing rounded-full bg-indigo-600"
                      style={{ animationDelay: `${d * 0.15}s` }}
                    />
                  ))}
                </span>
              </p>
            )}
            {error && (
              <p
                className="inline-flex items-center gap-2 self-start rounded-2xl border border-red-300/40 bg-red-50 px-4 py-3 text-[13px] text-red-500"
                role="alert"
              >
                <TriangleAlert className="size-4" /> {error}
              </p>
            )}
          </div>
        </div>
      )}

      <div aria-live="polite">{result && <Report data={result} />}</div>

      {empty && <EmptyHint />}
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      {[
        ["Plan", "Assign every order to a plant and week within capacity, cost and carbon."],
        ["Re-plan", "Drop a capacity event and see exactly which orders move, and what it costs."],
        ["Explain", "Ask why any order went where it did, with the full cost breakdown."],
      ].map(([title, body]) => (
        <div key={title} className="mini-card min-h-0">
          <p className="mini-card__title">{title}</p>
          <p className="mini-card__desc">{body}</p>
        </div>
      ))}
    </div>
  );
}
