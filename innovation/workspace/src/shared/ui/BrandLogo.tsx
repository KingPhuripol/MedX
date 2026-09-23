import React from "react";

/** MedX: the mark is a doorway, the entry point of the Clinical Front Door. */
export function BrandLogo({ compact = false }: { compact?: boolean }) {
  return <div className={`brand-logo ${compact ? "brand-logo--compact" : ""}`}>
    <span className="brand-logo__mark" aria-hidden="true">
      <svg viewBox="0 0 48 48" width="48" height="48" fill="none" focusable="false">
        <rect x="1" y="1" width="46" height="46" rx="13" fill="currentColor" />
        <path d="M12 32V16L20 26L28 16V32 M32 18L40 30 M40 18L32 30" stroke="var(--text-on-brand)" strokeWidth="2.8" strokeLinecap="round" />
        
      </svg>
    </span>
    {!compact ? <span className="brand-logo__copy"><strong>MedX</strong><small>Clinical Front Door</small></span> : null}
  </div>;
}
