"use client";

import { useState } from "react";

import { COPY, PROPOSED_V2C } from "@/lib/copy";
import type { RedFlag } from "@/lib/recorder";
import { submitFlow, type Decision, type ReviewPayload } from "@/lib/review";
import type { Patient } from "@/lib/roster";
import { hhmm, isoWithOffset } from "@/lib/time";
import { rows, type Row, type Scribe } from "@/lib/voice";

import { Icon } from "./Icon";
import { Limit } from "./Limit";

const R = COPY.review;

type Mode = "view" | "editing" | "rejecting" | "adding";

function sourceOf(row: Row, scribe: Scribe): { text: string; atMs: number } | null {
  for (const f of row.facts) {
    for (const id of f.span_turn_ids ?? []) {
      const t = scribe.turns.find((x) => x.turn_id === id);
      if (t) return { text: t.text, atMs: Date.parse(t.started_at) };
    }
  }
  return null;
}

function Tag({ kind }: { kind: keyof typeof R.tag }) {
  const cls = { waiting: "tag--wait", confirmed: "tag--ok", editing: "tag--warn", edited: "tag--warn", rejected: "tag--no", missing: "tag--no" }[kind];
  const icon = kind === "confirmed" ? "check" : kind === "editing" || kind === "edited" ? "pencil" : kind === "rejected" ? "x" : null;
  return (
    <span className={`tag ${cls}`}>
      {icon && <Icon name={icon} size="sm" />}
      {R.tag[kind]}
    </span>
  );
}

function decidedTag(d: Decision): keyof typeof R.tag {
  if (d.action === "reject") return "rejected";
  if (d.action === "edit" || d.action === "add") return "edited";
  return "confirmed";
}

