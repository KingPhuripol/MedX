import React from "react";

/** Pratu (ประตู, "door"): the mark is a doorway, the entry point of the Clinical Front Door. */
export function BrandLogo({ compact = false }: { compact?: boolean }) {
  return <div className={`brand-logo ${compact ? "brand-logo--compact" : ""}`}>
    <span className="brand-logo__mark" aria-hidden="true">
      <svg viewBox="0 0 48 48" width="48" height="48" fill="none" focusable="false">
        <rect x="1" y="1" width="46" height="46" rx="13" fill="currentColor" />
        <path d="M16 35V19.5C16 15.9 18.7 13 22 13s6 2.9 6 6.5V35" stroke="var(--text-on-brand)" strokeWidth="2.8" strokeLinecap="round" />
        <path d="M13 35h18" stroke="var(--text-on-brand)" strokeWidth="2.8" strokeLinecap="round" />
      </svg>
    </span>
    {!compact ? <span className="brand-logo__copy"><strong>Pratu</strong><small>Clinical Front Door</small></span> : null}
  </div>;
}
