// Charts for an answer: cost vs carbon, plant capacity used, and the weekly heatmap.

import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
  ZAxis,
  LabelList,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { useMemo, useState, type ReactNode } from "react";

import { Segmented } from "@/components/ui/controls";
import { fmtMoney, fmtPct, fmtTonnes } from "@/lib/format";
import type { CapacityCell, Kpis, TradeoffRow } from "@/lib/types";
import { cn, prefersReducedMotion } from "@/lib/utils";

// Plant identity colours, validated with the dataviz palette checks (CVD-safe, >= 3:1).
export const PLANT_COLORS: Record<string, string> = { A: "#3333cc", B: "#e96c2f", C: "#496d21" };
const GRID = "#f0f0f0";
const AXIS = { fontSize: 12, fill: "#666666" };

/** Passe-partout figure card (startup-program.md §2.4): 4px inset, display title. */
export function FigureCard({
  title,
  caption,
  action,
  children,
  className,
}: {
  title: string;
  caption?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <figure className={cn("rounded-card border border-st-secondary bg-white p-1", className)}>
      <div className="flex h-full flex-col rounded-xl bg-white px-5 pt-5 pb-4">
        <figcaption className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-display text-xl font-normal text-tx">{title}</p>
            {caption && <p className="mt-0.5 text-[13px] text-tx-tertiary">{caption}</p>}
          </div>
          {action}
        </figcaption>
        {children}
      </div>
    </figure>
  );
}

function TipBox({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-st-secondary bg-white px-3 py-2 text-[13px] text-tx shadow-[0_8px_24px_-6px_#0000001f]">
      {children}
    </div>
  );
}

/** Cost vs carbon, one dot per carbon-cut point; the current plan is the indigo dot. */
export function TradeoffChart({
  rows,
  currentCut = 0,
}: {
  rows: TradeoffRow[];
  currentCut?: number;
}) {
  const data = rows.map((r) => ({ ...r, current: r.carbon_cut_pct === currentCut }));
  return (
    <FigureCard title="Cost vs carbon" caption="One point per carbon cut; label = late orders">
      <div
        className="h-64"
        role="img"
        aria-label="Scatter of plan cost against carbon for each carbon cut"
      >
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 16, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              type="number"
              dataKey="carbon_t"
              name="Carbon"
              unit=" t"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              domain={["dataMin - 5", "dataMax + 5"]}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <YAxis
              type="number"
              dataKey="cost"
              name="Cost"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={72}
              domain={["dataMin - 5000", "dataMax + 5000"]}
              tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
            />
            <ZAxis range={[90, 90]} />
            <ChartTooltip
              cursor={{ stroke: GRID }}
              content={({ payload }) => {
                const p = payload?.[0]?.payload as (TradeoffRow & { current: boolean }) | undefined;
                if (!p) return null;
                return (
                  <TipBox>
                    <p className="font-medium">{p.carbon_cut_pct}% carbon cut</p>
                    <p className="text-tx-tertiary">
                      Cost {fmtMoney(p.cost)} · {fmtTonnes(p.carbon_t)} t · {p.late_orders} late
                    </p>
                    {!p.feasible && <p className="text-red-500">Drops {p.unmet_orders} orders</p>}
                  </TipBox>
                );
              }}
            />
            <Scatter data={data} isAnimationActive={!prefersReducedMotion()}>
              {data.map((d) => (
                <Cell
                  key={d.carbon_cut_pct}
                  fill={d.current ? "#3333cc" : d.feasible ? "#a7c0f1" : "#fddcce"}
                  stroke="#fcfcfc"
                  strokeWidth={2}
                />
              ))}
              <LabelList
                dataKey="late_orders"
                position="top"
                style={{ fontSize: 11, fill: "#3d3d3d" }}
              />
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <Legend
        items={[
          ["#3333cc", "This plan"],
          ["#a7c0f1", "Feasible cut"],
          ["#fddcce", "Cut drops orders"],
        ]}
      />
      <table className="sr-only">
        <caption>Trade-off table</caption>
        <thead>
          <tr>
            <th>Cut %</th>
            <th>Cost</th>
            <th>Carbon t</th>
            <th>Late</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.carbon_cut_pct}>
              <td>{r.carbon_cut_pct}</td>
              <td>{fmtMoney(r.cost)}</td>
              <td>{fmtTonnes(r.carbon_t)}</td>
              <td>{r.late_orders}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </FigureCard>
  );
}

