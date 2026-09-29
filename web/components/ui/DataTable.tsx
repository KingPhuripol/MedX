import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Applied to both the th and the td. */
  className?: string;
  /** Omit the per-cell data-label (compact mobile cards, e.g. action columns). */
  hideLabel?: boolean;
};
export type DataTableColumn<T> = Column<T>;

export type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption?: ReactNode;
  testId?: string;
  empty?: ReactNode;
};

/** Table at >=768px, one card per row below (td shows its column header via data-label). */
export function DataTable<T>({ columns, rows, rowKey, caption, testId, empty }: DataTableProps<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>;
  return (
    <table className="ui-table" data-testid={testId}>
      {caption ? <caption className="sr-only">{caption}</caption> : null}
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
              <td key={c.key} className={c.className} data-label={!c.hideLabel && typeof c.header === "string" ? c.header : undefined}>
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
