"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { COPY, FIELD_LABELS, PROPOSED_V2C, type Notice } from "@/lib/copy";
import type { ErrorKind, RecSnapshot, RecState, Recorder } from "@/lib/recorder";
import type { Patient } from "@/lib/roster";
import { clock, hhmm } from "@/lib/time";
import { allComplete, capturedCount, rows, type Row } from "@/lib/voice";

import { Icon, type IconName } from "./Icon";
import { Limit } from "./Limit";
import { Sheet } from "./Sheet";

export function patientMeta(p: Patient): string {
  return [p.sex && p.age !== undefined ? COPY.start.sexAge(p.sex, p.age) : null, p.bed].filter(Boolean).join(" · ");
}

interface ButtonSpec {
  icon: IconName;
  label: string;
  aria: string;
  disabled: boolean;
  spin?: boolean;
  fill?: boolean;
  live?: boolean;
}

const B = COPY.rec.button;

/** SPEC §3.1 table: centre button icon, label and aria-label per record state. */
export function recButton(rec: RecState): ButtonSpec {
  switch (rec) {
    case "idle":
      return { icon: "mic", label: B.start, aria: B.start, disabled: false };
    case "requesting_permission":
      return { icon: "mic", label: B.requesting, aria: B.requesting, disabled: true };
    case "connecting":
      return { icon: "loader", label: B.connecting, aria: B.connecting, disabled: true, spin: true };
    case "listening":
      return { icon: "pause", label: B.pause, aria: COPY.rec.ariaPause, disabled: false, fill: true, live: true };
    case "paused":
      return { icon: "mic", label: B.resume, aria: B.resume, disabled: false };
    case "reconnecting":
      return { icon: "loader", label: B.connecting, aria: COPY.rec.ariaReconnecting, disabled: true, spin: true };
    case "error":
      return { icon: "rotate-ccw", label: B.retry, aria: COPY.rec.ariaRetry, disabled: false };
    case "permission_denied":
      return { icon: "mic-off", label: B.askAgain, aria: B.askAgain, disabled: false };
    case "finishing":
      return { icon: "loader", label: COPY.rec.status.finishing, aria: COPY.rec.status.finishing, disabled: true };
  }
}

const STATUS_ICON: Record<RecState, { icon: IconName | "meter"; warn?: boolean; spin?: boolean }> = {
  idle: { icon: "mic" },
  requesting_permission: { icon: "mic" },
  connecting: { icon: "loader", spin: true },
  listening: { icon: "meter" },
  paused: { icon: "pause" },
  reconnecting: { icon: "wifi-off", warn: true },
  error: { icon: "mic-off", warn: true },
  permission_denied: { icon: "mic-off", warn: true },
  finishing: { icon: "loader", spin: true },
};

function errorNotice(kind: ErrorKind | null, captured: number): Notice {
  switch (kind) {
    case "no_mic":
      return COPY.rec.noMic;
    case "voice_unavailable":
      return PROPOSED_V2C.voiceUnavailable;
    case "access_code":
      return PROPOSED_V2C.accessCodeInvalid;
    case "session_ended":
      return PROPOSED_V2C.sessionEnded;
    default:
      return COPY.rec.error(captured);
  }
}

const METER_REST = [0.375, 0.75, 1, 0.5, 0.25]; // the comp's 6/12/16/8/4 px bars
const METER_WEIGHT = [0.5, 0.8, 1, 0.7, 0.4];

/** Level meter: transform-only bars from real input RMS at ~12 fps; static under reduced motion. */
function Meter({ recorder, live }: { recorder: Recorder; live: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const bars = Array.from(ref.current?.querySelectorAll("i") ?? []);
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!live || reduce || !recorder.hasMeter()) return;
    const id = setInterval(() => {
      const level = recorder.getLevel();
      bars.forEach((b, i) => {
        b.style.transform = `scaleY(${Math.max(0.2, Math.min(1, level * 1.6 * METER_WEIGHT[i]))})`;
      });
    }, 83);
    return () => {
      clearInterval(id);
      bars.forEach((b, i) => (b.style.transform = `scaleY(${METER_REST[i]})`));
    };
  }, [recorder, live]);
  return (
    <span className="meter" aria-hidden="true" ref={ref} data-testid="meter">
      {METER_REST.map((s, i) => (
        <i key={i} style={{ transform: `scaleY(${s})` }} />
      ))}
    </span>
  );
}

