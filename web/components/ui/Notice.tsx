import type { HTMLAttributes, ReactNode } from "react";

import s from "./primitives.module.css";

type Props = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  tone: "critical" | "warning" | "info" | "success";
  title?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
};

export function Notice({ tone, title, icon, actions, children, className, ...rest }: Props) {
  return (
    <div className={[s.notice, s[`notice_${tone}`], className].filter(Boolean).join(" ")} {...rest}>
      {icon}
      <div>
        {title ? <strong>{title}</strong> : null}
        {children}
        {actions}
      </div>
    </div>
  );
}
export default Notice;
