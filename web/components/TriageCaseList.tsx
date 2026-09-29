"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { postJson, type CaseItem } from "@/lib/triage";

export default function TriageCaseList() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/triage/cases", { credentials: "same-origin" })
      .then(async (resp) => {
        if (!active) return;
        if (!resp.ok) throw new Error(String(resp.status));
        setCases((await resp.json()).cases);
      })
      .catch(() => active && setError("Could not load the case list."));
    return () => {
      active = false;
    };
  }, []);

  async function assess(item: CaseItem) {
    setBusy(item.case_ref);
    setError(null);
    const resp = await postJson(`/api/triage/cases/${encodeURIComponent(item.case_ref)}/assess`, {
      as_of: item.suggested_as_of,
    }).catch(() => null);
    if (resp && resp.ok) {
      const data = await resp.json();
      router.push(`/nurse/triage/${data.assessment_id}`);
      return;
    }
    setBusy(null);
    setError("The assessment could not be created. Please try again.");
  }

  return (
    <section aria-labelledby="cases-title">
      <h1 id="cases-title">Triage cases</h1>
      <p>
        Synthetic fixture cases only. Each assessment gives red-flag alerts and a department suggestion for nurse
        review. Nothing is sent to a department until a nurse confirms it.
      </p>
      <p>
        <Link href="/nurse">Back to nurse home</Link>
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!cases && !error && <p aria-live="polite">Loading cases…</p>}
      {cases && (
        <ul data-testid="case-list">
          {cases.map((c) => (
            <li key={c.case_ref}>
              <strong>{c.case_ref}</strong> — {c.chief_complaint ?? "chief complaint not recorded"}{" "}
              <button type="button" onClick={() => assess(c)} disabled={busy !== null} aria-label={`Assess ${c.case_ref}`}>
                Assess
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
