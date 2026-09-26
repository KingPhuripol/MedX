import { DISCLAIMER_EN, DISCLAIMER_TH } from "@/lib/copy";

export default function Disclaimer() {
  return (
    <div className="disclaimer" role="note" data-testid="research-disclaimer">
      <p lang="en">{DISCLAIMER_EN}</p>
      <p lang="th">{DISCLAIMER_TH}</p>
    </div>
  );
}
