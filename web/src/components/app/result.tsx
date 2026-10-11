// The pieces of an answer: badges, verified summary, KPI tiles, checks,
// recommendations and the allocation, moved and explanation tables.

import {
  BadgeCheck,
  CircleAlert,
  CircleCheck,
  CircleX,
  Download,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Fragment, useMemo, useState, type ReactNode } from "react";

import { Badge } from "@/components/brand/marks";
import { Segmented, Tooltip } from "@/components/ui/controls";
import { useCountUp } from "@/hooks/motion";
import { fmtDate, fmtInt, fmtMoney, fmtPct, fmtSigned, fmtTonnes, toCsv } from "@/lib/format";
import type {
  AllocationRow,
  AnalyzeResponse,
  AnswerType,
  Comparison,
  Explanation,
  NumberMatch,
  Recommendation,
  Validator,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export const ANSWER_META: Record<
  AnswerType,
  { label: string; tone: "green" | "orange" | "indigo" | "grey"; dot: string }
> = {
  allocation: { label: "Allocation", tone: "green", dot: "bg-green-600" },
  scenario: { label: "Scenario", tone: "green", dot: "bg-green-600" },
  brief: { label: "Brief", tone: "green", dot: "bg-green-600" },
  infeasible: { label: "Infeasible", tone: "orange", dot: "bg-orange-700" },
  clarification_needed: { label: "Needs detail", tone: "indigo", dot: "bg-indigo-600" },
  refused: { label: "Refused", tone: "grey", dot: "bg-grey-500" },
};

export function AnswerBadge({ type }: { type: AnswerType }) {
  const meta = ANSWER_META[type];
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

function normaliseNumber(token: string): string {
  const plain = token.replace(/,/g, "").replace(/\.$/, "");
  const n = Number(plain);
  return Number.isFinite(n) ? String(n) : plain;
}

/** Summary text with every number-checked figure underlined; the tooltip names the fact. */
export function CheckedSummary({ text, matches }: { text: string; matches?: NumberMatch[] }) {
  // Split on whole number tokens the same way the backend's number check extracts them
  // (thousands commas removed), so "1,368,270" is one figure, never pieces of one.
  const parts = useMemo(() => text.split(/(\d[\d,]*(?:\.\d+)?)/g), [text]);
  const byToken = new Map((matches ?? []).map((m) => [normaliseNumber(m.token), m.facts] as const));
  return (
    <p className="text-body leading-[1.65] whitespace-pre-line text-tx">
      {parts.map((part, i) => {
        const facts = i % 2 === 1 ? byToken.get(normaliseNumber(part)) : undefined;
        if (!facts) return <Fragment key={i}>{part}</Fragment>;
        return (
          <Tooltip
            key={i}
            content={
              <span>
                <span className="font-medium">Checked</span> against {facts.join(", ")}
              </span>
            }
          >
            <span
              tabIndex={0}
              className="cursor-help underline decoration-indigo-400 decoration-dotted decoration-2 underline-offset-4"
            >
              {part}
            </span>
          </Tooltip>
        );
      })}
    </p>
  );
}

function Kpi({
  label,
  value,
  format,
  unit,
  delta,
}: {
  label: string;
  value: number;
  format: (n: number) => string;
  unit?: string;
  delta?: ReactNode;
}) {
  const { ref, value: shown } = useCountUp(value);
  return (
    <div className="flex min-h-36 flex-col justify-between rounded-xl border border-st-secondary bg-white p-5">
      <p className="text-caption text-tx-tertiary">{label}</p>
      <div>
        <p
          ref={ref as React.Ref<HTMLParagraphElement>}
          className="text-[40px] leading-none font-medium tracking-[-0.03em] text-tx tabular md:text-5xl"
          aria-hidden
        >
          {format(shown)}
          {unit && <span className="ml-1 text-xl text-tx-tertiary">{unit}</span>}
        </p>
        <p className="sr-only">
          {label}: {format(value)} {unit}
        </p>
        {delta && <div className="mt-3">{delta}</div>}
      </div>
    </div>
  );
}

function Delta({
  value,
  format,
  invert,
}: {
  value: number;
  format: (n: number) => string;
  invert?: boolean;
}) {
  if (value === 0) return <Badge tone="grey">no change</Badge>;
  const worse = invert ? value < 0 : value > 0;
  return <Badge tone={worse ? "orange" : "green"}>{fmtSigned(value, format)}</Badge>;
}

/** KPI tiles as a mosaic with 8px gaps (DESIGN §5); scenario answers show deltas. */
export function KpiMosaic({ data }: { data: AnalyzeResponse }) {
  const { kpis, comparison } = data;
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      <Kpi
        label="Landed cost"
        value={kpis.total_cost}
        format={fmtMoney}
        delta={comparison && <Delta value={comparison.extra_cost} format={fmtMoney} />}
      />
      <Kpi
        label="Carbon"
        value={kpis.total_carbon_t}
        format={fmtTonnes}
        unit="t CO2e"
        delta={comparison && <Delta value={comparison.extra_carbon_t} format={fmtTonnes} />}
      />
      <Kpi
        label="Late orders"
        value={kpis.late_orders}
        format={fmtInt}
        unit={`of ${kpis.orders_total}`}
        delta={comparison && <Delta value={comparison.late_orders_change} format={fmtInt} />}
      />
      <Kpi
        label="Unmet orders"
        value={kpis.unmet_orders}
        format={fmtInt}
        delta={comparison && <Delta value={comparison.unmet_change} format={fmtInt} />}
      />
    </div>
  );
}

const CHECKS: [keyof Validator, string][] = [
  ["capacity_ok", "Capacity"],
  ["eligibility_ok", "Eligibility"],
  ["delivery_ok", "Delivery flags"],
  ["complete_ok", "Every order"],
  ["numbers_ok", "Numbers"],
];

export function ValidatorBadges({ validator }: { validator: Validator }) {
  return (
    <div className="flex flex-wrap gap-2">
      {CHECKS.map(([key, label]) => {
        const ok = validator[key];
        return (
          <Badge
            key={key}
            tone={ok ? "green" : "red"}
            icon={
              ok ? (
                <CircleCheck className="size-4" strokeWidth={2} />
              ) : (
                <CircleX className="size-4" strokeWidth={2} />
              )
            }
          >
            {label} {ok ? "passed" : "failed"}
          </Badge>
        );
      })}
    </div>
  );
}

export function Recommendations({ items }: { items: Recommendation[] }) {
  if (!items.length) return null;
  return (
    <div className="grid gap-2 md:grid-cols-2">
      {items.map((r) => (
        <div
          key={r.action}
          className="flex flex-col gap-3 rounded-xl border border-st-secondary bg-white p-5"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-lg leading-snug font-medium text-tx">{r.action}</p>
            {r.requires_approval && (
              <span className="shrink-0 rounded-full bg-indigo-100 px-2.5 py-1 text-label font-medium text-indigo-800">
                Needs approval
              </span>
            )}
          </div>
          <p className="text-caption leading-relaxed text-tx-tertiary">{r.rationale}</p>
          <div className="mt-auto flex flex-wrap items-center gap-2 text-label text-tx-tertiary">
            <ShieldCheck className="size-4 text-indigo-600" strokeWidth={1.75} />
            {r.confidence} confidence
            {r.evidence_refs.map((ref) => (
              <span
                key={ref}
                className="rounded-full border border-st bg-sf-secondary px-2 py-0.5 font-mono text-[11px]"
              >
                {ref}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Tables (pricing.md rate-table style) ---------- */

export function TableShell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[20px] border border-st-secondary bg-white",
        className,
      )}
    >
      <div className="no-scrollbar overflow-x-auto">{children}</div>
    </div>
  );
}

export const th =
  "px-4 py-2.5 text-left text-label font-medium tracking-[0.08em] whitespace-nowrap text-tx-tertiary uppercase";
export const td = "px-4 py-3 text-caption whitespace-nowrap text-tx";

type Filter = "all" | "late" | "moved" | "unmet";

export function AllocationTable({ data }: { data: AnalyzeResponse }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const rows = useMemo(() => {
    let out: AllocationRow[] = data.allocation;
    if (filter === "late") out = out.filter((r) => r.days_late > 0);
    if (filter === "moved") out = out.filter((r) => r.moved);
    if (filter === "unmet")
      out = data.unmet_orders.map((id) => ({
        order_id: id,
        plant: null,
        cost: 0,
        carbon_kg: 0,
        arrival: null,
        on_time: false,
        week: null,
        days_late: 0,
        moved: false,
        base_plant: null,
      }));
    const q = query.trim().toLowerCase();
    if (q)
      out = out.filter((r) =>
        [r.order_id, r.plant, r.product, r.destination].some((v) => v?.toLowerCase().includes(q)),
      );
    return out;
  }, [data, filter, query]);

  const download = () => {
    const columns = [
      "order_id",
      "product",
      "qty",
      "destination",
      "due",
      "plant",
      "week",
      "arrival",
      "on_time",
      "days_late",
      "cost",
      "carbon_kg",
      "moved",
      "base_plant",
    ];
    const blob = new Blob(
      [toCsv(data.allocation as unknown as Record<string, unknown>[], columns)],
      { type: "text/csv" },
    );
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `${data.run_id}-allocation.csv`,
    });
    a.click();
    URL.revokeObjectURL(url);
  };

  const counts = {
    late: data.allocation.filter((r) => r.days_late > 0).length,
    moved: data.allocation.filter((r) => r.moved).length,
    unmet: data.unmet_orders.length,
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <Segmented
          label="Filter orders"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `All ${data.allocation.length}` },
            { value: "late", label: `Late ${counts.late}` },
            { value: "moved", label: `Moved ${counts.moved}` },
            { value: "unmet", label: `Unmet ${counts.unmet}` },
          ]}
        />
        <div className="flex items-center gap-2">
          <label className="relative block grow md:w-56">
            <span className="sr-only">Search orders</span>
            <Search className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-tx-tertiary" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search order, plant, place"
              className="h-10 w-full rounded-2xl border border-st bg-white pr-3 pl-10 text-base outline-none placeholder:text-tx-tertiary focus:border-indigo-300 focus:shadow-focus sm:text-caption"
            />
          </label>
          <button onClick={download} className="btn btn--soft btn--sm shrink-0">
            <span>
              <Download className="size-4" strokeWidth={1.75} /> CSV
            </span>
          </button>
        </div>
      </div>
      <TableShell>
        <table className="w-full">
          <thead className="border-b border-st-secondary bg-sf-secondary/40">
            <tr>
              {[
                "Order",
                "Product",
                "Qty",
                "Destination",
                "Due",
                "Plant",
                "Week",
                "Arrives",
                "Cost",
                "CO2e kg",
              ].map((h) => (
                <th key={h} className={th}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-st-secondary">
            {rows.slice(0, showAll ? rows.length : 25).map((r) => (
              <tr key={r.order_id} className="transition-colors hover:bg-sf-secondary/60">
                <td className={cn(td, "font-medium")}>{r.order_id}</td>
                <td className={td}>{r.product ?? "—"}</td>
                <td className={cn(td, "tabular")}>{r.qty ?? "—"}</td>
                <td className={td}>{r.destination ?? "—"}</td>
                <td className={cn(td, "tabular")}>{fmtDate(r.due)}</td>
                <td className={td}>
                  {r.plant ? (
                    <span className="inline-flex items-center gap-2">
                      <span
                        className="size-2 rounded-full"
                        style={{ background: PLANT_DOT[r.plant] }}
                      />
                      {r.plant}
                      {r.moved && r.base_plant && (
                        <span className="text-tx-tertiary">from {r.base_plant}</span>
                      )}
                    </span>
                  ) : (
                    <span className="text-red-500">Unmet</span>
                  )}
                </td>
                <td className={cn(td, "tabular")}>{r.week ?? "—"}</td>
                <td className={cn(td, "tabular")}>
                  {fmtDate(r.arrival)}
                  {r.days_late > 0 && <span className="ml-2 text-orange-900">+{r.days_late}d</span>}
                </td>
                <td className={cn(td, "tabular")}>{r.plant ? fmtMoney(r.cost) : "—"}</td>
                <td className={cn(td, "tabular")}>{r.plant ? fmtInt(r.carbon_kg) : "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-caption text-tx-tertiary">
                  No orders match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </TableShell>
      {rows.length > 25 && (
        <button className="btn btn--soft btn--sm self-center" onClick={() => setShowAll(!showAll)}>
          <span>{showAll ? "Show fewer" : `Show all ${rows.length} orders`}</span>
        </button>
      )}
    </div>
  );
}

const PLANT_DOT: Record<string, string> = { A: "#3333cc", B: "#e96c2f", C: "#496d21" };

export function MovedTable({ comparison }: { comparison: Comparison }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {[
          ["Moved orders", fmtInt(comparison.moved_count)],
          ["Kept their plant", `${fmtPct(comparison.stability_pct)}%`],
          [
            "Extra cost",
            `${fmtSigned(comparison.extra_cost, fmtMoney)} (${fmtPct(comparison.extra_cost_pct)}%)`,
          ],
          ["Extra carbon", `${fmtSigned(comparison.extra_carbon_t, fmtTonnes)} t`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-st-secondary bg-white p-4">
            <p className="text-label text-tx-tertiary">{label}</p>
            <p className="mt-2 text-xl font-medium tracking-[-0.5px] tabular">{value}</p>
          </div>
        ))}
      </div>
      <TableShell>
        <table className="w-full">
          <thead className="border-b border-st-secondary bg-sf-secondary/40">
            <tr>
              {["Order", "From", "To", "Cost change", "CO2e change kg", "Delivery"].map((h) => (
                <th key={h} className={th}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-st-secondary">
            {comparison.moved.map((m) => (
              <tr key={m.order_id} className="hover:bg-sf-secondary/60">
                <td className={cn(td, "font-medium")}>{m.order_id}</td>
                <td className={td}>{m.from_plant ?? "Unmet"}</td>
                <td className={td}>{m.to_plant ?? "Unmet"}</td>
                <td className={cn(td, "tabular")}>{fmtSigned(m.cost_change, fmtMoney)}</td>
                <td className={cn(td, "tabular")}>{fmtSigned(m.carbon_change_kg, fmtInt)}</td>
                <td className={td}>
                  {m.became_late ? (
                    <span className="text-orange-900">Now late</span>
                  ) : (
                    <span className="text-green-700">On time</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

export function ExplainTable({ explanation }: { explanation: Explanation }) {
  if (!explanation.found || !explanation.rows) {
    return <p className="text-caption text-tx-tertiary">That order is not in the loaded data.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <TableShell>
        <table className="w-full">
          <thead className="border-b border-st-secondary bg-sf-secondary/40">
            <tr>
              {[
                "Plant",
                "Week",
                "Production",
                "Energy",
                "Transport",
                "Duty",
                "Landed cost",
                "CO2e kg",
                "Arrives",
                "Capacity left",
              ].map((h) => (
                <th key={h} className={th}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-st-secondary">
            {explanation.rows.map((r) => (
              <tr key={r.plant} className={cn(r.chosen && "bg-indigo-50")}>
                <td className={cn(td, "font-medium")}>
                  <span className="inline-flex items-center gap-2">
                    Plant {r.plant}
                    {r.chosen && (
                      <BadgeCheck
                        className="size-4 text-indigo-700"
                        strokeWidth={2}
                        aria-label="chosen"
                      />
                    )}
                  </span>
                </td>
                {r.eligible ? (
                  <>
                    <td className={cn(td, "tabular")}>{r.week ?? "—"}</td>
                    {[r.production, r.energy, r.transport, r.duty, r.cost].map((v, i) => (
                      <td key={i} className={cn(td, "tabular", i === 4 && "font-medium")}>
                        {v == null ? "—" : fmtMoney(v)}
                      </td>
                    ))}
                    <td className={cn(td, "tabular")}>
                      {r.carbon_kg == null ? "—" : fmtInt(r.carbon_kg)}
                    </td>
                    <td className={cn(td, "tabular")}>
                      {fmtDate(r.arrival)}
                      {r.days_late ? (
                        <span className="ml-2 text-orange-900">+{r.days_late}d</span>
                      ) : null}
                    </td>
                    <td className={cn(td, "tabular")}>{r.capacity_left_in_week ?? "—"}</td>
                  </>
                ) : (
                  <td colSpan={9} className={cn(td, "text-tx-tertiary")}>
                    Cannot make this product or reach this destination
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
      <div className="flex flex-wrap gap-2">
        {(explanation.reason_codes ?? []).map((r) => (
          <Tooltip key={r.code + (r.plant ?? "")} content={r.detail ?? r.code}>
            <span tabIndex={0}>
              <Badge tone="indigo" icon={<CircleAlert className="size-4" strokeWidth={2} />}>
                {r.code.replaceAll("_", " ").toLowerCase()}
              </Badge>
            </span>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
