import type { ReactNode } from "react";

import s from "./primitives.module.css";

export function StatusChip({
  tone,
  icon,
  children,
}: {
  tone: "critical" | "warning" | "success" | "info" | "neutral";
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <span className={`${s.chip} ${s[`chip_${tone}`]}`}>
      {icon}
      {children}
    </span>
  );
}
export default StatusChip;
