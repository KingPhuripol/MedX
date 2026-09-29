import type { ReactNode } from "react";

import s from "./ui-local.module.css";

export type DataColumn<T> = { key: string; header: ReactNode; render: (row: T) => ReactNode; className?: string };

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). Cards below 768px. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  testId,
  empty,
}: {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption?: ReactNode;
  testId?: string;
  empty?: ReactNode;
}) {
  if (rows.length === 0 && empty) return <div className={s.tableEmpty}>{empty}</div>;
  return (
    <table className={`ui-table ${s.table}`} data-testid={testId}>
      {caption && <caption className="muted">{caption}</caption>}
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
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((c) => (
              <td key={c.key} data-label={typeof c.header === "string" ? c.header : c.key} className={c.className}>
                {c.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
export default DataTable;