function Clock({ snap }: { snap: RecSnapshot }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (snap.clockSince === null) return;
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [snap.clockSince]);
  const ms = snap.clockMs + (snap.clockSince === null ? 0 : Date.now() - snap.clockSince);
  return <span className="clock num">{clock(ms)}</span>;
}

function FactRow({ row }: { row: Row }) {
  const glyph =
    row.status === "captured"
      ? { cls: "ok", icon: "circle-check" as const, label: COPY.rec.glyphCaptured }
      : row.status === "asking"
        ? { cls: "asking", icon: "circle-dot" as const, label: COPY.rec.glyphAsking }
        : { cls: "open", icon: "circle-dashed" as const, label: COPY.rec.glyphMissing };
  return (
    <li className="fact" data-field={row.field} data-status={row.status}>
      <span className={glyph.cls}>
        <Icon name={glyph.icon} label={glyph.label} />
      </span>
      <span className="lbl">{row.label}</span>
      {row.status === "asking" ? (
        <span className="val--asking">{row.value}</span>
      ) : (
        <span key={row.value} className={row.status === "captured" ? "val" : "val val--empty"}>
          {row.value}
        </span>
      )}
    </li>
  );
}

function NoticeBox({ notice, icon, tone, spin }: { notice: Notice; icon: IconName; tone: "warn" | "muted"; spin?: boolean }) {
  return (
    <div className={`notice notice--${tone}`} role="status">
      <Icon name={icon} className={spin ? "spin" : ""} />
      <div>
        <strong>{notice.head}</strong>
        {notice.body}
      </div>
    </div>
  );
}

export interface RecordingProps {
  recorder: Recorder;
  patient: Patient;
  onFinished: () => void;
  /** Recovery that needs the start screen: access code (focus the field) or a closed session (new session). */
  onBackToStart: (why: "access_code" | "session_ended") => void;
}

