import type { ReactNode } from "react";

export type PageHeaderProps = {
  title: ReactNode;
  titleId?: string;
  subtitle?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  testId?: string;
};

/** The one h1 of a page: title, quiet subtitle, meta chips and page-level actions. */
export function PageHeader({ title, titleId, subtitle, meta, actions, testId }: PageHeaderProps) {
  return (
    <header className="ui-page-header" data-testid={testId}>
      <div className="ui-page-header__text">
        <h1 id={titleId}>{title}</h1>
        {subtitle ? <p className="muted ui-page-header__subtitle">{subtitle}</p> : null}
        {meta ? <div className="ui-page-header__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="ui-page-header__actions">{actions}</div> : null}
    </header>
  );
}
export default PageHeader;
