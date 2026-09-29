import type { ReactNode } from "react";

/** Sticky bar for the page's primary action (replaces .review-bar). Summary left, buttons right. */
export function ActionBar({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <div className="ui-action-bar">
      {summary ? <div className="ui-action-bar__summary">{summary}</div> : null}
      <div className="ui-action-bar__actions">{children}</div>
    </div>
  );
}
export default ActionBar;
