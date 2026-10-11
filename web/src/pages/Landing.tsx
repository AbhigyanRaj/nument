// The public home page: what nument does, how it works, and a way into the planner.

import { Link } from "react-router";

import heroGradient from "@/assets/hero-gradient.svg";
import { CtaBand, PageSheetEnd, SiteFooter, SiteHeader } from "@/components/brand/chrome";
import { Ornament, SectionHeading } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";
import { useReveal } from "@/hooks/motion";
import { EXAMPLES } from "@/pages/app/Ask";

export default function Landing() {
  useReveal();
  return (
    <>
      <SiteHeader />
      <main className="page-sheet">
        <section className="hero">
          <div className="hero__fade" />
          <img className="hero__gradient" src={heroGradient} alt="" aria-hidden />
          <div className="container hero__content">
            <div className="hero__glow" />
            <Ornament className="hero__ornament" />
            <div className="hero-badge">
              <div className="hero-badge__rule" />
              <p className="hero-badge__text">Multi-plant order allocation</p>
              <div className="hero-badge__rule" />
            </div>
            <h1 className="h-hero">
              Every order,
              <br />
              the right plant.
            </h1>
            <p className="lead">
              nument decides which plant builds each order and when, balancing cost, carbon and
              dates.
              <br className="hidden md:inline" /> Every number comes from the solver, never from the
              model.
            </p>
            <div className="hero__actions">
              <Button asChild variant="hero-primary">
                <Link to="/app/ask">Open the planner</Link>
              </Button>
              <Button asChild variant="hero-outline">
                <a href="#how">See how it works</a>
              </Button>
            </div>
          </div>
          <div className="marquee w-full">
            <p className="eyebrow">Ask it like you would ask a planner</p>
            <div className="marquee__track">
              <div className="marquee__row !opacity-100 [&>*]:!h-auto [&>*]:!opacity-100 [&>*]:!filter-none">
                {[...EXAMPLES, ...EXAMPLES].map((example, i) => (
                  <Link key={i} to="/app/ask" className="chip is-active whitespace-nowrap">
                    {example}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section id="how" className="container section">
          <SectionHeading
            title={"Six steps.\nTwo of them use an LLM."}
            intro="The model reads your request and writes the words. Planning, checking and comparing are plain code, so every figure is computed and every one is checked."
          />
          <div className="grid w-full gap-2 md:grid-cols-3" data-reveal-stagger>
            {[
              ["01", "Understand", "The request is parsed into an intent, weights and a scenario."],
              ["02", "Optimise", "CP-SAT assigns every order to a plant and week within capacity."],
              [
                "03",
                "Validate",
                "An independent checker recomputes capacity, eligibility and dates.",
              ],
              ["04", "Compare", "Re-plans are diffed: what moved, extra cost and carbon."],
              ["05", "Write", "The model writes a short summary from computed facts only."],
              [
                "06",
                "Check numbers",
                "Every figure in the text is matched to a fact, or rewritten.",
              ],
            ].map(([n, title, body]) => (
              <div key={n} className="mini-card min-h-44">
                <span className="font-mono text-label text-indigo-700">{n}</span>
                <div>
                  <p className="mini-card__title">{title}</p>
                  <p className="mini-card__desc">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <CtaBand
          title={
            <>
              <p>Plan this week&apos;s orders</p>
              <p>in under a minute</p>
            </>
          }
        >
          <Button asChild variant="ink">
            <Link to="/app/ask">Open the planner</Link>
          </Button>
        </CtaBand>
        <PageSheetEnd />
      </main>
      <SiteFooter />
    </>
  );
}
