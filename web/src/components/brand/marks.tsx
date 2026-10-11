// Brand marks: the nument wordmark and the small ornaments.

import type { ReactNode, SVGProps } from "react";

import { cn } from "@/lib/utils";

/** The lowercase text wordmark (DESIGN.md §2): Figtree 700, tracking -0.035em. */
export function Wordmark({ className, inverse }: { className?: string; inverse?: boolean }) {
  return (
    <span
      className={cn(
        "font-sans text-2xl leading-none font-bold tracking-[-0.035em]",
        inverse ? "text-white" : "text-black",
        className,
      )}
    >
      nument
    </span>
  );
}

/** nument's own symmetric line flourish (assets/ornament.svg), drawn in currentColor. */
export function Ornament({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 208 32"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      aria-hidden
      className={cn("h-6 w-auto md:h-8", className)}
      {...props}
    >
      <path d="M4 30h200" />
      <path d="M104 4c-6 8-6 16 0 24c6-8 6-16 0-24Z" />
      <path d="M92 26c-10-2-20-8-26-16c8 2 18 6 26 16Z" />
      <path d="M116 26c10-2 20-8 26-16c-8 2-18 6-26 16Z" />
      <path d="M60 26c-12 0-26-4-36-10c12 0 26 4 36 10Z" />
      <path d="M148 26c12 0 26-4 36-10c-12 0-26 4-36 10Z" />
      <circle cx="104" cy="16" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** A four-petal star glyph used on the dusk CTA band. */
export function StarGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={className}>
      <path
        fill="currentColor"
        d="M32 2c2.6 13.4 8.6 19.4 22 22-13.4 2.6-19.4 8.6-22 22-2.6-13.4-8.6-19.4-22-22C23.4 21.4 29.4 15.4 32 2Zm0 40c1.2 6.1 3.9 8.8 10 10-6.1 1.2-8.8 3.9-10 10-1.2-6.1-3.9-8.8-10-10 6.1-1.2 8.8-3.9 10-10Z"
        transform="translate(0 -2)"
      />
    </svg>
  );
}

/** Small uppercase label (12px, 525, tracking .17em). */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("eyebrow", className)}>{children}</p>;
}

/** Centred section heading: display h2 (36/28px) + optional intro, the kit's .section__head. */
export function SectionHeading({
  title,
  intro,
  align = "center",
  className,
}: {
  title: ReactNode;
  intro?: ReactNode;
  align?: "center" | "left";
  className?: string;
}) {
  return (
    <div
      data-reveal
      className={cn("section__head", align === "left" && "section__head--left", className)}
    >
      <h2 className="h-section text-balance">{title}</h2>
      {intro && <p className="intro">{intro}</p>}
    </div>
  );
}

const BADGE_TONES = {
  indigo: "badge--indigo",
  green: "badge--green",
  orange: "badge--orange",
  pink: "badge--pink",
  yellow: "badge--yellow",
  red: "badge--red",
  grey: "badge--grey",
} as const;

/** Coloured chip with the kit's inner glow and hover wiggle. */
export function Badge({
  tone = "indigo",
  children,
  className,
  icon,
}: {
  tone?: keyof typeof BADGE_TONES;
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <span className={cn("badge", BADGE_TONES[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

/** Label left, value right (20px, 525, tabular): the kit's stat row. */
export function StatRow({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="stat-row">
      <span className="stat-row__label">{label}</span>
      <span className="stat-row__value">{value}</span>
    </div>
  );
}
