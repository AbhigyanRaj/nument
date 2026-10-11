import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, UploadCloud } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { TableShell, td, th } from "@/components/app/result";
import { Button } from "@/components/ui/button";
import { Segmented, Select } from "@/components/ui/controls";
import { api } from "@/lib/api";
import type { IngestResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABLES = ["orders", "plants", "transport_duties", "capacity_events"];

export default function Data() {
  const queryClient = useQueryClient();
  const [table, setTable] = useState("capacity_events");
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [browse, setBrowse] = useState("orders");
  const [q, setQ] = useState("");
  const validation = useQuery({ queryKey: ["validate"], queryFn: api.validate });
  const page = useQuery({
    queryKey: ["data", browse, q],
    queryFn: () => api.data(browse, q, 50, 0),
  });

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.ingest(file, table, mode);
      setResult(r);
      toast.success(`${r.rows_loaded} rows loaded into ${r.table}`);
      queryClient.invalidateQueries();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const report = result?.validation ?? validation.data;

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-10">
      <div>
        <h1 className="font-display text-[32px] font-normal tracking-[-0.02em]">Data</h1>
        <p className="mt-1 text-body text-tx-tertiary">
          Load CSVs, check them, and browse what the planner sees.
        </p>
      </div>
      <div className="grid gap-2 lg:grid-cols-[1fr_1fr]">
        <div className="flex flex-col gap-5 rounded-card border border-st-secondary bg-white p-6">
          <p className="text-xl font-medium">Upload a CSV</p>
          <div className="flex flex-wrap gap-3">
            <Select
              label="Table"
              value={table}
              onValueChange={setTable}
              options={TABLES.map((t) => ({ value: t, label: t }))}
            />
            <Segmented
              label="Mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: "replace", label: "Replace" },
                { value: "append", label: "Append" },
              ]}
            />
          </div>
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              setFile(e.dataTransfer.files[0] ?? null);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed border-st bg-sf p-8 text-center transition-all duration-200",
              drag && "border-indigo-200 shadow-inset-glow-indigo",
            )}
          >
            <UploadCloud className="size-6 text-indigo-600" strokeWidth={1.5} />
            <span className="text-caption text-tx">
              {file ? file.name : "Drop a CSV here or choose a file"}
            </span>
            <span className="text-label text-tx-tertiary">UTF-8, up to 5 MB</span>
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <Button variant="app" disabled={!file || busy} onClick={upload} className="self-start">
            {busy ? "Loading…" : "Load file"}
          </Button>
          {result && (
            <div className="rounded-xl bg-sf-secondary p-4 text-caption">
              <p>
                <span className="font-medium">{result.status}</span>: {result.rows_loaded} loaded,{" "}
                {result.rows_rejected} rejected
                {result.ignored_columns.length > 0 &&
                  `; ignored ${result.ignored_columns.join(", ")}`}
              </p>
              {result.rejects.map((r) => (
                <p key={r.row} className="mt-1 text-tx-tertiary">
                  Row {r.row}: {r.reason}
                </p>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-3 rounded-card border border-st-secondary bg-white p-6">
          <div className="flex items-center justify-between">
            <p className="text-xl font-medium">Dataset checks</p>
            {report && (
              <span className="text-caption text-tx-tertiary">
                planning start {report.planning_start}
              </span>
            )}
          </div>
          {report?.checks.map((c) => (
            <div
              key={c.id}
              className="flex gap-3 border-b border-st-secondary py-2.5 last:border-0"
            >
              {c.ok ? (
                <CircleCheck className="mt-0.5 size-4 shrink-0 text-green-700" />
              ) : (
                <CircleX className="mt-0.5 size-4 shrink-0 text-red-500" />
              )}
              <div>
                <p className="text-caption font-medium">
                  {c.id} · {c.name}
                </p>
                <p className="text-[13px] text-tx-tertiary">{c.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Segmented
            label="Table"
            value={browse}
            onChange={setBrowse}
            options={TABLES.map((t) => ({ value: t, label: t.replace("_", " ") }))}
          />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search"
            aria-label="Search rows"
            className="h-10 w-56 rounded-2xl border border-st bg-white px-4 text-caption outline-none focus:border-indigo-300 focus:shadow-focus"
          />
        </div>
        <TableShell>
          <table className="w-full">
            <thead className="border-b border-st-secondary bg-sf-secondary/40">
              <tr>
                {page.data?.columns.map((c) => (
                  <th key={c} className={th}>
                    {c.replaceAll("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-st-secondary">
              {page.data?.rows.map((row, i) => (
                <tr key={i} className="hover:bg-sf-secondary/60">
                  {page.data!.columns.map((c) => (
                    <td key={c} className={cn(td, "tabular")}>
                      {row[c] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </TableShell>
        {page.data && <p className="text-label text-tx-tertiary">{page.data.total} rows</p>}
      </div>
    </div>
  );
}
