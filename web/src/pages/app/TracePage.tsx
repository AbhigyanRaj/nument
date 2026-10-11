import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { ANSWER_META, AnswerBadge } from "@/components/app/result";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function TracePage() {
  const { runId } = useParams();
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.runs(20) });
  const trace = useQuery({
    queryKey: ["trace", runId],
    queryFn: () => api.trace(runId!),
    enabled: !!runId,
  });

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-8">
      <div>
        <h1 className="font-display text-[32px] font-normal tracking-[-0.02em]">Trace</h1>
        <p className="mt-1 text-body text-tx-tertiary">
          Every step the agent took for a run, with timings and the number check.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-2.5">
          {(runs.data ?? []).map((run) => (
            <Link
              key={run.run_id}
              to={`/app/trace/${run.run_id}`}
              className={cn(
                "group flex items-center justify-between gap-4 rounded-card border border-st-secondary bg-white p-4 transition-transform duration-200 hover:-translate-y-px",
                run.run_id === runId && "border-indigo-200 bg-indigo-50",
              )}
            >
              <span className="min-w-0">
                <span className="line-clamp-2 text-caption font-medium text-tx group-hover:text-indigo-800">
                  {run.request}
                </span>
                <span className="mt-1 flex items-center gap-2 text-label text-tx-tertiary">
                  <span
                    className={cn("size-1.5 rounded-full", ANSWER_META[run.answer_type]?.dot)}
                  />
                  {run.run_id} · {fmtDateTime(run.created_at)}
                </span>
              </span>
            </Link>
          ))}
        </div>
        <div>
          {!runId && <p className="text-caption text-tx-tertiary">Pick a run to see its steps.</p>}
          {trace.data && (
            <div className="flex flex-col gap-6">
              <div className="flex flex-wrap items-center gap-3">
                <AnswerBadge type={trace.data.answer_type} />
                <p className="text-caption text-tx-secondary">“{trace.data.request}”</p>
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {[
                  ["Latency", `${(trace.data.latency_ms / 1000).toFixed(1)} s`],
                  ["LLM calls", String(trace.data.llm_calls)],
                  ["Tokens", String(trace.data.tokens)],
                  [
                    "Numbers matched",
                    `${trace.data.number_check.matched} of ${trace.data.number_check.checked}`,
                  ],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-st-secondary bg-white p-4">
                    <p className="text-label text-tx-tertiary">{k}</p>
                    <p className="mt-2 text-xl font-medium tabular">{v}</p>
                  </div>
                ))}
              </div>
              <ol className="relative flex flex-col gap-3 border-l border-st pl-6">
                {trace.data.steps.map((step) => (
                  <li
                    key={step.step}
                    className="relative rounded-card border border-st-secondary bg-white p-4"
                  >
                    <span className="absolute top-5 -left-[29px] size-2.5 rounded-full border-2 border-white bg-indigo-600" />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-caption font-medium">
                        {step.step}. {step.agent}{" "}
                        <span className="font-mono text-label text-tx-tertiary">{step.tool}</span>
                      </p>
                      <span className="text-label text-tx-tertiary tabular">{step.ms} ms</span>
                    </div>
                    {step.output != null && (
                      <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-[#fafafa] p-3 font-mono text-[12px] text-tx-secondary">
                        {JSON.stringify(step.output, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
