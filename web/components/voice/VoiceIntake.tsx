"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import {
  FIELD_LABELS,
  REASON_LABELS,
  SPEAKER_LABELS,
  displayValue,
  type FinishResult,
  type SessionState,
  type Speaker,
} from "@/lib/voice";

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
export default function VoiceIntake() {
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
  const missing = (state?.field_statuses ?? []).filter((s) => s.status === "MISSING");

  return (
    <section aria-labelledby="intake-title">
      <h1 id="intake-title">Voice intake (Thai, text first)</h1>
      <p>
        Synthetic patients only. The agent asks fixed intake questions; every extracted fact is for nurse review and
        confirmation.
      </p>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {!sessionId && (
        <form onSubmit={start}>
          <div className="field">
            <label htmlFor="patient-ref">Synthetic patient ref</label>
            <input
              id="patient-ref"
              name="patient-ref"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              pattern="SYN-[A-Za-z0-9-]+"
              aria-describedby="patient-ref-hint"
              required
            />
            <small id="patient-ref-hint">Must start with SYN- (synthetic data only).</small>
          </div>
          <button type="submit" disabled={busy}>
            Start intake
          </button>
        </form>
      )}

      {state && action && (
        <>
          <h2 id="question-title">Agent question</h2>
          <p role="status" aria-live="polite" aria-labelledby="question-title" lang="th" data-testid="agent-question">
            {action.utterance_th}
          </p>

          {action.action === "handoff" && (
            <div role="alert" data-testid="handoff-banner" className="disclaimer">
              <p>
                <strong>Hand off to nurse:</strong> {REASON_LABELS[action.reason ?? ""] ?? action.reason}
              </p>
              {action.missing_fields.length > 0 && (
                <p>Still missing: {action.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}</p>
              )}
            </div>
          )}

          {!finished && (
            <form onSubmit={addTurn} aria-label="Add a turn">
              <div className="field">
                <label htmlFor="turn-speaker">Speaker</label>
                <select
                  id="turn-speaker"
                  value={speaker}
                  onChange={(e) => setSpeaker(e.target.value as Speaker)}
                >
                  <option value="patient">Patient</option>
                  <option value="relative">Relative</option>
                  <option value="nurse">Nurse</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="turn-text">Turn text</label>
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
              </div>
              <button type="submit" disabled={busy}>
                Add turn
              </button>
            </form>
          )}

          <h2 id="facts-title">Extracted facts (for nurse review)</h2>
          <table aria-labelledby="facts-title" data-testid="facts-table">
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
                  <th scope="row">{FIELD_LABELS[f.field] ?? f.field}</th>
                  <td>{f.state}</td>
                  <td lang="th">{displayValue(f)}</td>
                  <td>
                    {f.span_turn_ids.map((id) => (
                      <a key={id} href={`#turn-${id}`} data-testid="source-link">
                        turn {seqById.get(id) ?? "?"}
                      </a>
                    ))}
                  </td>
                  <td>
                    <time dateTime={f.available_at_time}>{f.available_at_time}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 id="missing-title">Missing fields</h2>
          {missing.length > 0 ? (
            <ul aria-labelledby="missing-title" data-testid="missing-list">
              {missing.map((s) => (
                <li key={s.field}>
                  {FIELD_LABELS[s.field] ?? s.field}
                  {s.not_elicited ? " — not elicited after two attempts" : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p data-testid="missing-list">None missing.</p>
          )}

          <h2 id="transcript-title">Transcript</h2>
          <ol aria-labelledby="transcript-title" data-testid="transcript">
            {state.turns.map((t) => (
              <li key={t.turn_id} id={`turn-${t.turn_id}`}>
                <strong>{SPEAKER_LABELS[t.speaker]}:</strong> <span lang="th">{t.text}</span>
              </li>
            ))}
          </ol>

          {!finished && (
            <button type="button" onClick={finish} disabled={busy}>
              Finish intake
            </button>
          )}

          {summary && (
            <section aria-labelledby="summary-title" data-testid="intake-summary">
              <h2 id="summary-title" ref={summaryRef} tabIndex={-1}>
                Intake summary
              </h2>
              <p>Handoff reason: {REASON_LABELS[summary.handoff_reason] ?? summary.handoff_reason}</p>
              <p>
                Missing fields:{" "}
                {summary.missing_fields.length
                  ? summary.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")
                  : "none"}
              </p>
              <p>Evidence items recorded: {summary.evidence.length}</p>
            </section>
          )}
        </>
      )}
    </section>
  );
}
