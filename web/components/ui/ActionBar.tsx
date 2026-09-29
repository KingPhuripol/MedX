"use client";
import { useEffect, useState, type ReactNode } from "react";

/**
 * Bar for the page's primary action. Static by default so it can never cover red-flag content on load;
 * with `pinAfter` (id of the red-flag heading) it becomes sticky only once that heading has scrolled above the viewport.
 */
export function ActionBar({ summary, children, pinAfter }: { summary?: ReactNode; children: ReactNode; pinAfter?: string }) {
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    const el = pinAfter ? document.getElementById(pinAfter) : null;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setPinned(!e.isIntersecting && e.boundingClientRect.bottom < 0));
    io.observe(el);
    return () => io.disconnect();
  }, [pinAfter]);
  return (
    <div className={pinned ? "ui-action-bar ui-action-bar--pinned" : "ui-action-bar"}>
      {summary ? <div className="ui-action-bar__summary">{summary}</div> : null}
      <div className="ui-action-bar__actions">{children}</div>
    </div>
  );
}
export default ActionBar;
