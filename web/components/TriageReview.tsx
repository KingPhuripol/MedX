"use client";

import { AlertOctagon, CheckCircle2, Info } from "lucide-react";
import { FormEvent, useState } from "react";

import ScreeningBlock from "@/components/ScreeningBlock";
import { ActionBar } from "@/components/ui/ActionBar";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatThaiTime } from "@/lib/demo";
import {
  OUTPUT_LABEL,
  type Assessment,
  type Department,
  type ReviewAction,
  type ReviewBody,
} from "@/lib/triage";

import css from "./TriageReview.module.css";

type Props = {
  assessment: Assessment;
  departments: Department[];
  /** Returns an error message, or null on success. */
  onReview: (action: ReviewAction, body: ReviewBody) => Promise<string | null>;
};

function localTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : formatThaiTime(iso);
}

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

  const describedBy = allAcked ? undefined : "ack-hint";

  return (
    <div className={`page-stack ${css.page}`}>
      <PageHeader
        titleId="triage-title"
        title={`Triage review — ${a.case_ref}`}
        subtitle={<strong>{OUTPUT_LABEL}.</strong>}
        meta={
          <>
            <span>Evidence as of {localTime(a.as_of)}</span>
            <span>Red-flag rules {a.ruleset_version}</span>
          </>
        }
      />

      <Section
        tone={a.alerts.length ? "critical" : "default"}
        title={
          <span className={css.titleRow}>
            {a.alerts.length ? <AlertOctagon size={24} aria-hidden="true" /> : null}
            Red-flag alerts
          </span>
        }
        titleId="alerts-title"
        role={a.alerts.length ? "alert" : undefined}
        data-testid="alerts-section"
        actions={
          a.alerts.length ? <StatusChip tone="critical">พบสัญญาณอันตราย {a.alerts.length}</StatusChip> : undefined
        }
      >
        {a.alerts.length ? (
          <>
            <p className={css.flat}>
              <strong>Escalate to a clinician now.</strong> These alerts come from fixed rules and take priority over
              the department suggestion.
            </p>
            <ul className={css.list}>
              {a.alerts.map((x) => (
                <li key={x.rule_id} className={css.alertCard}>
                  <p className={css.alertName}>
                    <strong>{x.name_en}</strong> <span lang="th">({x.name_th})</span> — {x.rule_id}
                  </p>
                  <div className={css.msgs}>
                    <p className={css.flat}>{x.message_en}</p>
                    <p className={css.flat} lang="th">
                      {x.message_th}
                    </p>
                  </div>
                  <p className={css.evidence}>Evidence: {x.evidence_refs.join(", ")}</p>
                  {!reviewed && (
                    <label className={css.ackRow} htmlFor={`ack-${x.rule_id}`}>
                      <input
                        type="checkbox"
                        id={`ack-${x.rule_id}`}
                        checked={!!acked[x.rule_id]}
                        onChange={(e) => setAcked({ ...acked, [x.rule_id]: e.target.checked })}
                      />
                      <span>I have seen alert {x.rule_id}</span>
                    </label>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className={css.flat} data-testid="alerts-none">
            Nothing to acknowledge. This is not a negative screen: see the red-flag screening block for which
            rules were evaluated and their scope.
          </p>
        )}
        {a.not_evaluable.length > 0 && (
          <div className={css.notEval}>
            <h3>Rules not checked — data missing (not a negative result)</h3>
            <ul data-testid="not-evaluable" className={css.plainList}>
              {a.not_evaluable.map((n) => (
                <li key={n.rule_id}>
                  {n.name_en} ({n.rule_id}): missing {n.missing_inputs.join(", ")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      <ScreeningBlock screening={a.screening} />

      <Section
        title={`Department — ${OUTPUT_LABEL.toLowerCase()}`}
        titleId="dept-title"
        data-testid="department-section"
      >
        {suggested ? (
          <div className={css.deptGrid}>
            <ol data-testid="department-ranking" className={css.ranking}>
              {dept.top3.map((d) => (
                <li key={d.code}>
                  <span>
                    <strong>{d.label_en}</strong> <span lang="th">({d.label_th})</span>
                  </span>{" "}
                  <span>— score {d.score.toFixed(2)}</span>
                  <span className={css.evidence}>Evidence: {d.evidence_refs.join(", ")}</span>
                </li>
              ))}
            </ol>
            <div className={css.uncertainty}>
              <StatusChip tone={dept.uncertainty === "low" ? "info" : "warning"} icon={<Info size={16} aria-hidden="true" />}>
                Uncertainty: {dept.uncertainty} ({dept.uncertainty_label})
              </StatusChip>
            </div>
          </div>
        ) : (
          <>
            <p className={css.flat}>
              No department ranking is shown (status: {dept.status}). Choose a department manually below.
            </p>
            {dept.missing_information.length > 0 && (
              <Notice tone="warning" title="Missing information">
                <ul data-testid="missing-information" className={css.plainList}>
                  {dept.missing_information.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </Notice>
            )}
          </>
        )}
      </Section>

      {reviewed ? (
        <Section title="Review result" titleId="result-title">
          <Notice tone="success" icon={<CheckCircle2 size={24} aria-hidden="true" />}>
            <p role="status" data-testid="review-result">
              {a.review_status === "rejected"
                ? "Suggestion rejected. No department was sent."
                : `Confirmed department: ${label(a.confirmed_department)} (${a.review_status})`}
              {a.review ? ` — by ${a.review.reviewer_role} #${a.review.reviewer_id} at ${a.review.ts_utc}` : ""}
            </p>
          </Notice>
        </Section>
      ) : (
        <Section title="Nurse review" titleId="review-title">
          {!allAcked && (
            <p id="ack-hint" className={css.flat}>
              Acknowledge every red-flag alert above to enable the review buttons.
            </p>
          )}
          <div className={css.actions3}>
            {suggested && (
              <form id="confirm-form" className={css.actionCard} onSubmit={(e) => submit(e, "confirm", { department_code: choice })}>
                <fieldset className={css.fieldset}>
                  <legend>Confirm a suggested department</legend>
                  {dept.top3.map((d) => (
                    <label key={d.code} className={css.radioRow} htmlFor={`confirm-${d.code}`}>
                      <input
                        type="radio"
                        name="confirm-dept"
                        id={`confirm-${d.code}`}
                        value={d.code}
                        checked={choice === d.code}
                        onChange={() => setChoice(d.code)}
                      />
                      <span>{d.label_en}</span>
                    </label>
                  ))}
                </fieldset>
                <p className={css.evidence}>ปุ่มยืนยันอยู่ในแถบด้านล่างของหน้า</p>
              </form>
            )}
            <form className={css.actionCard} onSubmit={(e) => submit(e, "edit", { department_code: editCode, reason: editReason })}>
              <h3>Edit</h3>
              <Field label="Choose another department" htmlFor="edit-dept">
                <select id="edit-dept" value={editCode} onChange={(e) => setEditCode(e.target.value)} required>
                  <option value="">Select…</option>
                  {departments.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.label_en} ({d.label_th})
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Reason for the change" htmlFor="edit-reason">
                <textarea id="edit-reason" value={editReason} onChange={(e) => setEditReason(e.target.value)} required />
              </Field>
              <Button variant="secondary" type="submit" disabled={blocked} aria-describedby={describedBy}>
                Save edited department
              </Button>
            </form>
            <form className={`${css.actionCard} ${css.rejectCard}`} onSubmit={(e) => submit(e, "reject", { reason: rejectReason })}>
              <h3>Reject</h3>
              <Field label="Reason for rejecting" htmlFor="reject-reason">
                <textarea
                  id="reject-reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  required
                />
              </Field>
              <Button variant="danger" type="submit" disabled={blocked} aria-describedby={describedBy}>
                Reject suggestion
              </Button>
            </form>
          </div>
          {error && (
            <Notice tone="critical" role="alert" icon={<AlertOctagon size={24} aria-hidden="true" />}>
              <p>{error}</p>
            </Notice>
          )}
        </Section>
      )}

      {!reviewed && suggested && (
        <ActionBar
          pinAfter="alerts-title"
          summary={
            a.alerts.length
              ? `รับทราบ red flag แล้ว ${ackIds.length}/${a.alerts.length}`
              : a.screening?.status !== "evaluated"
                ? "การคัดกรอง red flag ไม่ครบหรือไม่ได้ทำ — ต้องประเมินผู้ป่วยโดยตรง"
                : "ไม่มีรายการที่ต้องรับทราบ"
          }
        >
          <Button type="submit" form="confirm-form" disabled={blocked} aria-describedby={describedBy}>
            Confirm department
          </Button>
        </ActionBar>
      )}
    </div>
  );
}
