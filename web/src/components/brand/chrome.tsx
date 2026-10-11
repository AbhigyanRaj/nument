import {
  BookOpen,
  ChevronDown,
  CodeXml,
  FileText,
  Layers,
  ListChecks,
  Menu,
  MessageSquareText,
  ScrollText,
  X,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { Ornament, StarGlyph, Wordmark } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";
import { useScrolled } from "@/hooks/motion";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export const REPO_URL = "https://github.com/AbhigyanRaj/nument";

interface MenuItem {
  title: string;
  desc: string;
  to: string;
  icon: ReactNode;
  external?: boolean;
}

const MENUS: { label: string; items: MenuItem[]; feature: { title: string; caption: string } }[] = [
  {
    label: "Product",
    items: [
      {
        title: "Ask",
        desc: "Plan, re-plan and explain in plain English",
        to: "/app/ask",
        icon: <MessageSquareText />,
      },
      {
        title: "Data",
        desc: "Load orders, plants, lanes and events",
        to: "/app/data",
        icon: <Layers />,
      },
      {
        title: "Trace",
        desc: "Every step the agent took, timed",
        to: "/app/trace",
        icon: <ListChecks />,
      },
      {
        title: "Brief",
        desc: "A number-checked note for leadership",
        to: "/app/ask",
        icon: <FileText />,
      },
    ],
    feature: { title: "Planner", caption: "Open the nument planner" },
  },
  {
    label: "Developers",
    items: [
      {
        title: "API reference",
        desc: "OpenAPI docs for every endpoint",
        to: "/api/docs",
        icon: <BookOpen />,
        external: true,
      },
      {
        title: "Source code",
        desc: "The full project on GitHub",
        to: REPO_URL,
        icon: <CodeXml />,
        external: true,
      },
      {
        title: "Evaluation",
        desc: "22 cases, CP-SAT vs greedy",
        to: `${REPO_URL}/blob/main/eval/report.md`,
        icon: <ScrollText />,
        external: true,
      },
    ],
    feature: { title: "API", caption: "POST /analyze in one call" },
  },
];

function MenuLink({ item, onNavigate }: { item: MenuItem; onNavigate?: () => void }) {
  const body = (
    <>
      <span className="mega-item__icon [&>svg]:size-5 [&>svg]:stroke-[1.5] [&>svg]:text-indigo-700">
        {item.icon}
      </span>
      <span>
        <span className="mega-item__title block">{item.title}</span>
        <span className="mega-item__desc block">{item.desc}</span>
      </span>
    </>
  );
  return item.external ? (
    <a className="mega-item" href={item.to} target="_blank" rel="noreferrer" onClick={onNavigate}>
      {body}
    </a>
  ) : (
    <Link className="mega-item" to={item.to} onClick={onNavigate}>
      {body}
    </Link>
  );
}

/** Marketing header: transparent over the hero, white after 10px of scroll; hover mega menus
 *  with a 100ms intent delay on desktop, a slide-down drawer below 1024px. */
export function SiteHeader() {
  const scrolled = useScrolled(10);
  const [open, setOpen] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const hover = (label: string | null) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(label), label ? 100 : 150);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(null);
        setDrawer(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const menu = MENUS.find((m) => m.label === open);
  // Signed-in visitors go straight back to their workspace instead of being offered "Log In".
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const signedIn = me.isSuccess;

  return (
    <header
      className={cn("site-header", (scrolled || open) && "is-scrolled")}
      onMouseLeave={() => hover(null)}
    >
      <div className="site-header__bg" />
      <div className="container site-header__row">
        <Link to="/" className="site-header__brand" aria-label="nument home">
          <Wordmark />
        </Link>
        <nav className="site-header__nav" aria-label="Main">
          {MENUS.map((m) => (
            <button
              key={m.label}
              className="nav-item gap-1"
              aria-expanded={open === m.label}
              onMouseEnter={() => hover(m.label)}
              onFocus={() => setOpen(m.label)}
              onClick={() => setOpen(open === m.label ? null : m.label)}
            >
              {m.label}
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform duration-200",
                  open === m.label && "rotate-180",
                )}
                strokeWidth={1.75}
                aria-hidden
              />
            </button>
          ))}
          <a className="nav-item" href="#how" onMouseEnter={() => hover(null)}>
            How it works
          </a>
          <a className="nav-item" href="#faq" onMouseEnter={() => hover(null)}>
            FAQ
          </a>
        </nav>
        <div className="site-header__actions">
          {signedIn ? (
            <>
              <span className="hidden text-caption text-tx-tertiary xl:inline">
                {me.data?.email}
              </span>
              <Button asChild variant="ink" size="sm">
                <Link to="/app/ask">Open planner</Link>
              </Button>
            </>
          ) : (
            <>
              <Button asChild variant="ink" size="sm">
                <Link to="/login">Log In</Link>
              </Button>
              <Button asChild variant="soft" size="sm">
                <Link to="/app/ask">Open planner</Link>
              </Button>
            </>
          )}
        </div>
        <div className="site-header__mobile">
          <Button asChild variant="soft" size="sm">
            <Link to={signedIn ? "/app/ask" : "/login"}>{signedIn ? "Planner" : "Log In"}</Link>
          </Button>
          <button className="burger" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <Menu className="size-6" strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {menu && (
        <>
          <div className="mega-backdrop" aria-hidden onMouseEnter={() => hover(null)} />
          <div className="mega" onMouseEnter={() => hover(menu.label)}>
            <div className="container mega__inner">
              <div className="col-span-2">
                <p className="label-mono mb-5 text-tx-tertiary">{menu.label}</p>
                <div className="grid grid-cols-2 gap-x-12 gap-y-3">
                  {menu.items.map((item) => (
                    <MenuLink key={item.title} item={item} onNavigate={() => setOpen(null)} />
                  ))}
                </div>
              </div>
              <Link to="/app/ask" className="mega-feature group" onClick={() => setOpen(null)}>
                <div className="mega-feature__img transition-transform duration-500 group-hover:scale-[1.02]">
                  {menu.feature.title}
                </div>
                <p className="mega-feature__caption">{menu.feature.caption}</p>
              </Link>
            </div>
          </div>
        </>
      )}

      {drawer && (
        <div
          className="fixed inset-0 z-[10001] bg-black/20 backdrop-blur-[6px]"
          onClick={() => setDrawer(false)}
        >
          <div
            className="drawer"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Menu"
          >
            <div className="flex items-center justify-between border-b border-st pb-3">
              <Wordmark />
              <button
                aria-label="Close menu"
                onClick={() => setDrawer(false)}
                className="grid size-10 place-items-center"
              >
                <X className="size-6" strokeWidth={1.5} />
              </button>
            </div>
            {MENUS.map((m) => (
              <details key={m.label} className="group">
                <summary className="drawer__row cursor-pointer list-none">
                  {m.label}
                  <ChevronDown
                    className="size-4 transition-transform group-open:rotate-180"
                    strokeWidth={1.5}
                  />
                </summary>
                <div className="flex flex-col gap-1 py-3">
                  {m.items.map((item) => (
                    <MenuLink key={item.title} item={item} onNavigate={() => setDrawer(false)} />
                  ))}
                </div>
              </details>
            ))}
            <a className="drawer__row" href="#how" onClick={() => setDrawer(false)}>
              How it works
            </a>
            <div className="drawer__actions">
              <Button asChild variant="ink">
                <Link to={signedIn ? "/app/ask" : "/login"}>{signedIn ? "Planner" : "Log In"}</Link>
              </Button>
              <Button asChild variant="soft">
                <Link to="/app/ask">Open planner</Link>
              </Button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

/** The one dark moment of a page: dusk gradient, grain, line-art rings, a star that sharpens. */
export function CtaBand({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className="container" data-reveal>
      <div className="cta-band">
        <div className="cta-band__inner">
          <div className="cta-band__noise" aria-hidden />
          <div className="cta-band__rings" aria-hidden />
          <div className="cta-band__title">{title}</div>
          <StarGlyph className="cta-star relative size-14 text-white" />
          <div className="relative flex flex-wrap justify-center gap-3">{children}</div>
        </div>
      </div>
    </section>
  );
}

/** The page sheet's rounded bottom edge, lifted over the footer. */
export function PageSheetEnd() {
  return <div className="page-sheet__end" aria-hidden />;
}

const FOOTER_COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Ask", href: "/app/ask" },
      { label: "Data", href: "/app/data" },
      { label: "Trace", href: "/app/trace" },
    ],
  },
  {
    title: "Developers",
    links: [
      { label: "API reference", href: "/api/docs" },
      { label: "Source code", href: REPO_URL },
      { label: "Evaluation", href: `${REPO_URL}/blob/main/eval/report.md` },
    ],
  },
  {
    title: "Method",
    links: [
      { label: "How it works", href: "/#how" },
      { label: "Guardrails", href: "/#guardrails" },
      { label: "Data card", href: `${REPO_URL}/blob/main/docs/DATA_CARD.md` },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Log in", href: "/login" },
      { label: "Create account", href: "/login?mode=signup" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-brand">
            <div className="flex flex-col gap-4">
              <Wordmark className="text-4xl" />
              <p className="text-label text-tx-tertiary">Every order, the right plant.</p>
              <div className="flex gap-3">
                <div className="trust-tile">
                  SYNTHETIC
                  <br />
                  DATA
                </div>
                <div className="trust-tile">
                  NUMBER
                  <br />
                  CHECKED
                </div>
              </div>
            </div>
            <div className="footer-legal">
              © 2026 nument. A planning demo on fully synthetic data.
            </div>
          </div>
          <div className="footer-cols">
            {FOOTER_COLUMNS.map((col) => (
              <div className="footer-col" key={col.title}>
                <h3 className="label-mono">{col.title}</h3>
                <ul>
                  {col.links.map((link) => (
                    <li key={link.label}>
                      <a href={link.href}>{link.label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="container" style={{ width: "92%" }}>
        <div className="footer-giant footer-giant--art" aria-hidden>
          nument
        </div>
      </div>
    </footer>
  );
}

export { Ornament };
