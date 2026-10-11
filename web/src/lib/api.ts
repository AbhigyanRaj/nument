// Typed client for the nument API. Everything goes through same-origin /api (Vite proxy in
// dev, nginx in Docker), so the session cookie works without CORS.

import { fixtureFor, fixturesById, runsFixture } from "@/fixtures/sample";
import { readSse } from "@/lib/sse";
import type {
  AnalyzeResponse,
  DataPage,
  Health,
  IngestResult,
  RunSummary,
  Scenario,
  StepEvent,
  Trace,
  ValidationReport,
  Weights,
} from "@/lib/types";

const BASE = "/api";
export const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "true";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET") headers.set("X-Requested-With", "nument");
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join("; ");
  } catch {
    // fall through to the status text
  }
  return response.statusText || `Request failed (${response.status})`;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export interface AnalyzeBody {
  request: string;
  weights: Weights | null;
  scenario: Scenario | null;
}

export interface StreamHandlers {
  onRun?: (runId: string) => void;
  onStepStarted?: (step: StepEvent) => void;
  onStep?: (step: StepEvent) => void;
}

const FIXTURE_STEPS: StepEvent[] = [
  { step: 1, agent: "router", tool: "classify_request" },
  { step: 2, agent: "optimiser", tool: "solve_allocation" },
  { step: 3, agent: "checker", tool: "validate_plan" },
  { step: 4, agent: "scenario", tool: "compare_plans" },
  { step: 5, agent: "writer", tool: "write_summary" },
  { step: 6, agent: "checker", tool: "check_numbers" },
];

export const api = {
  health: () => request<Health>("/health"),
  runs: (limit = 20) =>
    USE_FIXTURES ? Promise.resolve(runsFixture) : request<RunSummary[]>(`/runs?limit=${limit}`),
  run: (id: string) =>
    USE_FIXTURES
      ? Promise.resolve(fixturesById[id] ?? fixturesById["al-demo01"])
      : request<AnalyzeResponse>(`/runs/${encodeURIComponent(id)}`),
  trace: (id: string) => request<Trace>(`/trace/${encodeURIComponent(id)}`),
  validate: () => request<ValidationReport>("/validate"),
  data: (table: string, q = "", limit = 50, offset = 0) =>
    request<DataPage>(
      `/data/${table}?${new URLSearchParams({ q, limit: String(limit), offset: String(offset) })}`,
    ),
  ingest: (file: File, table: string, mode: "replace" | "append") => {
    const form = new FormData();
    form.append("file", file);
    form.append("table", table);
    form.append("mode", mode);
    return request<IngestResult>("/ingest", { method: "POST", body: form });
  },
  me: () =>
    USE_FIXTURES
      ? Promise.resolve({ email: "demo@nument.app" })
      : request<{ email: string }>("/auth/me"),
  login: (email: string, password: string) =>
    request<{ email: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signup: (email: string, password: string) =>
    request<{ email: string }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  analyze: (body: AnalyzeBody) =>
    request<AnalyzeResponse>("/analyze", { method: "POST", body: JSON.stringify(body) }),

  /** Streams the agent's steps, then resolves with the final response. */
  async analyzeStream(
    body: AnalyzeBody,
    handlers: StreamHandlers,
    signal?: AbortSignal,
  ): Promise<AnalyzeResponse> {
    if (USE_FIXTURES) {
      handlers.onRun?.("al-demo");
      for (const step of FIXTURE_STEPS) {
        handlers.onStepStarted?.(step);
        await wait(380);
        handlers.onStep?.({ ...step, ms: 120 + step.step * 90 });
      }
      return fixtureFor(body.request);
    }
    const response = await fetch(`${BASE}/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "nument" },
      body: JSON.stringify(body),
      credentials: "same-origin",
      signal,
    });
    if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
    let runId: string | null = null;
    for await (const message of readSse(response)) {
      const data = JSON.parse(message.data);
      if (message.event === "run") {
        runId = data.run_id;
        handlers.onRun?.(data.run_id);
      } else if (message.event === "step_started") handlers.onStepStarted?.(data);
      else if (message.event === "step") handlers.onStep?.(data);
      else if (message.event === "result") return data as AnalyzeResponse;
      else if (message.event === "error") throw new ApiError(500, data.message ?? "Run failed");
    }
    // The stream dropped before the result: the run is still saved, so fetch it.
    if (runId) return api.run(runId);
    throw new ApiError(502, "The planning stream ended before a result arrived");
  },
};