function Item({
  row,
  scribe,
  decision,
  onDecide,
  locked,
}: {
  row: Row;
  scribe: Scribe;
  decision: Decision | undefined;
  onDecide: (d: Decision | undefined) => void;
  locked: boolean;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState<string | null>(null);
  const missing = row.state === "MISSING";
  const original = missing ? null : row.value;
  const src = sourceOf(row, scribe);
  const inputId = `v-${row.field}`;

  if (decision && mode === "view") {
    return (
      <li className="decided" data-field={row.field} data-decision={decision.action}>
        <div className="rv-top">
          <span className="rv-lead">
            <span className="t-meta b muted">{row.label}</span>
            <Tag kind={decidedTag(decision)} />
          </span>
          {!locked && (
            <button type="button" className="linkbtn" aria-label={`${R.change}${row.label}`} onClick={() => onDecide(undefined)}>
              {R.change}
            </button>
          )}
        </div>
        {decision.action === "reject" ? (
          <p className="t-body">
            <span className="rv-val--struck">{original}</span> <span className="t-meta muted">{R.rejectedNote}</span>
          </p>
        ) : (
          <p className="t-body b">{decision.value}</p>
        )}
        {decision.action === "edit" && original && <p className="t-meta muted">{R.heard(original)}</p>}
      </li>
    );
  }

  const quote = src && (
    <blockquote className="quote">
      <time className="num">{R.source(hhmm(src.atMs))}</time>“{src.text}”
    </blockquote>
  );

  if (mode === "editing" || mode === "adding") {
    const save = () => {
      const v = draft.trim();
      if (!v) return;
      onDecide({ field: row.field, action: mode === "adding" ? "add" : "edit", value: v, original });
      setMode("view");
    };
    return (
      <li data-field={row.field}>
        <div className="rv-top">
          <span className="t-meta b muted">{row.label}</span>
          <Tag kind="editing" />
        </div>
        {quote}
        <div className="field">
          <label htmlFor={inputId}>{R.editLabel}</label>
          <textarea id={inputId} className="textarea" value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
        </div>
        <div className="acts acts--2">
          <button type="button" className="btn" onClick={save} disabled={!draft.trim()}>
            {R.saveEdit}
          </button>
          <button type="button" className="btn" style={{ fontWeight: 400 }} onClick={() => setMode("view")}>
            {R.dismiss}
          </button>
        </div>
      </li>
    );
  }

  if (mode === "rejecting") {
    return (
      <li data-field={row.field}>
        <div className="rv-top">
          <span className="t-meta b muted">{row.label}</span>
          <Tag kind="waiting" />
        </div>
        <p className="t-title">{row.value}</p>
        {quote}
        <fieldset className="chips">
          <legend className="sr">{R.reject}</legend>
          {R.rejectReasons.map((r) => (
            <label key={r} className="chip">
              <input type="radio" className="sr" name={`reason-${row.field}`} checked={reason === r} onChange={() => setReason(r)} />
              {r}
            </label>
          ))}
        </fieldset>
        <div className="acts acts--2">
          <button
            type="button"
            className="btn"
            disabled={!reason}
            onClick={() => {
              onDecide({ field: row.field, action: "reject", value: null, original, reason: reason ?? undefined });
              setMode("view");
            }}
          >
            {R.rejectSave}
          </button>
          <button type="button" className="btn" style={{ fontWeight: 400 }} onClick={() => setMode("view")}>
            {R.dismiss}
          </button>
        </div>
      </li>
    );
  }

  if (missing) {
    return (
      <li data-field={row.field} data-status="missing">
        <div className="rv-top">
          <span className="t-meta b muted">{row.label}</span>
          <Tag kind="missing" />
        </div>
        <p className="t-body muted">{R.missingBody}</p>
        <div className="acts acts--2">
          <button
            type="button"
            className="btn"
            onClick={() => {
              setDraft("");
              setMode("adding");
            }}
          >
            {R.add}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => onDecide({ field: row.field, action: "unknown", value: COPY.rec.valueUnknown, original: null })}
          >
            {R.markUnknown}
          </button>
        </div>
      </li>
    );
  }

  return (
    <li data-field={row.field} data-status="waiting">
      <div className="rv-top">
        <span className="t-meta b muted">{row.label}</span>
        <Tag kind="waiting" />
      </div>
      <p className="t-title">{row.value}</p>
      {quote}
      <div className={row.negativeAllergy ? "acts acts--1" : "acts"}>
        <button type="button" className="btn" onClick={() => onDecide({ field: row.field, action: "confirm", value: row.value, original })}>
          <Icon name="check" size="sm" />
          {row.negativeAllergy ? R.confirmNoAllergy : R.confirm}
        </button>
        {row.negativeAllergy ? (
          <div className="acts acts--2">
            <EditReject onEdit={() => { setDraft(row.value); setMode("editing"); }} onReject={() => { setReason(null); setMode("rejecting"); }} />
          </div>
        ) : (
          <EditReject onEdit={() => { setDraft(row.value); setMode("editing"); }} onReject={() => { setReason(null); setMode("rejecting"); }} />
        )}
      </div>
    </li>
  );
}

function EditReject({ onEdit, onReject }: { onEdit: () => void; onReject: () => void }) {
  return (
    <>
      <button type="button" className="btn" onClick={onEdit}>
        <Icon name="pencil" size="sm" />
        {R.edit}
      </button>
      <button type="button" className="btn" onClick={onReject}>
        <Icon name="x" size="sm" />
        {R.reject}
      </button>
    </>
  );
}

export interface ReviewProps {
  patient: Patient;
  scribe: Scribe;
  durationMs: number;
  redFlag: RedFlag | null;
  ackAtMs: number | null;
  consentAtMs: number;
  onContinue: () => void;
  onSubmitted: () => void;
  onAuthLost: () => void;
}

type SubmitState = "idle" | "submitting" | "not_connected" | "error";

