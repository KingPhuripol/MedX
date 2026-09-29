"use client";

import { useEffect, useRef, useState } from "react";

import type { LiveState } from "./copy";

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/**
 * Decorative orb. The audio level is written straight to `style.transform` from a rAF loop
 * (no React state per frame). With reduced motion the orb stays static; state is in the status line.
 */
export function Orb({ state, getLevel }: { state: LiveState; getLevel: () => number }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced || (state !== "listening" && state !== "speaking")) {
      el.style.transform = "";
      return;
    }
    let raf = 0;
    let smooth = 0;
    const tick = () => {
      const raw = getLevel();
      smooth += (raw - smooth) * (raw > smooth ? 0.4 : 0.12); // fast attack, slow release
      el.style.transform = `scale(${(1 + 0.3 * smooth).toFixed(3)})`;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      el.style.transform = "";
    };
  }, [state, reduced, getLevel]);

  return (
    <div className="live-orb-stage" aria-hidden="true">
      <div className="live-orb" data-testid="live-orb" data-state={state} ref={ref} />
    </div>
  );
}
