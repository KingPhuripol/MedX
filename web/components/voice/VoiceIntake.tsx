"use client";

import { AlertOctagon, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatThaiTime } from "@/lib/demo";
import {
  FIELD_LABELS,
  REASON_LABELS,
  SPEAKER_LABELS,
  displayValue,
  type FinishResult,
  type SessionState,
  type Speaker,
} from "@/lib/voice";

import css from "./VoiceIntake.module.css";

function localTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : formatThaiTime(iso);
}

async function call<T>(url: string, init?: RequestInit): Promise<{ status: number; data: T | null }> {
  const resp = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = resp.ok ? ((await resp.json()) as T) : null;
  return { status: resp.status, data };
}

/** Nurse-run Thai intake. The agent question shown here is only ever the server's allowlisted utterance. */
export default function VoiceIntake({ embedded = false }: { embedded?: boolean }) {
  const router = useRouter();
  const [ref, setRef] = useState("SYN-");
  const [state, setState] = useState<SessionState | null>(null);
  const [speaker, setSpeaker] = useState<Speaker>("patient");
  const [text, setText] = useState("");
  const [typingSince, setTypingSince] = useState<number | null>(null);
  const [summary, setSummary] = useState<FinishResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const textRef = useRef<HTMLInputElement>(null);
  const summaryRef = useRef<HTMLHeadingElement>(null);

  const sessionId = state?.session.session_id ?? null;
  const finished = state?.session.status === "finished" || summary !== null;

  useEffect(() => {
    if (sessionId && !finished) textRef.current?.focus();
  }, [sessionId, finished]);
  useEffect(() => {
    if (summary) summaryRef.current?.focus();
  }, [summary]);

  function fail(status: number, what: string): void {
    if (status === 401) {
      router.replace("/login");
      return;
    }
    if (status === 422) setError(`${what}: the input was rejected (check the synthetic ref, text and timing).`);
    else if (status === 409) setError(`${what}: this intake is already finished.`);
    else setError(`${what} failed. Please try again.`);
  }

  async function refresh(id: string): Promise<void> {
    const { status, data } = await call<SessionState>(`/api/voice/sessions/${id}`);
    if (data) setState(data);
    else fail(status, "Loading the intake");
  }

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { status, data } = await call<{ session: { session_id: string } }>("/api/voice/sessions", {
        method: "POST",
        body: JSON.stringify({ patient_ref: ref.trim(), data_class: "synthetic" }),
      });
      if (data) await refresh(data.session.session_id);
      else fail(status, "Starting the intake");
    } catch {
      setError("The service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function addTurn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!sessionId || !text.trim()) return;
    setBusy(true);
    setError(null);
    const lastEnd = Math.max(0, ...(state?.turns ?? []).map((t) => Date.parse(t.ended_at)));
    const now = Date.now();
    const started = Math.max(Math.min(typingSince ?? now, now), lastEnd);
    const ended = Math.max(now, started);
    try {
      const { status, data } = await call<unknown>(`/api/voice/sessions/${sessionId}/turns`, {
        method: "POST",
        body: JSON.stringify({
          speaker,
          text: text.trim(),
          started_at: new Date(started).toISOString(),
          ended_at: new Date(ended).toISOString(),
        }),
      });
      if (data) {
        setText("");
        setTypingSince(null);
        await refresh(sessionId);
      } else fail(status, "Adding the turn");
    } catch {
      setError("The service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const { status, data } = await call<FinishResult>(`/api/voice/sessions/${sessionId}/finish`, { method: "POST" });
      if (data) {
        setSummary(data);
        await refresh(sessionId);
      } else fail(status, "Finishing the intake");
    } catch {
      setError("The service is unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const action = state?.next_action ?? null;
  const seqById = new Map((state?.turns ?? []).map((t) => [t.turn_id, t.seq]));
  const speakerById = new Map((state?.turns ?? []).map((t) => [t.turn_id, t.speaker]));
  const missing = (state?.field_statuses ?? []).filter((s) => s.status === "MISSING");

  const intro =
    "Synthetic patients only. The agent asks fixed intake questions; every extracted fact is for nurse review and confirmation.";

  return (
    <div className={embedded ? css.embedded : `page-stack ${css.page}`}>
      {embedded ? (
        <div className={css.embeddedHead}>
          <h2 id="intake-title">Voice intake (Thai, text first)</h2>
          <p className={css.muted}>{intro}</p>
        </div>
      ) : (
        <PageHeader titleId="intake-title" title="Voice intake (Thai, text first)" subtitle={intro} />
      )}

      {error && (
        <Notice tone="critical" role="alert" icon={<AlertOctagon size={24} aria-hidden="true" />}>
          <p>{error}</p>
        </Notice>
      )}

      {!sessionId && (
        <Section>
          <form onSubmit={start} className={css.startForm}>
            <Field
              label="Synthetic patient ref"
              htmlFor="patient-ref"
              hint="Must start with SYN- (synthetic data only)."
            >
              <input
                id="patient-ref"
                name="patient-ref"
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                pattern="SYN-[A-Za-z0-9-]+"
                aria-describedby="patient-ref-hint"
                required
              />
            </Field>
            <Button type="submit" disabled={busy}>
              Start intake
            </Button>
          </form>
        </Section>
      )}

      {state && action && (
        <>
          {action.action === "handoff" && (
            <Notice
              tone="warning"
              role="alert"
              data-testid="handoff-banner"
              icon={<AlertTriangle size={24} aria-hidden="true" />}
            >
              <p>
                <strong>Hand off to nurse:</strong> {REASON_LABELS[action.reason ?? ""] ?? action.reason}
              </p>
              {action.missing_fields.length > 0 && (
                <p>Still missing: {action.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}</p>
              )}
            </Notice>
          )}

          {state.session.allergy_conflict && (
            <Notice
              tone="warning"
              role="alert"
              data-testid="allergy-conflict-banner"
              icon={<AlertTriangle size={24} aria-hidden="true" />}
            >
              <p>
                <strong>Drug allergy conflict:</strong> a later answer did not match the drug allergy already recorded.
                The recorded allergy was kept. Nurse to confirm with the patient.
              </p>
            </Notice>
          )}

          <div className={css.columns}>
            <div className={css.col}>
              <Section title="Agent question" titleId="question-title">
                <p
                  role="status"
                  aria-live="polite"
                  aria-labelledby="question-title"
                  lang="th"
                  data-testid="agent-question"
                  className={css.question}
                >
                  {action.utterance_th}
                </p>
              </Section>

              {!finished && (
                <Section>
                  <form onSubmit={addTurn} aria-label="Add a turn" className={css.turnForm}>
                    <Field label="Speaker" htmlFor="turn-speaker">
                      <select id="turn-speaker" value={speaker} onChange={(e) => setSpeaker(e.target.value as Speaker)}>
                        <option value="patient">Patient</option>
                        <option value="relative">Relative</option>
                        <option value="nurse">Nurse</option>
                      </select>
                    </Field>
                    <Field label="Turn text" htmlFor="turn-text">
                      <input
                        id="turn-text"
                        ref={textRef}
                        lang="th"
                        value={text}
                        autoComplete="off"
                        onChange={(e) => {
                          if (typingSince === null) setTypingSince(Date.now());
                          setText(e.target.value);
                        }}
                        required
                      />
                    </Field>
                    <Button type="submit" disabled={busy}>
                      Add turn
                    </Button>
                  </form>
                </Section>
              )}

              <Section title="Transcript" titleId="transcript-title">
                <ol aria-labelledby="transcript-title" data-testid="transcript" className={css.transcript}>
                  {state.turns.map((t) => (
                    <li key={t.turn_id} id={`turn-${t.turn_id}`} className={t.speaker === "agent" ? css.turnAgent : css.turn}>
                      <StatusChip tone={t.speaker === "agent" ? "info" : "neutral"}>{SPEAKER_LABELS[t.speaker]}</StatusChip>
                      <span lang="th">{t.text}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            </div>

            <div className={css.col}>
              <Section title="Extracted facts (for nurse review)" titleId="facts-title">
                <div className={css.tableWrap}>
                  <table aria-labelledby="facts-title" data-testid="facts-table" className={css.facts}>
                    <thead>
                      <tr>
                        <th scope="col">Field</th>
                        <th scope="col">State</th>
                        <th scope="col">Value</th>
                        <th scope="col">Source turn(s)</th>
                        <th scope="col">Available at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.facts.map((f) => (
                        <tr key={f.fact_id} data-testid="fact-row" data-field={f.field}>
                          <th scope="row" data-label="Field">
                            {FIELD_LABELS[f.field] ?? f.field}
                          </th>
                          <td data-label="State">
                            <StatusChip tone={f.state === "KNOWN" ? "success" : "warning"}>{f.state}</StatusChip>
                          </td>
                          <td lang="th" data-label="Value">
                            {displayValue(
                              f,
                              f.span_turn_ids.flatMap((id) => speakerById.get(id) ?? []),
                            )}
                          </td>
                          <td data-label="Source turn(s)">
                            {f.span_turn_ids.map((id) => (
                              <a key={id} href={`#turn-${id}`} data-testid="source-link" className={css.source}>
                                turn {seqById.get(id) ?? "?"}
                              </a>
                            ))}
                          </td>
                          <td data-label="Available at" className={css.muted}>
                            <time dateTime={f.available_at_time}>{localTime(f.available_at_time)}</time>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>

              <Section title="Missing fields" titleId="missing-title" tone={missing.length ? "warning" : "default"}>
                {missing.length > 0 ? (
                  <ul aria-labelledby="missing-title" data-testid="missing-list" className={css.missing}>
                    {missing.map((s) => (
                      <li key={s.field}>
                        <StatusChip tone="warning">
                          {FIELD_LABELS[s.field] ?? s.field}
                          {s.not_elicited ? " — not elicited after two attempts" : ""}
                        </StatusChip>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p data-testid="missing-list" className={css.none}>
                    None missing.
                  </p>
                )}
              </Section>

              {!finished && (
                <div>
                  <Button type="button" onClick={finish} disabled={busy}>
                    Finish intake
                  </Button>
                </div>
              )}
            </div>
          </div>

          {summary && (
            <Section title={null} aria-labelledby="summary-title" data-testid="intake-summary">
              <h2 id="summary-title" ref={summaryRef} tabIndex={-1} className={css.flush}>
                Intake summary
              </h2>
              <p className={css.flush}>Handoff reason: {REASON_LABELS[summary.handoff_reason] ?? summary.handoff_reason}</p>
              <p className={css.flush}>
                Missing fields:{" "}
                {summary.missing_fields.length
                  ? summary.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")
                  : "none"}
              </p>
              <p className={css.flush}>Evidence items recorded: {summary.evidence.length}</p>
            </Section>
          )}
        </>
      )}
    </div>
  );
}
