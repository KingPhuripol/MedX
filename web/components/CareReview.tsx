"use client";

import { AlertOctagon, AlertTriangle } from "lucide-react";
import { FormEvent, useState } from "react";

import ScreeningBlock from "@/components/ScreeningBlock";
import ActionBar from "@/components/ui/ActionBar";
import { Button } from "@/components/ui/button";
import Notice from "@/components/ui/Notice";
import PageHeader from "@/components/ui/PageHeader";
import Section from "@/components/ui/Section";
import StatusChip from "@/components/ui/StatusChip";
import { formatThaiTime } from "@/lib/demo";
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

import styles from "./CareReview.module.css";

type Props = {
  assessment: Assessment;
  vocabulary: Vocabulary;
  /** Returns an error message, or null on success. */
  onReview: (action: ReviewAction, body: ReviewBody) => Promise<string | null>;
};

function Refs({ refs }: { refs: EvidenceRef[] }) {
  return (
    <details className={styles.refsBox}>
      <summary>ดูหลักฐานและที่มา (Evidence)</summary>
      <span className={styles.refs}>{refs.map(refText).join("; ")}</span>
    </details>
  );
}

/**
 * A filterable, scroll-capped vocabulary picker. Every checkbox stays in the DOM (same ids and label text):
 * the filter only hides non-matching rows that are not selected. Selected entries are listed first, in the order
 * they had when the picker opened (so a row does not jump under the pointer while it is being ticked).
 */
