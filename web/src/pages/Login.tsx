import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, TriangleAlert } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { Wordmark } from "@/components/brand/marks";
import { PixelField } from "@/components/brand/PixelField";
import { Checkbox, Input } from "@/components/ui/controls";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Mode = "login" | "signup";

// One component, two modes (PixelField brief §10).
const COPY: Record<
  Mode,
  { heading: string; cta: string; prompt: string; action: string; next: Mode }
> = {
  login: {
    heading: "Log into your account",
    cta: "Log in",
    prompt: "Don't have an account?",
    action: "Create one",
    next: "signup",
  },
  signup: {
    heading: "Create your account",
    cta: "Create account",
    prompt: "Already have an account?",
    action: "Log in",
    next: "login",
  },
};

/** Unbuilt SSO: the button's own label morphs to "Coming soon" for 1600ms (brief §5). */
function ComingSoon({ label }: { label: string }) {
  const [revealed, setRevealed] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  return (
    <button
      type="button"
      className="btn btn--auth"
      onClick={() => {
        setRevealed(true);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setRevealed(false), 1600);
      }}
    >
      <span className="relative inline-grid overflow-hidden">
        <span
          className={cn(
            "col-start-1 row-start-1 transition-all duration-200 ease-out",
            revealed && "-translate-y-1.5 opacity-0",
          )}
          aria-hidden={revealed}
        >
          {label}
        </span>
        <span
          className={cn(
            "col-start-1 row-start-1 font-medium text-indigo-700 transition-all duration-200 ease-out",
            !revealed && "translate-y-1.5 opacity-0",
          )}
          aria-hidden={!revealed}
        >
          Coming soon ✨
        </span>
      </span>
    </button>
  );
}

export default function Login() {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>(params.get("mode") === "signup" ? "signup" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [terms, setTerms] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Already signed in: go straight to the planner instead of showing the form again.
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  const copy = COPY[mode];
  const valid =
    email.includes("@") &&
    password.length >= (mode === "signup" ? 10 : 1) &&
    (mode === "login" || terms);

  if (me.isSuccess) return <Navigate to={params.get("next") || "/app/ask"} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      await (mode === "login" ? api.login(email, password) : api.signup(email, password));
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate(params.get("next") || "/app/ask");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth h-dvh min-h-[560px]">
      <div className="auth__art relative overflow-hidden bg-[#eef2ee]">
        <PixelField className="absolute inset-0 touch-pan-y" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2"
          style={{
            background:
              "linear-gradient(to top, rgba(0,0,0,.72), rgba(0,0,0,.25) 45%, transparent)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 p-10 text-white"
        >
          <Wordmark inverse className="text-lg text-white/85" />
          <h2 className="mt-3 font-display text-[44px] leading-[1.02] font-normal tracking-[-0.015em]">
            Every order, the right plant
          </h2>
          <p className="mt-3 max-w-[330px] text-[13px] leading-relaxed text-white/65">
            nument assigns each order to the plant and week with the best landed cost and carbon,
            without breaking capacity or a delivery date.
          </p>
        </div>
      </div>
      <div className="auth__panel overflow-y-auto">
        <form className="auth__col" onSubmit={submit} noValidate>
          <div className="mb-5 flex justify-center min-[900px]:hidden">
            <Wordmark />
          </div>
          <h1 className="auth__title">{copy.heading}</h1>
          <label className="sr-only" htmlFor="email">
            Work email
          </label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="e.g., name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label className="sr-only" htmlFor="password">
            Password
          </label>
          <Input
            id="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "signup" ? "Password (10+ characters)" : "Password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {mode === "signup" && (
            <label className="checkbox my-2">
              <Checkbox checked={terms} onCheckedChange={setTerms} />
              <span>I accept the terms of service &amp; privacy policy</span>
            </label>
          )}
          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-50 px-3 py-2.5 text-[13px] text-red-500"
            >
              <TriangleAlert className="mt-px size-3.5 shrink-0" /> {error}
            </div>
          )}
          <button
            type="submit"
            disabled={!valid}
            className={cn(
              "btn btn--auth mt-2",
              valid ? "btn--auth-primary" : "!cursor-not-allowed !text-tx-muted",
            )}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : copy.cta}
          </button>
          <div className="divider-or my-4">OR</div>
          <ComingSoon label="Continue with Google" />
          <ComingSoon label="Continue with Microsoft" />
          <p className="auth__switch">
            {copy.prompt}{" "}
            <button
              type="button"
              className="text-[#525252] hover:underline"
              onClick={() => {
                setMode(copy.next);
                setError(null);
              }}
            >
              {copy.action}
            </button>
          </p>
          <p className="mt-2 text-center text-label text-tx-tertiary">
            <Link to="/" className="hover:text-tx">
              Back to nument
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
