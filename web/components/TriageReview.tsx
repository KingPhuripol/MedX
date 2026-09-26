"use client";

import { FormEvent, useState } from "react";

import {
  OUTPUT_LABEL,
  type Assessment,
  type Department,
  type ReviewAction,
  type ReviewBody,
} from "@/lib/triage";

type Props = {
  assessment: Assessment;
  departments: Department[];
  /** Returns an error message, or null on success. */
  onReview: (action: ReviewAction, body: ReviewBody) => Promise<string | null>;
};

export default function TriageReview({ assessment, departments, onReview }: Props) {
  const a = assessment;
  const dept = a.department;
  const suggested = dept.status === "suggested" && dept.top3.length > 0;
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [choice, setChoice] = useState(suggested ? dept.top3[0].code : "");
  const [editCode, setEditCode] = useState("");
  const [editReason, setEditReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const allAcked = a.alerts.every((x) => acked[x.rule_id]);
  const ackIds = a.alerts.map((x) => x.rule_id).filter((id) => acked[id]);
  const reviewed = a.review_status !== "pending_review";
  const blocked = !allAcked || busy;

  async function submit(event: FormEvent<HTMLFormElement>, action: ReviewAction, body: Omit<ReviewBody, "acknowledged_alert_ids">) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const message = await onReview(action, { ...body, acknowledged_alert_ids: ackIds });
    setBusy(false);
    if (message) setError(message);
  }

  const label = (code: string | null) => {
    const d = departments.find((x) => x.code === code);
    return d ? `${d.label_en} (${d.label_th})` : code ?? "none";
  };

  return (
    <section aria-labelledby="triage-title">
      <h1 id="triage-title">Triage review — {a.case_ref}</h1>
      <p>
        <strong>{OUTPUT_LABEL}.</strong> Evidence as of {a.as_of}. Red-flag rules {a.ruleset_version}.
      </p>

      <section
        aria-labelledby="alerts-title"
        role={a.alerts.length ? "alert" : undefined}
        data-testid="alerts-section"
      >
        <h2 id="alerts-title">Red-flag alerts</h2>
        {a.alerts.length ? (
          <>
            <p>
              <strong>Escalate to a clinician now.</strong> These alerts come from fixed rules and take priority
              over the department suggestion.
            </p>
            <ul>
              {a.alerts.map((x) => (
                <li key={x.rule_id}>
                  <p>
                    <strong>{x.name_en}</strong> <span lang="th">({x.name_th})</span> — {x.rule_id}
                  </p>
                  <p>{x.message_en}</p>
                  <p lang="th">{x.message_th}</p>
                  <p>Evidence: {x.evidence_refs.join(", ")}</p>
                  {!reviewed && (
                    <p>
                      <input
                        type="checkbox"
                        id={`ack-${x.rule_id}`}
                        checked={!!acked[x.rule_id]}
                        onChange={(e) => setAcked({ ...acked, [x.rule_id]: e.target.checked })}
                      />{" "}
                      <label htmlFor={`ack-${x.rule_id}`}>I have seen alert {x.rule_id}</label>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p>No red-flag rule fired on the data recorded so far.</p>
        )}
        {a.not_evaluable.length > 0 && (
          <>
            <h3>Rules not checked — data missing (not a negative result)</h3>
            <ul data-testid="not-evaluable">
              {a.not_evaluable.map((n) => (
                <li key={n.rule_id}>
                  {n.name_en} ({n.rule_id}): missing {n.missing_inputs.join(", ")}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="dept-title" data-testid="department-section">
        <h2 id="dept-title">Department — {OUTPUT_LABEL.toLowerCase()}</h2>
        {suggested ? (
          <>
            <ol data-testid="department-ranking">
              {dept.top3.map((d) => (
                <li key={d.code}>
                  {d.label_en} <span lang="th">({d.label_th})</span> — score {d.score.toFixed(2)}; evidence:{" "}
                  {d.evidence_refs.join(", ")}
                </li>
              ))}
            </ol>
            <p>
              Uncertainty: {dept.uncertainty} ({dept.uncertainty_label})
            </p>
          </>
        ) : (
          <>
            <p>No department ranking is shown (status: {dept.status}). Choose a department manually below.</p>
            {dept.missing_information.length > 0 && (
              <>
                <h3>Missing information</h3>
                <ul data-testid="missing-information">
                  {dept.missing_information.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </section>

      {reviewed ? (
        <section aria-labelledby="result-title">
          <h2 id="result-title">Review result</h2>
          <p role="status" data-testid="review-result">
            {a.review_status === "rejected"
              ? "Suggestion rejected. No department was sent."
              : `Confirmed department: ${label(a.confirmed_department)} (${a.review_status})`}
            {a.review ? ` — by ${a.review.reviewer_role} #${a.review.reviewer_id} at ${a.review.ts_utc}` : ""}
          </p>
        </section>
      ) : (
        <section aria-labelledby="review-title">
          <h2 id="review-title">Nurse review</h2>
          {!allAcked && <p id="ack-hint">Acknowledge every red-flag alert above to enable the review buttons.</p>}
          {suggested && (
            <form onSubmit={(e) => submit(e, "confirm", { department_code: choice })}>
              <fieldset>
                <legend>Confirm a suggested department</legend>
                {dept.top3.map((d) => (
                  <p key={d.code}>
                    <input
                      type="radio"
                      name="confirm-dept"
                      id={`confirm-${d.code}`}
                      value={d.code}
                      checked={choice === d.code}
                      onChange={() => setChoice(d.code)}
                    />{" "}
                    <label htmlFor={`confirm-${d.code}`}>{d.label_en}</label>
                  </p>
                ))}
              </fieldset>
              <button type="submit" disabled={blocked} aria-describedby={allAcked ? undefined : "ack-hint"}>
                Confirm department
              </button>
            </form>
          )}
          <form onSubmit={(e) => submit(e, "edit", { department_code: editCode, reason: editReason })}>
            <div className="field">
              <label htmlFor="edit-dept">Choose another department</label>
              <select id="edit-dept" value={editCode} onChange={(e) => setEditCode(e.target.value)} required>
                <option value="">Select…</option>
                {departments.map((d) => (
                  <option key={d.code} value={d.code}>
                    {d.label_en} ({d.label_th})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="edit-reason">Reason for the change</label>
              <textarea id="edit-reason" value={editReason} onChange={(e) => setEditReason(e.target.value)} required />
            </div>
            <button type="submit" disabled={blocked} aria-describedby={allAcked ? undefined : "ack-hint"}>
              Save edited department
            </button>
          </form>
          <form onSubmit={(e) => submit(e, "reject", { reason: rejectReason })}>
            <div className="field">
              <label htmlFor="reject-reason">Reason for rejecting</label>
              <textarea
                id="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                required
              />
            </div>
            <button type="submit" disabled={blocked} aria-describedby={allAcked ? undefined : "ack-hint"}>
              Reject suggestion
            </button>
          </form>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </section>
      )}
    </section>
  );
}
