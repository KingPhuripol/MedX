import type { ReactNode } from "react";

import s from "./ui-local.module.css";

/** WP-C local minimal copy of the shared primitive (WP-A's version wins at merge). Sticky at >=768px. */
export function ActionBar({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <div className={`ui-action-bar ${s.actionBar}`}>
      {summary && <div>{summary}</div>}
      <div className={s.actionBarButtons}>{children}</div>
    </div>
  );
}
export default ActionBar;