/** Review and confirm (SPEC §2.4, T10). Nothing reaches the case without a decision on every row. */
export function Review(props: ReviewProps) {
  const { scribe } = props;
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [submit, setSubmit] = useState<SubmitState>("idle");
  const [finished, setFinished] = useState(false);
  const list = rows(scribe);
  const decided = list.filter((r) => decisions[r.field]).length;
  const edited = Object.values(decisions).filter((d) => d.action === "edit" || d.action === "add").length;
  const ready = decided === list.length;
  const secs = Math.floor(props.durationMs / 1000);

  async function send() {
    if (!ready || submit === "submitting") return;
    setSubmit("submitting");
    const payload: ReviewPayload = {
      session_id: scribe.session.session_id,
      patient_ref: props.patient.id,
      decisions: list.map((r) => decisions[r.field]),
      consent_acknowledged_at: isoWithOffset(props.consentAtMs),
      red_flag_acknowledged_at: props.ackAtMs !== null ? isoWithOffset(props.ackAtMs) : null,
    };
    const r = await submitFlow(scribe.session.session_id, payload);
    if (r.finished) setFinished(true);
    if (r.outcome === "auth") return props.onAuthLost();
    if (r.outcome === "submitted") return props.onSubmitted();
    setSubmit(r.outcome);
  }

  return (
    <main className="screen">
      <header className="appbar">
        {!finished && (
          <button type="button" className="btn btn--ghost btn--link" onClick={props.onContinue}>
            <Icon name="chevron-left" />
            {R.back}
          </button>
        )}
      </header>

      {props.redFlag && props.ackAtMs !== null && (
        <div className="flag-strip" data-testid="ack-strip" style={{ marginTop: 8 }}>
          <Icon name="triangle-alert" />
          <span className="num">{COPY.rec.ackStrip(hhmm(props.ackAtMs))}</span>
        </div>
      )}

      <h1 className="t-display" style={{ marginTop: 8 }}>
        {R.title}
      </h1>
      <p className="t-meta muted num">{R.meta(props.patient.id, Math.floor(secs / 60), secs % 60)}</p>
      <p className="t-body" style={{ marginTop: 8 }}>
        {R.instruction}
      </p>

      <ul className="group review-list" style={{ marginTop: 24 }}>
        {list.map((r) => (
          <Item
            key={r.field}
            row={r}
            scribe={scribe}
            decision={decisions[r.field]}
            locked={submit === "submitting"}
            onDecide={(d) =>
              setDecisions((prev) => {
                const next = { ...prev };
                if (d) next[r.field] = d;
                else delete next[r.field];
                return next;
              })
            }
          />
        ))}
      </ul>

      <div className="bar">
        {submit === "not_connected" && (
          <div className="notice notice--warn" role="alert">
            <Icon name="triangle-alert" />
            <div>
              <strong>{PROPOSED_V2C.notConnected.head}</strong>
              {PROPOSED_V2C.notConnected.body}
            </div>
          </div>
        )}
        {submit === "error" && (
          <div className="notice notice--warn" role="alert">
            <Icon name="triangle-alert" />
            <div>
              <strong>{R.submitError.head}</strong>
              {R.submitError.body}
            </div>
          </div>
        )}
        <div className="bar-meta">
          <span className="b">{ready ? R.done : R.progress(decided)}</span>
          <span className="muted">{ready ? R.editedCount(edited) : R.progressHint}</span>
        </div>
        <button type="button" className="btn btn--primary btn--block" disabled={!ready || submit === "submitting"} onClick={send}>
          {ready && submit !== "submitting" && <Icon name="send" />}
          {submit === "submitting" ? R.submitting : submit === "error" ? R.retrySubmit : R.submit}
        </button>
        {ready && <p className="t-meta muted">{R.helper}</p>}
        <Limit />
      </div>
    </main>
  );
}

/** "ส่งเข้าเคสแล้ว": shown only after a 2xx from submitReview. */
export function Submitted({ patientId, onNext }: { patientId: string; onNext: () => void }) {
  const n = R.submitted(patientId);
  return (
    <main className="screen screen--fixed">
      <div className="done-screen">
        <h1 className="slot-head t-display" tabIndex={-1}>
          <Icon name="circle-check" size="lg" />
          {n.head}
        </h1>
        <p className="t-body">{n.body}</p>
      </div>
      <button type="button" className="btn btn--primary btn--block" onClick={onNext}>
        {R.next}
      </button>
      <Limit />
    </main>
  );
}
