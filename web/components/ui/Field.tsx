import type { ReactNode } from "react";

import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). */
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
    <div className={`ui-field ${s.field}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <small id={`${htmlFor}-hint`}>{hint}</small>}
      {error && (
        <p role="alert" className={`ui-field-error ${s.fieldError}`}>
          {error}
        </p>
      )}
    </div>
  );
}
export default Field;
