/** MedX text wordmark. No logo asset; the X is the purple accent. */
export default function Wordmark() {
  return (
    <span className="wordmark" role="img" aria-label="MedX" data-testid="wordmark">
      Med<span className="wordmark-x">X</span>
    </span>
  );
}
