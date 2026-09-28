"use client";

import { FormEvent, useState } from "react";

import ScreeningBlock from "@/components/ScreeningBlock";
import {
  CARE_STALE_TEXT,
  OUTPUT_LABEL,
  refText,
  type Assessment,
  type EvidenceRef,
  type ReviewAction,
  type ReviewBody,
  type VocabEntry,
  type Vocabulary,
} from "@/lib/care";

type Props = {
  assessment: Assessment;
  vocabulary: Vocabulary;
  /** Returns an error message, or null on success. */
  onReview: (action: ReviewAction, body: ReviewBody) => Promise<string | null>;
};

function Refs({ refs }: { refs: EvidenceRef[] }) {
  return <span className="meta">Evidence: {refs.map(refText).join("; ")}</span>;
}

function CodePicker({
  legend,
  name,
  entries,
  chosen,
  onChange,
}: {
  legend: string;
  name: string;
  entries: VocabEntry[];
  chosen: string[];
  onChange: (codes: string[]) => void;
}) {
  return (
    <fieldset>
      <legend>{legend}</legend>
      {entries.map((e) => (
        <p key={e.code}>
          <input
            type="checkbox"
            id={`${name}-${e.code}`}
            checked={chosen.includes(e.code)}
            onChange={(ev) => onChange(ev.target.checked ? [...chosen, e.code] : chosen.filter((c) => c !== e.code))}
          />{" "}
          <label htmlFor={`${name}-${e.code}`}>
            {e.display} <span lang="th">({e.display_th})</span> — {e.code}
          </label>
        </p>
      ))}
    </fieldset>
  );
}

