// A clean, printable page for the leadership brief.

import { useQuery } from "@tanstack/react-query";
import { Copy, Printer } from "lucide-react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { Wordmark } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const HEADINGS = ["Situation", "Plan", "Trade-off", "Risks", "Decision needed"];

/** Blog-post article template (680px column) with a print stylesheet. */
export default function Brief() {
  const { runId } = useParams();
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId!),
    enabled: !!runId,
  });
  const text = run.data?.brief ?? run.data?.summary ?? "";
  const blocks = text.split("\n").filter(Boolean);

  return (
    <div className="min-h-dvh bg-sf px-5 py-16 md:py-24 print:py-0">
      <article className="mx-auto max-w-[680px]">
        <div className="mb-6 flex items-center justify-between text-caption text-tx-tertiary print:hidden">
          <Link to={`/app/ask?run=${runId}`} className="hover:text-tx">
            ← Back to the run
          </Link>
          <Wordmark className="text-lg" />
        </div>
        <h1 className="font-display text-[36px] leading-tight font-normal tracking-[-0.02em] md:text-[42px]">
          Leadership brief
        </h1>
        <div className="mt-4 mb-6 flex flex-wrap items-center justify-between gap-4">
          <span className="rounded-full bg-sf-secondary px-3 py-1 text-label text-tx-tertiary">
            {runId}
          </span>
          <div className="flex gap-2 print:hidden">
            <Button
              variant="soft"
              size="sm"
              onClick={() =>
                navigator.clipboard.writeText(text).then(() => toast.success("Copied"))
              }
            >
              <Copy className="size-4" strokeWidth={1.75} /> Copy
            </Button>
            <Button variant="app" size="sm" onClick={() => window.print()}>
              <Printer className="size-4" strokeWidth={1.75} /> Print or save PDF
            </Button>
          </div>
        </div>
        <hr className="mb-8 border-st" />
        <div className="flex flex-col gap-5 text-base leading-[1.65] text-tx">
          {blocks.map((block, i) =>
            HEADINGS.includes(block.replace(/[#:*]/g, "").trim()) ? (
              <h2 key={i} className="mt-6 text-2xl font-semibold tracking-[-0.01em]">
                {block.replace(/[#:*]/g, "").trim()}
              </h2>
            ) : (
              <p key={i}>{block}</p>
            ),
          )}
        </div>
        {run.data && (
          <p className="mt-10 border-t border-st pt-6 text-caption text-tx-tertiary">
            {run.data.meta.number_check.matched} of {run.data.meta.number_check.checked} figures
            checked against computed facts.
          </p>
        )}
      </article>
    </div>
  );
}
