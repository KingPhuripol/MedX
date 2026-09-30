/** MedX text wordmark ("Med" + "X" in --primary). Text only, never an image logo. */
export function Wordmark({ size }: { size: 20 | 28 }) {
  return (
    <span className="wordmark" style={{ fontSize: size }} role="img" aria-label="MedX" data-testid="wordmark">
      Med<span>X</span>
    </span>
  );
}
