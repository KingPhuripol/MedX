import type { HTMLAttributes, ReactNode } from "react";

import s from "./primitives.module.css";

type Props = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title?: ReactNode;
  titleId?: string;
  actions?: ReactNode;
  tone?: "default" | "critical" | "warning";
  children?: ReactNode;
};

export function Section({ title, titleId, actions, tone = "default", children, className, ...rest }: Props) {
  const tc = tone === "critical" ? s.critical : tone === "warning" ? s.warning : "";
  return (
    <section
      className={[s.section, tc, className].filter(Boolean).join(" ")}
      aria-labelledby={title ? titleId : undefined}
      {...rest}
    >
      {title ? (
        <div className={s.sectionHead}>
          <h2 id={titleId}>{title}</h2>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
export default Section;
