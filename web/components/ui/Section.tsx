import type { HTMLAttributes, ReactNode } from "react";

import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). */
export function Section({
  title,
  titleId,
  actions,
  tone = "default",
  children,
  className,
  ...rest
}: {
  title?: ReactNode;
  titleId?: string;
  actions?: ReactNode;
  tone?: "default" | "critical" | "warning";
  children?: ReactNode;
} & HTMLAttributes<HTMLElement>) {
  const toneClass = tone === "critical" ? s.critical : tone === "warning" ? s.warning : "";
  return (
    <section
      {...rest}
      className={`ui-section ui-section--${tone} ${s.section} ${toneClass} ${className ?? ""}`}
      aria-labelledby={titleId}
    >
      {(title || actions) && (
        <div className={s.sectionHead}>
          {title && (
            <h2 id={titleId} className={`ui-section-title ${s.title}`}>
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
export default Section;
