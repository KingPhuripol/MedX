import type { ReactNode } from "react";

import s from "./primitives.module.css";

export function EmptyState({
  title,
  description,
  action,
  icon,
  headingLevel = 2,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  headingLevel?: 1 | 2;
}) {
  const H = headingLevel === 1 ? "h1" : "h2";
  return (
    <div className={s.empty}>
      {icon}
      <H>{title}</H>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}
export default EmptyState;
