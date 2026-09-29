import type { ReactNode } from "react";

export type FieldProps = { label: ReactNode; htmlFor: string; hint?: ReactNode; error?: ReactNode; children: ReactNode };

/** Label + control + hint/error. Controls inside get 44px height via .ui-field CSS. */
export function Field({ label, htmlFor, hint, error, children }: FieldProps) {
  return (
    <div className="ui-field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <small id={`${htmlFor}-hint`}>{hint}</small> : null}
      {error ? (
        <p role="alert" className="ui-field-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
export default Field;
