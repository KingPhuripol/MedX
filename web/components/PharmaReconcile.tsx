"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import RoleGuard from "@/components/RoleGuard";
import {
  NLM_ATTRIBUTION,
  NOTICE_LABELS,
  NOT_STATED,
  PHRASING_LABEL,
  REVIEW_NOTE,
  SCOPE_COMPARED,
  SCOPE_NOT_CHECKED,
  SCOPE_READING,
  SOURCE_LABELS,
  formatDose,
  formatFrequency,
  issueLabel,
  notVerifiable,
  orNotStated,
  runSummary,
  sortIssues,
  type ExtractionRecord,
  type Fixture,
  type Issue,
  type Run,
} from "@/lib/pharma";

const JSON_HEADERS = { "Content-Type": "application/json" };

function issueTitle(issue: Issue): string {
  return `${issueLabel(issue)}: ${issue.ingredients.join(", ")}`;
}

function fieldStatusText(issue: Issue): string {
  const status = issue.detail?.field_status;
  if (status === "unverifiable") return notVerifiable(issue.detail?.unverifiable_reason);
  if (status === "not_recognised") return "not recognised";
  return NOT_STATED;
}

function ScopeSection() {
  return (
    <section aria-labelledby="scope-title" className="pharma-scope" data-testid="scope">
      <h2 id="scope-title">Scope of this check</h2>
      <p>{SCOPE_COMPARED}</p>
      <p>Not checked:</p>
      <ul>
        {SCOPE_NOT_CHECKED.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p>{SCOPE_READING}</p>
    </section>
  );
}

function AllergyBasis({ issue }: { issue: Issue }) {
  const d = issue.detail ?? {};
  if (!issue.type.startsWith("allergy_")) return null;
  return (
    <div className="issue-basis" data-testid="allergy-basis">
      <p>Basis: {d.basis ?? "not recorded"}</p>
      {issue.type === "allergy_class" && (
        <p>
          Class: {d.class_name} (class source: {d.class_source}; formulary {d.formulary_version})
        </p>
      )}
      {issue.type === "allergy_cross_reactivity" && (
        <>
          <p>Citation: {d.citation}</p>
          <p>
            Review status:{" "}
            {d.clinical_review_status === "pending_pharmacist" ? "pending pharmacist sign-off" : d.clinical_review_status}
          </p>
        </>
      )}
    </div>
  );
}

function RunSummary({ run }: { run: Run }) {
  const summary = runSummary(run);
  return (
    <p data-testid="unchecked-summary">
      {summary.text}
      {summary.complete && (
        <>
          {" "}
          See <a href="#scope-title">Scope of this check</a> for what is and is not compared.
        </>
      )}
    </p>
  );
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
        {issue.type === "missing_field" && issue.field ? ` · ${issue.field} ${fieldStatusText(issue)} in the first source listed` : ""}
      </p>
      <AllergyBasis issue={issue} />
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
            <th scope="col">Dose per administration</th>
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
              <td>{src.source_type === "allergy_record" || src.presence === "absent" ? "—" : formatFrequency(src)}</td>
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

function SourceTable({ record, index }: { record: ExtractionRecord; index: number }) {
  const label = SOURCE_LABELS[record.source_type] ?? record.source_type;
  const caption = `${label} as read (${record.evidence_ref}, available at ${record.available_at_time})`;
  if (record.status !== "ok" || !record.entries) {
    return (
      <p data-testid={`source-${index}`}>
        <strong>{caption}</strong>: could not be read ({record.failure_reason ?? "extraction failed"}). This list was not
        checked.
      </p>
    );
  }
  return (
    <table className="sources" data-testid={`source-${index}`}>
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Text as recorded</th>
          <th scope="col">Name read</th>
          <th scope="col">Matched ingredient(s)</th>
          <th scope="col">Dose per administration</th>
          <th scope="col">Route</th>
          <th scope="col">Frequency</th>
        </tr>
      </thead>
      <tbody>
        {record.entries.map((e, n) => (
          <tr key={`${record.evidence_ref}-${n}`}>
            <th scope="row">
              {e.source_text}
              {e.discontinue_intent ? " (intended to end)" : ""}
            </th>
            <td>{e.drug_name_raw}</td>
            <td>{e.recognised ? e.ingredients.join(", ") : "not recognised"}</td>
            <td>{formatDose(e)}</td>
            <td>{orNotStated(e.route)}</td>
            <td>{formatFrequency(e)}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
      const unchecked = data.unchecked_comparisons ?? 0;
      setStatus(
        `Check ${data.status}: ${data.issues.length} issue(s) and ${data.notices.length} notice(s) for pharmacist review` +
          (unchecked ? `; ${unchecked} comparison(s) could not be checked.` : "."),
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

      <ScopeSection />

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
            <RunSummary run={run} />
            {issues.length === 0 ? (
              <p>
                No discrepancies were found by the rules among the fields that could be compared. This is not a
                confirmation that the lists agree; check the notices and the lists below.
              </p>
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
          <section aria-labelledby="lists-title">
            <h2 id="lists-title">Medication lists as read ({run.extraction?.length ?? 0})</h2>
            <p>
              Every source list with the fields read from each line. A field shown as “{NOT_STATED}”, “not recognised” or
              “not verifiable” was not compared.
            </p>
            {(run.extraction ?? []).map((record, n) => (
              <SourceTable key={record.evidence_ref} record={record} index={n + 1} />
            ))}
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
