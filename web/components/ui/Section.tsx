import { useId, type HTMLAttributes, type ReactNode } from "react";

export type SectionProps = {
  title?: ReactNode;
  titleId?: string;
  actions?: ReactNode;
  tone?: "default" | "critical" | "warning";
  children?: ReactNode;
} & Omit<HTMLAttributes<HTMLElement>, "title">;

/** Card section with an h2 title. `critical` is reserved for red flags and errors. */
export function Section({ title, titleId, actions, tone = "default", children, className, ...rest }: SectionProps) {
  const generated = useId();
  const id = titleId ?? `section-${generated.replace(/:/g, "")}`;
  return (
    <section
      className={["ui-section", `ui-section--${tone}`, className].filter(Boolean).join(" ")}
      aria-labelledby={title ? id : undefined}
      {...rest}
    >
      {title || actions ? (
        <div className="ui-section__head">
          {title ? <h2 id={id}>{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
export default Section;
