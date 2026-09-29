import type { ReactNode } from "react";

import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). */
export function PageHeader({
  title,
  titleId,
  subtitle,
  meta,
  actions,
  testId,
}: {
  title: ReactNode;
  titleId?: string;
  subtitle?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  testId?: string;
}) {
  return (
    <header className={`ui-page-header ${s.pageHeader}`} data-testid={testId}>
      <div className={s.headerText}>
        <h1 id={titleId}>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
        {meta && <div className={s.meta}>{meta}</div>}
      </div>
      {actions && <div className={s.actions}>{actions}</div>}
    </header>
  );
}
export default PageHeader;
