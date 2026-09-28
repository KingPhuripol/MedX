"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { OUTPUT_LABEL, postJson, type CaseItem } from "@/lib/care";

export default function CareCaseList() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/care/cases", { credentials: "same-origin" })
      .then(async (resp) => {
        if (!active) return;
        if (resp.status === 503) throw new Error("The synthetic dataset is missing. Run make data.");
        if (!resp.ok) throw new Error("Could not load the case list.");
        setCases((await resp.json()).cases);
      })
      .catch((e: Error) => active && setError(e.message || "Could not load the case list."));
    return () => {
      active = false;
    };
  }, []);

  async function assess(caseId: string, dp: string) {
    setBusy(true);
    setError(null);
    const resp = await postJson(`/api/care/cases/${encodeURIComponent(caseId)}/assess`, { decision_point: dp }).catch(
      () => null,
    );
    if (resp && resp.ok) {
      const data = await resp.json();
      router.push(`/physician/care/${data.assessment_id}`);
      return;
    }
    setBusy(false);
    setError("The assessment could not be created. Please try again.");
  }

  return (
    <section aria-labelledby="care-cases-title">
      <h1 id="care-cases-title">Care suggestion cases</h1>
      <p>
        <strong>{OUTPUT_LABEL}.</strong> Synthetic development-split cases only. Each assessment shows red-flag alerts
        and screening status first, then a case summary, information to collect next and care-pathway options to
        consider. Nothing affects care until a physician confirms it.
      </p>
      <p>
        <Link href="/physician">Back to physician home</Link>
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!cases && !error && <p aria-live="polite">Loading cases…</p>}
      {cases && (
        <ul data-testid="care-case-list">
          {cases.map((c) => (
            <li key={c.case_id}>
              <strong>{c.case_id}</strong>{" "}
              {c.decision_points.map((d) => (
                <button
                  key={d.decision_point}
                  type="button"
                  className="secondary"
                  onClick={() => assess(c.case_id, d.decision_point)}
                  disabled={busy}
                  aria-label={`Assess ${c.case_id} at ${d.decision_point}`}
                >
                  {d.decision_point} ({d.as_of})
                </button>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
