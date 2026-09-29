import type { HTMLAttributes, ReactNode } from "react";

import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). No default role. */
export function Notice({
  tone,
  title,
  icon,
  actions,
  children,
  className,
  ...rest
}: {
  tone: "critical" | "warning" | "info" | "success";
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div {...rest} className={`ui-notice ui-notice--${tone} ${s.notice} ${s[`notice_${tone}`]} ${className ?? ""}`}>
      {icon && <div aria-hidden="true">{icon}</div>}
      <div className={s.noticeBody}>
        {title && <p className={s.noticeTitle}>{title}</p>}
        {children}
        {actions}
      </div>
    </div>
  );
}
export default Notice;
