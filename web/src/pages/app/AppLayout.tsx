// The signed-in app frame: sidebar with New request and recent runs, top bar,
// and the redirect to login when signed out.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { House, Layers, ListChecks, LogOut, Menu, MessageSquareText, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";

import { ANSWER_META } from "@/components/app/result";
import { Wordmark } from "@/components/brand/marks";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/app/ask", label: "Ask", icon: MessageSquareText },
  { to: "/app/data", label: "Data", icon: Layers },
  { to: "/app/trace", label: "Trace", icon: ListChecks },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.runs(12) });
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col gap-8 px-4 py-5">
      {/* The logo keeps you inside the app; the public site is one click away below. */}
      <Link to="/app/ask" className="px-2" onClick={onNavigate} aria-label="nument planner">
        <Wordmark />
      </Link>
      <button
        className="btn btn--ink w-full"
        onClick={() => {
          navigate("/app/ask", { state: { fresh: Date.now() } });
          onNavigate?.();
        }}
      >
        <span className="btn__glow" />
        <span>
          <Plus className="size-4" strokeWidth={2} /> New request
        </span>
      </button>
      <nav className="flex flex-col gap-0.5" aria-label="App">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex h-[34px] items-center gap-2.5 rounded-lg px-2 text-caption transition-colors duration-150",
                isActive
                  ? "bg-sf-tertiary text-tx"
                  : "text-tx-tertiary hover:bg-sf-secondary hover:text-tx",
              )
            }
          >
            <Icon className="size-4" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="flex min-h-0 flex-1 flex-col gap-2">
        <p className="px-2 text-label font-medium tracking-[0.08em] text-tx-tertiary uppercase">
          Recent runs
        </p>
        <div className="no-scrollbar flex flex-col gap-1 overflow-y-auto">
          {(runs.data ?? []).map((run) => (
            <button
              key={run.run_id}
              onClick={() => {
                navigate(`/app/ask?run=${run.run_id}`);
                onNavigate?.();
              }}
              className="group flex items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-[background-color,transform] duration-200 hover:-translate-y-px hover:bg-sf-secondary"
            >
              <span
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  ANSWER_META[run.answer_type]?.dot,
                )}
              />
              <span className="min-w-0">
                <span className="line-clamp-2 text-caption leading-snug text-tx group-hover:text-indigo-800">
                  {run.request}
                </span>
                <span className="font-mono text-[11px] text-tx-tertiary">{run.run_id}</span>
              </span>
            </button>
          ))}
          {runs.data?.length === 0 && (
            <p className="px-2 text-caption text-tx-tertiary">No runs yet.</p>
          )}
        </div>
      </div>
      <Link
        to="/"
        onClick={onNavigate}
        className="flex h-[34px] items-center gap-2.5 rounded-lg px-2 text-caption text-tx-tertiary transition-colors duration-150 hover:bg-sf-secondary hover:text-tx"
      >
        <House className="size-4" strokeWidth={1.75} /> nument home
      </Link>
    </div>
  );
}

function HealthPill() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 });
  const h = health.data;
  const ok = h?.status === "ok";
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-st-secondary bg-white px-3 py-1.5 text-label text-tx-tertiary">
      <span
        className={cn(
          "size-2 rounded-full",
          health.isError ? "bg-red-400" : ok ? "bg-green-600" : "bg-yellow-600",
        )}
      />
      {health.isError
        ? "API offline"
        : h
          ? `API ok · data ${h.data_store} · LLM ${h.llm}${h.model ? ` (${h.model})` : ""}`
          : "Checking"}
    </span>
  );
}

export default function AppLayout() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  const location = useLocation();
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(false);
  const queryClient = useQueryClient();

  if (me.isError)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );

  return (
    <div className="min-h-dvh bg-sf">
      <aside className="fixed inset-y-0 left-0 hidden w-[272px] border-r border-st-secondary bg-white lg:block">
        <Sidebar />
      </aside>
      {drawer && (
        <div
          className="fixed inset-0 z-50 bg-black/20 backdrop-blur-[6px] lg:hidden"
          onClick={() => setDrawer(false)}
        >
          <aside
            className="h-full w-[280px] animate-[slideDown_.3s_ease-out] bg-white"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              aria-label="Close menu"
              className="absolute top-4 left-[236px] grid size-9 place-items-center"
              onClick={() => setDrawer(false)}
            >
              <X className="size-5" />
            </button>
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}
      <div className="lg:pl-[272px]">
        <header className="sticky top-0 z-40 flex h-[60px] items-center justify-between gap-3 border-b border-st-secondary bg-white/90 px-4 backdrop-blur md:px-8">
          <button
            className="grid size-9 place-items-center lg:hidden"
            aria-label="Open menu"
            onClick={() => setDrawer(true)}
          >
            <Menu className="size-5" strokeWidth={1.5} />
          </button>
          <HealthPill />
          <div className="flex items-center gap-2">
            <span className="hidden text-caption text-tx-tertiary md:inline">{me.data?.email}</span>
            <button
              className="btn btn--ghost"
              onClick={async () => {
                await api.logout().catch(() => undefined);
                queryClient.removeQueries({ queryKey: ["me"] });
                navigate("/login");
              }}
            >
              <span>
                <LogOut className="size-4" strokeWidth={1.75} /> Log out
              </span>
            </button>
          </div>
        </header>
        <main className="px-4 py-8 md:px-8 md:py-10">
          {/* "New request" remounts the page so the Ask workspace starts clean. */}
          <div key={(location.state as { fresh?: number } | null)?.fresh ?? "page"}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
