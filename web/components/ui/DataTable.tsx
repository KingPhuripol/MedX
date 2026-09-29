import type { ReactNode } from "react";

import s from "./primitives.module.css";

export type Column<T> = { key: string; header: ReactNode; render: (row: T) => ReactNode; className?: string; hideLabel?: boolean };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  testId,
  empty,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption?: ReactNode;
  testId?: string;
  empty?: ReactNode;
}) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <div className={s.tableWrap}>
      <table className={s.table} data-testid={testId}>
        {caption ? <caption className={s.srOnly}>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={c.className}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td key={c.key} className={c.className} data-label={c.hideLabel ? undefined : typeof c.header === "string" ? c.header : c.key}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export default DataTable;