function CodePicker({
  legend,
  name,
  entries,
  chosen,
  max,
  onChange,
}: {
  legend: string;
  name: string;
  entries: VocabEntry[];
  chosen: string[];
  max: number;
  onChange: (codes: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [initial] = useState(chosen);
  const ordered = [
    ...entries.filter((e) => initial.includes(e.code)),
    ...entries.filter((e) => !initial.includes(e.code)),
  ];
  const q = query.trim().toLowerCase();
  const matches = (e: VocabEntry) =>
    !q || `${e.display} ${e.display_th} ${e.code}`.toLowerCase().includes(q);
  return (
    <fieldset className={styles.picker}>
      <legend>{legend}</legend>
      <div className={styles.pickerTools}>
        <label htmlFor={`${name}-filter`} className={styles.pickerFilterLabel}>
          ค้นหา / Filter
        </label>
        <input
          type="search"
          id={`${name}-filter`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.preventDefault();
          }}
          className={styles.pickerFilter}
        />
        <StatusChip tone="neutral">
          เลือก {chosen.length}/{max}
        </StatusChip>
      </div>
      <div className={styles.pickerList}>
        {ordered.map((e) => (
          <label
            key={e.code}
            htmlFor={`${name}-${e.code}`}
            className={styles.checkRow}
            hidden={!matches(e) && !chosen.includes(e.code)}
          >
            <input
              type="checkbox"
              id={`${name}-${e.code}`}
              checked={chosen.includes(e.code)}
              onChange={(ev) =>
                onChange(
                  ev.target.checked
                    ? [...chosen, e.code]
                    : chosen.filter((c) => c !== e.code),
                )
              }
            />
            <span>
              {e.display} <span lang="th">({e.display_th})</span> — {e.code}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function CareReview({
  assessment,
  vocabulary,
  onReview,
}: Props) {
  const a = assessment;
  const scr = a.red_flag_screening;
  const suggested = a.status === "suggested";
  const needsScreeningAck = scr.status !== "evaluated";
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [screeningAck, setScreeningAck] = useState(false);
  const [editNi, setEditNi] = useState<string[]>(
    a.next_information.map((x) => x.code),
  );
  const [editCp, setEditCp] = useState<string[]>(
    a.pathway_options.map((x) => x.code),
  );
  const [editReason, setEditReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const allAcked =
    a.alerts.every((x) => acked[x.rule_id]) &&
    (!needsScreeningAck || screeningAck);
  const ackIds = a.alerts.map((x) => x.rule_id).filter((id) => acked[id]);
  const ackTotal = a.alerts.length + (needsScreeningAck ? 1 : 0);
  const ackCount = ackIds.length + (needsScreeningAck && screeningAck ? 1 : 0);
  const reviewed = a.review_status !== "pending_review";
  const blocked = !allAcked || busy;
  const hint = allAcked ? undefined : "ack-hint";

  async function submit(
    event: FormEvent<HTMLFormElement>,
    action: ReviewAction,
    body: Partial<ReviewBody>,
  ) {
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
    <section
      aria-labelledby="care-title"
      className={`page-stack ${styles.page}`}
    >
      <PageHeader
        titleId="care-title"
        title={
          <>
            Care suggestion review — {a.case_id} at {a.decision_point}
          </>
        }
        subtitle={
          <span data-testid="output-label">
            <strong>{OUTPUT_LABEL}.</strong> Evidence available as of{" "}
            <time dateTime={a.as_of}>{formatThaiTime(a.as_of)}</time>.
          </span>
        }
        meta={
          <>
            <span>Rules {a.rules_version}</span>
            <span>
              Provider {a.provider ?? "not called"} {a.model_version ?? ""}
            </span>
          </>
        }
      />

      <Section
        tone="critical"
        title="Red-flag alerts and screening"
        titleId="redflag-title"
        data-testid="redflag-section"
      >
        <div className={styles.stack}>
          {a.alerts.length > 0 ? (
            <div role="alert" data-testid="alerts" className={styles.stack}>
              <p className={styles.escalate}>
                <AlertOctagon size={20} aria-hidden="true" />
                <span>
                  <strong>Escalate to a clinician now.</strong> These alerts
                  come from fixed rules, are computed before any suggestion and
                  cannot be changed by the model.
                </span>
              </p>
              <ul className={styles.alertList}>
                {a.alerts.map((x) => (
                  <li key={x.rule_id} className={styles.alertCard}>
                    <p className={styles.alertName}>
                      <StatusChip
                        tone="critical"
                        icon={<AlertOctagon size={16} aria-hidden="true" />}
                      >
                        Red flag · พบสัญญาณอันตราย
                      </StatusChip>{" "}
                      <strong>{x.name_en}</strong>{" "}
                      <span lang="th">({x.name_th})</span> — {x.rule_id}
                    </p>
                    <p>{x.message_en}</p>
                    <p lang="th">{x.message_th}</p>
                    <p className={styles.refs}>
                      Evidence: {x.evidence_refs.join(", ")}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Notice tone="info" data-testid="no-alert">
              No alert raised by the rules that ran. This is not an all-rules
              result: see the screening block below for what was and was not
              checked.
            </Notice>
          )}
          <ScreeningBlock screening={scr} staleText={CARE_STALE_TEXT} />
        </div>
      </Section>

      <Section
        title={`Suggestion (${a.status})`}
        titleId="suggestion-title"
        data-testid="suggestion-section"
      >
        <div className={styles.stack}>
          {suggested ? (
            <>
              <div className={styles.cols}>
                <div className={styles.col}>
                  <h3>Case summary</h3>
                  <ul data-testid="case-summary" className={styles.items}>
                    {a.case_summary.map((s, i) => (
                      <li key={i}>
                        {s.text} <Refs refs={s.evidence_refs} />
                      </li>
                    ))}
                  </ul>
                </div>
                <div className={styles.col}>
                  <h3>Information to collect next</h3>
                  {a.next_information.length ? (
                    <ol data-testid="next-information" className={styles.items}>
                      {a.next_information.map((x) => (
                        <li key={x.code}>
                          {x.display} <span lang="th">({x.display_th})</span> —{" "}
                          {x.code}. Sources: {x.source_refs.join(", ")}.{" "}
                          <Refs refs={x.evidence_refs} />
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p>
                      No next-information item matched the rules for this
                      snapshot.
                    </p>
                  )}
                  <h3>Care-pathway options to consider</h3>
                  {a.pathway_options.length ? (
                    <ul data-testid="pathway-options" className={styles.items}>
                      {a.pathway_options.map((x) => (
                        <li key={x.code}>
                          {x.display} <span lang="th">({x.display_th})</span> —{" "}
                          {x.code}. Sources: {x.source_refs.join(", ")}.{" "}
                          <Refs refs={x.evidence_refs} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>
                      No care-pathway option matched the rules for this
                      snapshot.
                    </p>
                  )}
                </div>
              </div>
              <p>
                <StatusChip tone="neutral">
                  Uncertainty: {a.uncertainty}
                </StatusChip>
              </p>
            </>
          ) : a.status === "abstained" ? (
            <Notice
              tone="warning"
              icon={<AlertTriangle size={20} />}
              data-testid="abstained"
            >
              <strong>No suggestion: required information is missing.</strong>{" "}
              The system abstained. Collect the items below and assess again.
            </Notice>
          ) : (
            <Notice
              tone="warning"
              icon={<AlertTriangle size={20} />}
              data-testid="status-error"
            >
              <strong>
                No suggestion is shown because the provider output failed
                validation ({a.reason}).
              </strong>{" "}
              The red-flag alerts and screening above are unaffected.
            </Notice>
          )}
          {a.missing_information.length ? (
            <Notice tone="warning" title="Missing information">
              <p>
                Not recorded or stated as unknown — never read as negative or
                normal.
              </p>
              <ul data-testid="missing-information" className={styles.missing}>
                {a.missing_information.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </Notice>
          ) : (
            <p data-testid="missing-information-none" className="muted">
              No optional input is absent.
            </p>
          )}
        </div>
      </Section>

      {reviewed ? (
        <Section title="Review result" titleId="result-title">
          <Notice
            tone={a.review_status === "rejected" ? "warning" : "success"}
            role="status"
            data-testid="review-result"
          >
            {a.review_status === "rejected"
              ? "Suggestion rejected. Nothing is care-facing."
              : `${a.review_status === "confirmed" ? "Confirmed" : "Edited"}: next information ${
                  final?.next_information.join(", ") || "none"
                }; pathway options ${final?.pathway_options.join(", ") || "none"}`}
            {a.review
              ? ` — by ${a.review.reviewer_role} #${a.review.reviewer_id} at ${a.review.ts_utc}`
              : ""}
          </Notice>
        </Section>
      ) : (
        <>
          <Section title="Physician review" titleId="review-title">
            <div className={styles.stack}>
              <fieldset data-testid="acknowledgements" className={styles.ack}>
                <legend>Acknowledge before reviewing</legend>
                {a.alerts.map((x) => (
                  <label
                    key={x.rule_id}
                    htmlFor={`ack-${x.rule_id}`}
                    className={styles.checkRow}
                  >
                    <input
                      type="checkbox"
                      id={`ack-${x.rule_id}`}
                      checked={!!acked[x.rule_id]}
                      onChange={(e) =>
                        setAcked({ ...acked, [x.rule_id]: e.target.checked })
                      }
                    />
                    <span>I have seen alert {x.rule_id}</span>
                  </label>
                ))}
                {needsScreeningAck && (
                  <label htmlFor="ack-screening" className={styles.checkRow}>
                    <input
                      type="checkbox"
                      id="ack-screening"
                      checked={screeningAck}
                      onChange={(e) => setScreeningAck(e.target.checked)}
                    />
                    <span>I have seen that {scr.banner?.toLowerCase()}</span>
                  </label>
                )}
                {!a.alerts.length && !needsScreeningAck && (
                  <p>Nothing to acknowledge.</p>
                )}
              </fieldset>
              {!allAcked && (
                <p id="ack-hint" className="muted">
                  Acknowledge every red-flag alert and the screening banner to
                  enable the review buttons.
                </p>
              )}
              {error && (
                <Notice tone="critical" role="alert">
                  {error}
                </Notice>
              )}
            </div>
          </Section>

          {suggested && (
            <ActionBar
              summary={
                <span className={styles.ackSummary}>
                  Acknowledged {ackCount}/{ackTotal}
                </span>
              }
            >
              <form
                id="confirm-form"
                onSubmit={(e) => submit(e, "confirm", {})}
              />
              <Button
                type="submit"
                form="confirm-form"
                disabled={blocked}
                aria-describedby={hint}
              >
                Confirm suggestion
              </Button>
            </ActionBar>
          )}

          <Section title="Edit or reject" titleId="alt-title">
            <div className={styles.stack}>
              <details className={styles.alt} open={!suggested}>
                <summary>Edit the suggestion (reason required)</summary>
                <div className={styles.stack}>
                  <form
                    className={styles.stack}
                    onSubmit={(e) =>
                      submit(e, "edit", {
                        next_information: editNi,
                        pathway_options: editCp,
                        reason: editReason,
                      })
                    }
                  >
                    <div className={styles.pickers}>
                      <CodePicker
                        legend="Edit: information to collect next (at most 5)"
                        name="edit-ni"
                        entries={vocabulary.next_information}
                        chosen={editNi}
                        max={5}
                        onChange={setEditNi}
                      />
                      <CodePicker
                        legend="Edit: care-pathway options (at most 3)"
                        name="edit-cp"
                        entries={vocabulary.pathway_options}
                        chosen={editCp}
                        max={3}
                        onChange={setEditCp}
                      />
                    </div>
                    <div className={styles.field}>
                      <label htmlFor="edit-reason">Reason for the edit</label>
                      <textarea
                        id="edit-reason"
                        rows={2}
                        value={editReason}
                        onChange={(e) => setEditReason(e.target.value)}
                        required
                      />
                    </div>
                    <div>
                      <Button
                        type="submit"
                        variant="secondary"
                        disabled={blocked}
                        aria-describedby={hint}
                      >
                        Save edited suggestion
                      </Button>
                    </div>
                  </form>
                </div>
              </details>
              <div className={styles.rejectBox}>
                <form
                  className={styles.stack}
                  onSubmit={(e) =>
                    submit(e, "reject", { reason: rejectReason })
                  }
                >
                  <div className={styles.field}>
                    <label htmlFor="reject-reason">Reason for rejecting</label>
                    <textarea
                      id="reject-reason"
                      rows={2}
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      required
                    />
                  </div>
                  <div>
                    <Button
                      type="submit"
                      variant="danger"
                      disabled={blocked}
                      aria-describedby={hint}
                    >
                      Reject suggestion
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </Section>
        </>
      )}
    </section>
  );
}
