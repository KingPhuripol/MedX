import type { ReactNode } from "react";

import s from "./primitives.module.css";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: ReactNode;
  htmlFor: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={s.field}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <small id={`${htmlFor}-hint`}>{hint}</small> : null}
      {error ? (
        <p role="alert" className={s.fieldError}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
export default Field;
