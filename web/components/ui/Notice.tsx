import type { HTMLAttributes, ReactNode } from "react";

export type NoticeProps = {
  tone: "critical" | "warning" | "info" | "success";
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
} & Omit<HTMLAttributes<HTMLDivElement>, "title">;

/** Bordered message block. No default role: callers set role="alert" where the page requires it. */
export function Notice({ tone, title, icon, actions, children, className, ...rest }: NoticeProps) {
  return (
    <div className={["ui-notice", `ui-notice--${tone}`, className].filter(Boolean).join(" ")} {...rest}>
      {icon ? (
        <span className="ui-notice__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <div className="ui-notice__body">
        {title ? <p className="ui-notice__title">{title}</p> : null}
        {children}
        {actions ? <div className="ui-notice__actions">{actions}</div> : null}
      </div>
    </div>
  );
}
export default Notice;
