// The pill buttons used everywhere, with the hover glow and press effect.

import { Slot, Slottable } from "@radix-ui/react-slot";
import { ArrowRight } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

// Pill buttons from the kit (components.css .btn): cursor-following glow on filled variants,
// press scale .96, 350ms colour transitions. "app" is the logged-in product's #141414 primary.
const VARIANTS = {
  ink: "btn--ink",
  soft: "btn--soft",
  "hero-primary": "btn--hero btn--hero-primary",
  "hero-outline": "btn--hero btn--hero-outline",
  outline: "btn--outline",
  auth: "btn--auth",
  "auth-primary": "btn--auth btn--auth-primary",
  app: "btn--app",
  ghost: "btn--ghost",
} as const;

const GLOWS = new Set<keyof typeof VARIANTS>(["ink", "hero-primary", "auth-primary", "app"]);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS;
  size?: "sm" | "md";
  block?: boolean;
  arrow?: boolean;
  asChild?: boolean;
}

function trackGlow(event: PointerEvent<HTMLElement>) {
  const el = event.currentTarget;
  const rect = el.getBoundingClientRect();
  el.style.setProperty("--gx", `${event.clientX - rect.left}px`);
  el.style.setProperty("--gy", `${event.clientY - rect.top}px`);
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "ink",
    size = "md",
    block,
    arrow,
    asChild,
    className,
    children,
    onPointerMove,
    ...props
  },
  ref,
) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      ref={ref}
      className={cn(
        "btn",
        VARIANTS[variant],
        size === "sm" && "btn--sm",
        block && "btn--block",
        className,
      )}
      onPointerMove={(event: PointerEvent<HTMLButtonElement>) => {
        if (GLOWS.has(variant)) trackGlow(event);
        onPointerMove?.(event);
      }}
      {...props}
    >
      {GLOWS.has(variant) && <span className="btn__glow" aria-hidden />}
      <Slottable>{children}</Slottable>
      {arrow && <ArrowRight className="btn__arrow" aria-hidden strokeWidth={1.75} />}
    </Comp>
  );
});
