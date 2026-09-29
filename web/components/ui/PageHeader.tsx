import type { ReactNode } from "react";

import s from "./primitives.module.css";

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
    <header className={s.header} data-testid={testId}>
      <div className={s.headerMain}>
        <h1 id={titleId}>{title}</h1>
        {subtitle ? <p className={s.muted}>{subtitle}</p> : null}
        {meta ? <div className={s.meta}>{meta}</div> : null}
      </div>
      {actions ? <div className={s.actions}>{actions}</div> : null}
    </header>
  );
}
export default PageHeader;