export default function CareReview({ assessment, vocabulary, onReview }: Props) {
  const a = assessment;
  const scr = a.red_flag_screening;
  const suggested = a.status === "suggested";
  const needsScreeningAck = scr.status !== "evaluated";
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [screeningAck, setScreeningAck] = useState(false);
  const [editNi, setEditNi] = useState<string[]>(a.next_information.map((x) => x.code));
  const [editCp, setEditCp] = useState<string[]>(a.pathway_options.map((x) => x.code));
  const [editReason, setEditReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const allAcked = a.alerts.every((x) => acked[x.rule_id]) && (!needsScreeningAck || screeningAck);
  const ackIds = a.alerts.map((x) => x.rule_id).filter((id) => acked[id]);
  const reviewed = a.review_status !== "pending_review";
  const blocked = !allAcked || busy;
  const hint = allAcked ? undefined : "ack-hint";

  async function submit(event: FormEvent<HTMLFormElement>, action: ReviewAction, body: Partial<ReviewBody>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const message = await onReview(action, {
      ...body,
      acknowledged_alert_ids: ackIds,
      screening_acknowledged: screeningAck,
    });
    setBusy(false);
    if (message) setError(message);
  }

  const final = a.review?.final_codes;

  return (
    <section aria-labelledby="care-title">
      <h1 id="care-title">
        Care suggestion review — {a.case_id} at {a.decision_point}
      </h1>
      <p data-testid="output-label">
        <strong>{OUTPUT_LABEL}.</strong> Evidence available as of {a.as_of}. Rules {a.rules_version}; provider{" "}
        {a.provider ?? "not called"} {a.model_version ?? ""}.
      </p>

      <section aria-labelledby="redflag-title" data-testid="redflag-section">
        <h2 id="redflag-title">Red-flag alerts and screening</h2>
        {a.alerts.length > 0 ? (
          <div role="alert" data-testid="alerts">
            <p>
              <span aria-hidden="true">⚠ </span>
              <strong>Escalate to a clinician now.</strong> These alerts come from fixed rules, are computed before
              any suggestion and cannot be changed by the model.
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
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p data-testid="no-alert">
            No alert raised by the rules that ran. This is not an all-rules result: see the screening block below
            for what was and was not checked.
          </p>
        )}
        <ScreeningBlock screening={scr} staleText={CARE_STALE_TEXT} />
      </section>

      <section aria-labelledby="suggestion-title" data-testid="suggestion-section">
        <h2 id="suggestion-title">Suggestion ({a.status})</h2>
        {suggested ? (
          <>
            <h3>Case summary</h3>
            <ul data-testid="case-summary">
              {a.case_summary.map((s, i) => (
                <li key={i}>
                  {s.text} <Refs refs={s.evidence_refs} />
                </li>
              ))}
            </ul>
            <h3>Information to collect next</h3>
            {a.next_information.length ? (
              <ol data-testid="next-information">
                {a.next_information.map((x) => (
                  <li key={x.code}>
                    {x.display} <span lang="th">({x.display_th})</span> — {x.code}. Sources: {x.source_refs.join(", ")}
                    . <Refs refs={x.evidence_refs} />
                  </li>
                ))}
              </ol>
            ) : (
              <p>No next-information item matched the rules for this snapshot.</p>
            )}
            <h3>Care-pathway options to consider</h3>
            {a.pathway_options.length ? (
              <ul data-testid="pathway-options">
                {a.pathway_options.map((x) => (
                  <li key={x.code}>
                    {x.display} <span lang="th">({x.display_th})</span> — {x.code}. Sources: {x.source_refs.join(", ")}
                    . <Refs refs={x.evidence_refs} />
                  </li>
                ))}
              </ul>
            ) : (
              <p>No care-pathway option matched the rules for this snapshot.</p>
            )}
            <p>Uncertainty: {a.uncertainty}</p>
          </>
        ) : a.status === "abstained" ? (
          <p data-testid="abstained">
            <strong>No suggestion: required information is missing.</strong> The system abstained. Collect the items
            below and assess again.
          </p>
        ) : (
          <p data-testid="status-error">
            <strong>No suggestion is shown because the provider output failed validation ({a.reason}).</strong> The
            red-flag alerts and screening above are unaffected.
          </p>
        )}
        <h3>Missing information</h3>
        {a.missing_information.length ? (
          <>
            <p>Not recorded or stated as unknown — never read as negative or normal.</p>
            <ul data-testid="missing-information">
              {a.missing_information.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </>
        ) : (
          <p data-testid="missing-information-none">No optional input is absent.</p>
        )}
      </section>

      {reviewed ? (
        <section aria-labelledby="result-title">
          <h2 id="result-title">Review result</h2>
          <p role="status" data-testid="review-result">
            {a.review_status === "rejected"
              ? "Suggestion rejected. Nothing is care-facing."
              : `${a.review_status === "confirmed" ? "Confirmed" : "Edited"}: next information ${
                  final?.next_information.join(", ") || "none"
                }; pathway options ${final?.pathway_options.join(", ") || "none"}`}
            {a.review ? ` — by ${a.review.reviewer_role} #${a.review.reviewer_id} at ${a.review.ts_utc}` : ""}
          </p>
        </section>
      ) : (
        <section aria-labelledby="review-title">
          <h2 id="review-title">Physician review</h2>
          <fieldset data-testid="acknowledgements">
            <legend>Acknowledge before reviewing</legend>
            {a.alerts.map((x) => (
              <p key={x.rule_id}>
                <input
                  type="checkbox"
                  id={`ack-${x.rule_id}`}
                  checked={!!acked[x.rule_id]}
                  onChange={(e) => setAcked({ ...acked, [x.rule_id]: e.target.checked })}
                />{" "}
                <label htmlFor={`ack-${x.rule_id}`}>I have seen alert {x.rule_id}</label>
              </p>
            ))}
            {needsScreeningAck && (
              <p>
                <input
                  type="checkbox"
                  id="ack-screening"
                  checked={screeningAck}
                  onChange={(e) => setScreeningAck(e.target.checked)}
                />{" "}
                <label htmlFor="ack-screening">I have seen that {scr.banner?.toLowerCase()}</label>
              </p>
            )}
            {!a.alerts.length && !needsScreeningAck && <p>Nothing to acknowledge.</p>}
          </fieldset>
          {!allAcked && (
            <p id="ack-hint">Acknowledge every red-flag alert and the screening banner to enable the review buttons.</p>
          )}
          {suggested && (
            <form onSubmit={(e) => submit(e, "confirm", {})}>
              <button type="submit" disabled={blocked} aria-describedby={hint}>
                Confirm suggestion
              </button>
            </form>
          )}
          <form onSubmit={(e) => submit(e, "edit", { next_information: editNi, pathway_options: editCp, reason: editReason })}>
            <CodePicker
              legend="Edit: information to collect next (at most 5)"
              name="edit-ni"
              entries={vocabulary.next_information}
              chosen={editNi}
              onChange={setEditNi}
            />
            <CodePicker
              legend="Edit: care-pathway options (at most 3)"
              name="edit-cp"
              entries={vocabulary.pathway_options}
              chosen={editCp}
              onChange={setEditCp}
            />
            <div className="field">
              <label htmlFor="edit-reason">Reason for the edit</label>
              <textarea id="edit-reason" value={editReason} onChange={(e) => setEditReason(e.target.value)} required />
            </div>
            <button type="submit" disabled={blocked} aria-describedby={hint}>
              Save edited suggestion
            </button>
          </form>
          <form onSubmit={(e) => submit(e, "reject", { reason: rejectReason })}>
            <div className="field">
              <label htmlFor="reject-reason">Reason for rejecting</label>
              <textarea id="reject-reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} required />
            </div>
            <button type="submit" disabled={blocked} aria-describedby={hint}>
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
