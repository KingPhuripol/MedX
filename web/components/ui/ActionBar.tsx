import type { ReactNode } from "react";

import s from "./primitives.module.css";

export function ActionBar({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <div className={s.actionBar}>
      {summary ? <div className={s.actionSummary}>{summary}</div> : null}
      <div className={s.actionButtons}>{children}</div>
    </div>
  );
}
export default ActionBar;