/** Recording screen (SPEC §2.3, §3). */
export function Recording({ recorder, patient, onFinished, onBackToStart }: RecordingProps) {
  const snap = useSyncExternalStore(recorder.subscribe, recorder.getSnapshot, recorder.getSnapshot);
  const [sheet, setSheet] = useState(false);
  const [leave, setLeave] = useState(false);
  const alarmHead = useRef<HTMLHeadingElement>(null);

  const { rec, scribe } = snap;
  const na = scribe.next_action;
  const flagOpen = !!snap.redFlag && snap.ackAtMs === null;
  const complete = allComplete(scribe);
  const extractionDown = na?.kind === "handoff" && na.reason === "extraction_unavailable";
  // Sticky on the client too (D-V2C-5): once a red flag was raised, no question is suggested again this session.
  const attentionHandoff = !!snap.redFlag || (na?.kind === "handoff" && na.reason === "nurse_attention_phrase");
  const live = rec === "listening" && na?.kind === "prompt_nurse" && !attentionHandoff && !complete;
  const factRows = rows(scribe, live);
  const captured = capturedCount(scribe);

  // Red flag: focus moves to the heading when it appears, and again when finish is refused.
  useEffect(() => {
    if (flagOpen) alarmHead.current?.focus();
  }, [flagOpen, snap.finishBlocked]);

  // Leave guard: the system back gesture opens the sheet instead of leaving mid-session.
  useEffect(() => {
    history.pushState({ scribe: "recording" }, "");
    const onPop = () => {
      history.pushState({ scribe: "recording" }, "");
      setLeave(true);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  async function finish() {
    setLeave(false);
    const r = await recorder.finish();
    if (r === "blocked") alarmHead.current?.focus();
    if (r === "done") onFinished();
  }

  function press() {
    if (rec === "error" && snap.errorKind === "access_code") return onBackToStart("access_code");
    if (rec === "error" && snap.errorKind === "session_ended") return onBackToStart("session_ended");
    recorder.press();
  }

  const btn = recButton(rec);
  const quiet = complete && !btn.disabled;
  const recCls = ["rec", quiet ? "rec--quiet" : btn.live ? "rec--live" : ""].filter(Boolean).join(" ");
  const finishEnabled = recorder.canFinish();
  const st = STATUS_ICON[rec];
  const meta = patientMeta(patient);

  // ------------------------------------------------------------------ top: alarm or patient + slot
  let top: React.ReactNode;
  if (flagOpen && snap.redFlag) {
    top = (
      <section className="alarm" role="alert" aria-labelledby="rf" data-testid="red-flag">
        <div className="alarm-id">
          <span>
            <span className="b num">{patient.id}</span>
            {meta && ` · ${meta}`}
          </span>
          <span>{rec === "listening" ? COPY.rec.redFlag.stillRecording : COPY.rec.status[rec]}</span>
        </div>
        <div className="alarm-head">
          <Icon name="triangle-alert" />
          <h2 id="rf" className="t-title" tabIndex={-1} ref={alarmHead}>
            {COPY.rec.redFlag.heading}
          </h2>
        </div>
        <div className="alarm-quote" data-testid="red-flag-quote">
          <span className="t-meta num" style={{ fontWeight: 400, display: "block" }}>
            {COPY.rec.redFlag.quoteLabel} · {hhmm(snap.redFlag.atMs)}
          </span>
          “{snap.redFlag.quote}”
        </div>
        <p className="t-meta">{COPY.rec.redFlag.body}</p>
        {snap.finishBlocked && <p className="alarm-block">{COPY.rec.finishBlocked}</p>}
        <button type="button" className="btn btn--block" onClick={() => recorder.acknowledge()}>
          {COPY.rec.redFlag.ack}
        </button>
      </section>
    );
  } else {
    let slot: React.ReactNode;
    if (complete) {
      slot = (
        <section className="slot slot--done" aria-live="polite" data-testid="slot" data-slot="done">
          <h2 className="slot-head t-title">
            <Icon name="circle-check" />
            {COPY.rec.complete.head}
          </h2>
          <p className="t-body">{COPY.rec.complete.body}</p>
        </section>
      );
    } else if (attentionHandoff) {
      slot = (
        <section className="slot slot--idle" aria-live="polite" data-testid="slot" data-slot="neutral">
          <h2 className="t-title">{PROPOSED_V2C.slotAfterAck.head}</h2>
          <p className="slot-note">{PROPOSED_V2C.slotAfterAck.body}</p>
        </section>
      );
    } else {
      const question = na?.kind === "prompt_nurse" ? na.suggested_question_th : snap.lastQuestion;
      const fieldLabel = na?.field ? FIELD_LABELS[na.field] ?? na.field : "";
      let note: string | null = null;
      if (live) note = COPY.rec.noteListening(fieldLabel);
      else if (extractionDown) note = null;
      else if (rec === "idle") note = COPY.rec.noteIdle;
      else if (rec === "paused") note = COPY.rec.notePaused;
      else if (rec === "reconnecting" || rec === "connecting" || rec === "requesting_permission") note = COPY.rec.noteReconnecting;
      else if (rec === "error" || rec === "permission_denied") note = COPY.rec.noteError;
      slot = (
        <section
          className={`slot ${live ? "slot--ask" : "slot--idle"}`}
          aria-live="polite"
          aria-labelledby={question ? "q" : undefined}
          data-testid="slot"
          data-slot={live ? "ask" : "neutral"}
        >
          {question ? (
            <p id="q" key={question} className="slot-q xfade">
              {question}
            </p>
          ) : (
            <p className="t-title">{PROPOSED_V2C.noQuestion}</p>
          )}
          {note && <p className="slot-note">{note}</p>}
        </section>
      );
    }
    top = (
      <>
        <header className="appbar">
          <div className="patient">
            <span className="b num">{patient.id}</span>
            {meta && <span className="t-meta muted">{meta}</span>}
          </div>
        </header>
        {snap.redFlag && snap.ackAtMs !== null && (
          <div className="flag-strip" data-testid="ack-strip">
            <Icon name="triangle-alert" />
            <span className="num">{COPY.rec.ackStrip(hhmm(snap.ackAtMs))}</span>
          </div>
        )}
        {slot}
        {extractionDown && (
          <div style={{ marginTop: 8 }}>
            <NoticeBox notice={COPY.rec.extractionUnavailable} icon="triangle-alert" tone="warn" />
          </div>
        )}
      </>
    );
  }

  // ------------------------------------------------------------------ dock: notice or transcript
  let dockTop: React.ReactNode = null;
  if (flagOpen) dockTop = null;
  else if (rec === "permission_denied") dockTop = <NoticeBox notice={COPY.rec.permissionDenied} icon="mic-off" tone="warn" />;
  else if (rec === "error") dockTop = <NoticeBox notice={errorNotice(snap.errorKind, captured)} icon="triangle-alert" tone="warn" />;
  else if (rec === "reconnecting") dockTop = <NoticeBox notice={COPY.rec.reconnecting(Math.max(1, snap.attempt))} icon="loader" tone="warn" spin />;
  else if (rec === "paused") dockTop = <NoticeBox notice={snap.systemPause ? COPY.rec.systemPause : COPY.rec.paused} icon="pause" tone="muted" />;
  else if (!snap.lines.length && !snap.interim && !snap.failedSegments) {
    dockTop = <div className="heard heard--empty">{COPY.rec.transcriptEmpty}</div>;
  } else {
    // A failed segment is surfaced in the dock itself, not only in the sheet: silent loss must stay visible.
    const failed = snap.failedSegments > 0;
    const last = snap.lines.slice(-(3 - (snap.interim ? 1 : 0) - (failed ? 1 : 0)));
    dockTop = (
      <button type="button" className="heard" aria-label={COPY.rec.transcriptOpen} onClick={() => setSheet(true)} data-testid="transcript">
        {last.map((l) => (
          <span key={l.key} className={`line${snap.redFlag?.quote === l.text ? " line--flag" : ""}`}>
            <time className="num">{hhmm(l.atMs)}</time>
            <span>{l.text}</span>
          </span>
        ))}
        {snap.interim && (
          <span className="line line--interim">
            <time className="num">{hhmm(snap.interim.atMs)}</time>
            <span>{snap.interim.text}…</span>
          </span>
        )}
        {failed && (
          <span className="line line--failed" data-testid="failed-segments">
            <Icon name="triangle-alert" size="sm" className="warn-ic" />
            <span>{PROPOSED_V2C.failedSegments(snap.failedSegments)}</span>
          </span>
        )}
      </button>
    );
  }

  return (
    <main className="screen screen--fixed">
      {top}

      <section className="facts" aria-labelledby="fh" style={{ marginTop: 16 }}>
        <div className="facts-head">
          <h2 id="fh" className="t-body b">
            {COPY.rec.factsHeading}
          </h2>
          <span className="t-meta muted">{COPY.rec.factsCount(captured)}</span>
        </div>
        <ul className="group" data-testid="facts" tabIndex={0} aria-labelledby="fh">
          {factRows.map((r) => (
            <FactRow key={r.field} row={r} />
          ))}
        </ul>
      </section>

      <section className="dock" aria-label="เครื่องบันทึก">
        {dockTop}
        <div className="controls">
          <div className="state" role="status" data-testid="rec-status">
            <Clock snap={snap} />
            <span className="say">
              {st.icon === "meter" ? (
                <Meter recorder={recorder} live={rec === "listening"} />
              ) : (
                <Icon name={st.icon} size="sm" className={[st.warn ? "warn-ic" : "muted", st.spin ? "spin" : ""].join(" ")} />
              )}
              {COPY.rec.status[rec]}
            </span>
          </div>
          <div className="rec-wrap">
            <button type="button" className={recCls} aria-label={btn.aria} disabled={btn.disabled} onClick={press} data-testid="rec-button" data-state={rec}>
              <Icon name={btn.icon} size="lg" fill={btn.fill} className={btn.spin ? "spin" : ""} />
            </button>
            <span className="rec-label" aria-hidden="true">
              {btn.label}
            </span>
          </div>
          <button
            type="button"
            className={`btn finish${complete && finishEnabled ? " btn--primary" : ""}`}
            disabled={!finishEnabled}
            onClick={finish}
          >
            {COPY.rec.finish}
          </button>
        </div>
        <Limit style={{ paddingTop: 0 }} />
      </section>

      {!flagOpen && (
        <Sheet open={sheet} onClose={() => setSheet(false)} title={COPY.rec.transcriptTitle}>
          <div className="sheet-scroll">
            {snap.lines.map((l) => (
              <p key={l.key} className={`line${snap.redFlag?.quote === l.text ? " line--flag" : ""}`}>
                <time className="num">{hhmm(l.atMs)}</time>
                <span>{l.text}</span>
              </p>
            ))}
            {snap.failedSegments > 0 && <p className="t-meta muted">{PROPOSED_V2C.failedSegments(snap.failedSegments)}</p>}
          </div>
        </Sheet>
      )}

      <Sheet open={leave} onClose={() => setLeave(false)} title={COPY.rec.leave.head}>
        <p className="t-body">{COPY.rec.leave.body}</p>
        <div className="sheet-acts">
          <button type="button" className="btn btn--primary btn--block" onClick={finish}>
            {COPY.rec.leave.confirm}
          </button>
          <button type="button" className="btn btn--block" onClick={() => setLeave(false)}>
            {COPY.rec.leave.back}
          </button>
        </div>
      </Sheet>
    </main>
  );
}