export function Legend({ items }: { items: [string, string][] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1">
      {items.map(([color, label]) => (
        <span key={label} className="inline-flex items-center gap-2 text-label text-tx-tertiary">
          <span className="size-3 rounded-[3px]" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/** Utilisation per plant, with a metric switch (share of orders vs capacity used). */
export function UtilisationChart({ kpis }: { kpis: Kpis }) {
  const [metric, setMetric] = useState<"util" | "share">("util");
  const source = metric === "util" ? kpis.plant_utilisation : kpis.plant_share;
  const data = Object.entries(source).map(([plant, value]) => ({ plant, value: value * 100 }));
  return (
    <FigureCard
      title={metric === "util" ? "Capacity used" : "Share of orders"}
      caption="Per plant, over the planning horizon"
      action={
        <Segmented
          label="Metric"
          size="sm"
          tone="light"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "util", label: "Capacity" },
            { value: "share", label: "Orders" },
          ]}
        />
      }
    >
      <div key={metric} className="h-64 animate-[fade-in_.4s_ease-out]">
        <ResponsiveContainer>
          <BarChart
            data={data}
            margin={{ top: 20, right: 8, bottom: 0, left: 0 }}
            barCategoryGap="28%"
          >
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis
              dataKey="plant"
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              tickFormatter={(p) => `Plant ${p}`}
            />
            <YAxis
              tick={AXIS}
              axisLine={false}
              tickLine={false}
              width={40}
              unit="%"
              domain={[0, 100]}
            />
            <ChartTooltip
              cursor={{ fill: "#f5f5f5" }}
              content={({ payload }) => {
                const p = payload?.[0]?.payload as { plant: string; value: number } | undefined;
                return p ? (
                  <TipBox>
                    Plant {p.plant}: {fmtPct(p.value)}%
                  </TipBox>
                ) : null;
              }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={!prefersReducedMotion()}>
              {data.map((d) => (
                <Cell key={d.plant} fill={PLANT_COLORS[d.plant] ?? "#556adc"} />
              ))}
              <LabelList
                dataKey="value"
                position="top"
                formatter={(v: unknown) => `${Number(v).toFixed(0)}%`}
                style={{ fontSize: 12, fill: "#3d3d3d" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </FigureCard>
  );
}

// Sequential indigo ramp for utilisation (light = idle, dark = full); red ring when over 95%.
const RAMP = ["#fafcff", "#e8effc", "#d2dff9", "#a7c0f1", "#81a0e9", "#556adc", "#3333cc"];

function rampColor(share: number) {
  return RAMP[Math.min(RAMP.length - 1, Math.floor(share * RAMP.length))];
}

/** Plant × week capacity use, optionally split by product. */
export function CapacityHeatmap({ cells }: { cells: CapacityCell[] }) {
  const [byProduct, setByProduct] = useState(false);
  const weeks = useMemo(
    () => [...new Set(cells.map((c) => c.week))].sort((a, b) => a - b),
    [cells],
  );
  const weekStart = useMemo(() => new Map(cells.map((c) => [c.week, c.week_start])), [cells]);
  const rows = useMemo(() => {
    const groups = new Map<
      string,
      Map<number, { used: number; effective: number; base: number }>
    >();
    for (const c of cells) {
      const key = byProduct ? `${c.plant} · ${c.product}` : `Plant ${c.plant}`;
      const row = groups.get(key) ?? new Map();
      const cur = row.get(c.week) ?? { used: 0, effective: 0, base: 0 };
      row.set(c.week, {
        used: cur.used + c.used,
        effective: cur.effective + c.effective,
        base: cur.base + c.base,
      });
      groups.set(key, row);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [cells, byProduct]);

  return (
    <FigureCard
      title="Capacity by week"
      caption="Units used of effective capacity; striped cells lost capacity to events"
      action={
        <Segmented
          label="Grouping"
          size="sm"
          tone="light"
          value={byProduct ? "product" : "plant"}
          onChange={(v) => setByProduct(v === "product")}
          options={[
            { value: "plant", label: "By plant" },
            { value: "product", label: "By product" },
          ]}
        />
      }
    >
      <div className="no-scrollbar overflow-x-auto">
        <table className="w-full min-w-[520px] border-separate border-spacing-1 text-label">
          <thead>
            <tr>
              <th className="w-24 text-left font-medium text-tx-tertiary uppercase">&nbsp;</th>
              {weeks.map((w) => (
                <th
                  key={w}
                  className="pb-1 text-left font-medium tracking-[0.08em] text-tx-tertiary uppercase"
                >
                  W{w} <span className="font-normal normal-case">{weekStart.get(w)?.slice(5)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, byWeek]) => (
              <tr key={label}>
                <th
                  scope="row"
                  className="pr-2 text-left text-caption font-normal whitespace-nowrap text-tx-secondary"
                >
                  {label}
                </th>
                {weeks.map((w) => {
                  const c = byWeek.get(w) ?? { used: 0, effective: 0, base: 0 };
                  const share = c.effective ? c.used / c.effective : 0;
                  const lost = c.effective < c.base;
                  return (
                    <td
                      key={w}
                      title={`${label}, week ${w}: ${c.used.toLocaleString()} of ${c.effective.toLocaleString()} units${lost ? ` (base ${c.base.toLocaleString()})` : ""}`}
                      className={cn(
                        "h-10 rounded-lg px-2 align-middle tabular transition-transform hover:scale-[1.04]",
                        share > 0.95 && "ring-2 ring-red-300 ring-inset",
                      )}
                      style={{
                        background: lost
                          ? `repeating-linear-gradient(45deg, ${rampColor(share)} 0 6px, #ffffff99 6px 8px)`
                          : rampColor(share),
                        color: share > 0.6 ? "#ffffff" : "#3d3d3d",
                      }}
                    >
                      {Math.round(share * 100)}%
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center gap-2 text-label text-tx-tertiary">
        0%
        <span className="flex h-2 w-40 overflow-hidden rounded-full">
          {RAMP.map((c) => (
            <span key={c} className="flex-1" style={{ background: c }} />
          ))}
        </span>
        100%
      </div>
    </FigureCard>
  );
}
