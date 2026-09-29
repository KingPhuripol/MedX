import type { ReactNode } from "react";

export type StatusTone = "critical" | "warning" | "success" | "info" | "neutral";

/** Pill with text (never colour only). Deliberately has no role="status". */
export function StatusChip({ tone, icon, children }: { tone: StatusTone; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={`ui-chip ui-chip--${tone}`}>
      {icon ? (
        <span aria-hidden="true" className="ui-chip__icon">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}
export default StatusChip;
