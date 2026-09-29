import type { ReactNode } from "react";

type PageFrameProps = {
  /** Short scope label shown in the eyebrow chip. */
  eyebrow: string;
  titleId: string;
  title: ReactNode;
  /** One claim sentence; must end with a period. */
  claim: string;
  /** Next-step strip content; include one <em> key phrase. */
  next: ReactNode;
  children?: ReactNode;
  testId?: string;
};

/** Page grammar (R&D deck): eyebrow → h1 → claim → body → next-step strip. */
export default function PageFrame({ eyebrow, titleId, title, claim, next, children, testId }: PageFrameProps) {
  return (
    <section className="page" aria-labelledby={titleId} data-testid={testId}>
      <p className="eyebrow" data-testid="eyebrow">
        <span className="dot" aria-hidden="true" />
        {eyebrow}
      </p>
      <h1 id={titleId}>{title}</h1>
      <h2 className="claim" data-testid="claim">
        {claim}
      </h2>
      <div className="page-body">{children}</div>
      <p className="next-step" data-testid="next-step">
        <span className="arrow" aria-hidden="true">
          →
        </span>
        {next}
      </p>
    </section>
  );
}
