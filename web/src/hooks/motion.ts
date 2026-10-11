import { useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "@/lib/utils";

/** Adds .is-revealed to every [data-reveal] (and staggered children) inside the page once
 *  15% of it is visible, the kit's 800ms fade-up. CSS keeps it visible under reduced motion. */
export function useReveal(deps: unknown[] = []) {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>(
      "[data-reveal]:not(.is-revealed), [data-reveal-stagger] > *:not(.is-revealed)",
    );
    if (!("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("is-revealed"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target as HTMLElement;
          const parent = el.parentElement;
          if (parent?.hasAttribute("data-reveal-stagger")) {
            const index = Array.from(parent.children).indexOf(el);
            el.style.transitionDelay = `${index * 120}ms`;
          }
          el.classList.add("is-revealed");
          io.unobserve(el);
        }),
      { threshold: 0.15 },
    );
    targets.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Counts from 0 to `target` when the element scrolls into view (instant with reduced motion). */
export function useCountUp(target: number, duration = 1200) {
  const ref = useRef<HTMLElement | null>(null);
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0));
  useEffect(() => {
    if (prefersReducedMotion() || document.documentElement.classList.contains("capture")) {
      setValue(target);
      return;
    }
    const el = ref.current;
    if (!el || !("IntersectionObserver" in window)) {
      setValue(target);
      return;
    }
    let frame = 0;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / duration);
          const eased = 1 - Math.pow(1 - t, 3);
          setValue(target * eased);
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [target, duration]);
  return { ref, value };
}

/** True once the page has scrolled past `offset` px (the header's white layer). */
export function useScrolled(offset = 10) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > offset);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [offset]);
  return scrolled;
}

/** Types `text` out character by character (a full string under reduced motion). */
export function useTypewriter(text: string, speed = 42, startDelay = 400) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? text : ""));
  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(text);
      return;
    }
    setShown("");
    let i = 0;
    let timer = window.setTimeout(function step() {
      i += 1;
      setShown(text.slice(0, i));
      if (i < text.length) timer = window.setTimeout(step, speed);
    }, startDelay);
    return () => window.clearTimeout(timer);
  }, [text, speed, startDelay]);
  return shown;
}
