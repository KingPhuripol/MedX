import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  headingLevel?: 1 | 2;
};

/** Centred dashed panel: what happened, why, and the next step. h1 only for 403/404. */
export function EmptyState({ title, description, action, icon, headingLevel = 2 }: EmptyStateProps) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <div className="ui-empty">
      {icon ? (
        <span className="ui-empty__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <Heading>{title}</Heading>
      {description ? <div className="ui-empty__description">{description}</div> : null}
      {action ? <div className="ui-empty__action">{action}</div> : null}
    </div>
  );
}
export default EmptyState;
