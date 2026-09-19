import React from "react";
import { Icon, type IconName } from "./Icon";

export function StatusBadge({ tone = "neutral", children }: {
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  children: React.ReactNode;
}) {
  const icon: IconName = tone === "success" ? "check" : tone === "warning" || tone === "danger" ? "alert" : "spark";
  return <span className={`status-badge status-${tone}`}><Icon name={icon} size={14} />{children}</span>;
}
