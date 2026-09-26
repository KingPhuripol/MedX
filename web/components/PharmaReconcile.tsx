"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import RoleGuard from "@/components/RoleGuard";
import {
  NLM_ATTRIBUTION,
  NOTICE_LABELS,
  PHRASING_LABEL,
  REVIEW_NOTE,
  SOURCE_LABELS,
  TYPE_LABELS,
  formatDose,
  sortIssues,
  type Fixture,
  type Issue,
  type Run,
} from "@/lib/pharma";

const JSON_HEADERS = { "Content-Type": "application/json" };

function issueTitle(issue: Issue): string {
  return `${TYPE_LABELS[issue.type] ?? issue.type}: ${issue.ingredients.join(", ")}`;
}

function IssueCard({
  issue,
  index,
  onConfirm,
  onDismiss,
  busy,
}: {
  issue: Issue;
  index: number;
  onConfirm: (issue: Issue) => void;
  onDismiss: (issue: Issue, reason: string) => void;
  busy: boolean;
}) {
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const titleId = `issue-${index}-title`;
  const reasonId = `issue-${index}-reason`;
  const title = issueTitle(issue);

  function submitDismiss() {
    if (!reason.trim()) {
      setReasonError("A reason is required to dismiss an issue.");
      return;
    }
    setReasonError(null);
    onDismiss(issue, reason);
  }

  return (
    <article className="issue" aria-labelledby={titleId} data-severity={issue.severity} data-type={issue.type}>
      <h3 id={titleId}>{title}</h3>
      <p className="issue-meta">
        Priority: {issue.severity} · Status: <strong data-testid="issue-status">{issue.status}</strong> · Rule{" "}
        {issue.rule_id}
        {issue.unverifiable ? " · units not comparable" : ""}
        {issue.possible_substitution ? " · possible same-class substitution" : ""}
      </p>
      <p className="phrasing">{issue.phrasing.text}</p>
      <p className="phrasing-label">
        {PHRASING_LABEL} (phrasing: {issue.phrasing.source}, {issue.phrasing.provider})
      </p>
      <table className="sources">
        <caption>Conflicting sources for {title}</caption>
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col">Evidence reference</th>
            <th scope="col">Available at</th>
            <th scope="col">Text as recorded</th>
            <th scope="col">Dose</th>
            <th scope="col">Frequency</th>
          </tr>
        </thead>
        <tbody>
          {issue.conflicting_sources.map((src, n) => (
            <tr key={`${src.evidence_ref}-${n}`}>
              <th scope="row">
                {SOURCE_LABELS[src.source_type] ?? src.source_type}
                {src.presence === "absent" ? " (not present)" : ""}
              </th>
              <td>{src.evidence_ref}</td>
              <td>{src.available_at_time}</td>
              <td>{src.presence === "absent" ? "—" : src.raw_span}</td>
              <td>{src.source_type === "allergy_record" ? "—" : formatDose(src)}</td>
              <td>{src.source_type === "allergy_record" || src.presence === "absent" ? "—" : src.frequency_code ?? "not stated"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {issue.status === "open" ? (
        <div className="decision">
          <button type="button" onClick={() => onConfirm(issue)} disabled={busy} aria-describedby={titleId}>
            Confirm
          </button>
          <div className="field">
            <label htmlFor={reasonId}>Reason for dismissing</label>
            <textarea
              id={reasonId}
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              aria-invalid={reasonError ? true : undefined}
              aria-describedby={reasonError ? `${reasonId}-error` : undefined}
            />
            {reasonError && (
              <p id={`${reasonId}-error`} className="error" role="alert">
                {reasonError}
              </p>
            )}
          </div>
          <button type="button" onClick={submitDismiss} disabled={busy} aria-describedby={titleId}>
            Dismiss
          </button>
        </div>
      ) : (
        <p className="decision-recorded">
          Decision recorded: {issue.status}
          {issue.decision?.reason ? ` — reason: ${issue.decision.reason}` : ""}
        </p>
      )}
    </article>
  );
}

function Reconcile() {
  const router = useRouter();
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState("rules_plus_model");
  const [run, setRun] = useState<Run | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const handleAuth = useCallback(
    (resp: Response) => {
      if (resp.status === 401) router.replace("/login");
      return resp;
    },
    [router],
  );

  const loadRun = useCallback(
    async (runId: string, message?: string) => {
      const resp = handleAuth(await fetch(`/api/pharma/runs/${encodeURIComponent(runId)}`, { credentials: "same-origin" }));
      if (!resp.ok) {
        setStatus("The saved run could not be loaded.");
        return;
      }
      const data: Run = await resp.json();
      setRun(data);
      if (message) setStatus(message);
    },
    [handleAuth],
  );

  useEffect(() => {
    fetch("/api/pharma/fixtures", { credentials: "same-origin" })
      .then(handleAuth)
      .then(async (resp) => {
        if (!resp.ok) return;
        const data = await resp.json();
        setFixtures(data.fixtures);
        if (data.fixtures.length) setSelected((cur) => cur || data.fixtures[0].fixture_ref);
      })
      .catch(() => setStatus("The service is unavailable. Please try again."));
    const runId = new URLSearchParams(window.location.search).get("run");
    if (runId) void loadRun(runId, "Saved run loaded.");
  }, [handleAuth, loadRun]);

  async function onRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setStatus("Running check…");
    try {
      const resp = handleAuth(
        await fetch("/api/pharma/reconcile", {
          method: "POST",
          headers: JSON_HEADERS,
          credentials: "same-origin",
          body: JSON.stringify({ fixture_ref: selected, mode }),
        }),
      );
      if (!resp.ok) {
        setStatus("The check could not be run.");
        return;
      }
      const data: Run = await resp.json();
      setRun(data);
      window.history.replaceState(null, "", `?run=${encodeURIComponent(data.run_id)}`);
      setStatus(
        `Check ${data.status}: ${data.issues.length} issue(s) and ${data.notices.length} notice(s) for pharmacist review.`,
      );
    } catch {
      setStatus("The service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(issue: Issue, action: "confirm" | "dismiss", reason?: string) {
    if (!run) return;
    setBusy(true);
    try {
      const resp = handleAuth(
        await fetch(`/api/pharma/issues/${encodeURIComponent(issue.issue_id)}/${action}`, {
          method: "POST",
          headers: JSON_HEADERS,
          credentials: "same-origin",
          body: JSON.stringify(action === "dismiss" ? { reason } : {}),
        }),
      );
      if (resp.status === 409) {
        await loadRun(run.run_id, "This issue already has a recorded decision.");
        return;
      }
      if (!resp.ok) {
        setStatus("The decision could not be recorded.");
        return;
      }
      await loadRun(run.run_id, `Issue ${action === "confirm" ? "confirmed" : "dismissed"}: ${issueTitle(issue)}.`);
    } catch {
      setStatus("The service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const issues = run ? sortIssues(run.issues) : [];

  return (
    <section aria-labelledby="reconcile-title" className="pharma">
      <h1 id="reconcile-title">Medication reconciliation</h1>
      <p>{REVIEW_NOTE}</p>
      <p className="pharma-attribution" data-testid="nlm-attribution">
        {NLM_ATTRIBUTION}
      </p>

      <section aria-labelledby="run-title">
        <h2 id="run-title">Run a check</h2>
        <form className="pharma-form" onSubmit={onRun}>
          <div className="field">
            <label htmlFor="fixture">Synthetic patient</label>
            <select id="fixture" value={selected} onChange={(e) => setSelected(e.target.value)}>
              {fixtures.map((f) => (
                <option key={f.fixture_ref} value={f.fixture_ref}>
                  {f.fixture_ref} — {f.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="mode">Phrasing mode</label>
            <select id="mode" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="rules_plus_model">Rules + model phrasing</option>
              <option value="rules_only">Rules only</option>
            </select>
          </div>
          <button type="submit" disabled={busy || !selected}>
            Run check
          </button>
        </form>
      </section>

      <p role="status" aria-live="polite" className="pharma-status">
        {status}
      </p>

      {run && (
        <>
          <section aria-labelledby="issues-title">
            <h2 id="issues-title">Issues for pharmacist review ({issues.length})</h2>
            <p>
              Patient {run.patient_ref} · as of {run.as_of} · run {run.status} · {run.formulary_version} ·{" "}
              {run.rules_version}
              {run.excluded_future_items ? ` · ${run.excluded_future_items} item(s) after the decision time excluded` : ""}
            </p>
            {issues.length === 0 ? (
              <p>No issues were found by the rules. Notices, if any, are listed below.</p>
            ) : (
              <ol className="issue-list">
                {issues.map((issue, n) => (
                  <li key={issue.issue_id}>
                    <IssueCard
                      issue={issue}
                      index={n + 1}
                      busy={busy}
                      onConfirm={(i) => void decide(i, "confirm")}
                      onDismiss={(i, reason) => void decide(i, "dismiss", reason)}
                    />
                  </li>
                ))}
              </ol>
            )}
          </section>
          <section aria-labelledby="notices-title">
            <h2 id="notices-title">Notices ({run.notices.length})</h2>
            {run.notices.length === 0 ? (
              <p>No notices.</p>
            ) : (
              <ul className="notice-list">
                {run.notices.map((n) => (
                  <li key={n.notice_id}>
                    <strong>{NOTICE_LABELS[n.type] ?? n.type}</strong>: {n.detail}
                    {n.raw_span ? ` (“${n.raw_span}”)` : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}

export default function PharmaReconcile() {
  return (
    <RoleGuard role="pharmacist">
      <Reconcile />
    </RoleGuard>
  );
}
