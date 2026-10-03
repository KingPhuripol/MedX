import { COPY } from "@/lib/copy";

/** The limitation label: the last line of every screen. */
export function Limit({ style }: { style?: React.CSSProperties }) {
  return (
    <p className="limit" data-testid="limit" style={style}>
      {COPY.limit}
    </p>
  );
}
