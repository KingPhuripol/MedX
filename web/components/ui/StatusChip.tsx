import type { ReactNode } from "react";

import s from "./ui-local.module.css";

type Tone = "critical" | "warning" | "success" | "info" | "neutral";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). Never role="status". */
export function StatusChip({ tone, icon, children }: { tone: Tone; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={`ui-chip ui-chip--${tone} ${s.chip} ${s[`chip_${tone}`]}`}>
      {icon}
      {children}
    </span>
  );
}
export default StatusChip;
