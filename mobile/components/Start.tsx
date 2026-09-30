"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { COPY, PROPOSED_V2C } from "@/lib/copy";
import { loadRoster, SYN_ID, type Patient } from "@/lib/roster";

import { Icon } from "./Icon";
import { Limit } from "./Limit";
import { Wordmark } from "./Wordmark";

export interface StartProps {
  username: string;
  accessCodeRequired: boolean;
  /** Focus the access-code field (returning after "access code invalid"). */
  accessCodeError?: boolean;
  initialPatient?: Patient | null;
  initialConsent?: boolean;
  busy?: boolean;
  error?: string | null;
  onSignOut: () => void;
  onOpen: (patient: Patient, accessCode: string) => void;
  roster?: () => Promise<Patient[]>;
}

type ListState = { kind: "loading" } | { kind: "error" } | { kind: "ready"; items: Patient[] };

/** Start session (SPEC §2.2): pick a synthetic patient, tick consent, open recording. No mic request here. */
export function Start(props: StartProps) {
  const { roster = loadRoster } = props;
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Patient | null>(props.initialPatient ?? null);
  const [consent, setConsent] = useState(!!props.initialConsent);
  const [code, setCode] = useState("");
  const codeRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setList({ kind: "loading" });
    roster().then(
      (items) => setList({ kind: "ready", items }),
      () => setList({ kind: "error" }),
    );
  };
  useEffect(load, [roster]);

  useEffect(() => {
    if (props.accessCodeError) codeRef.current?.focus();
  }, [props.accessCodeError]);

  const q = query.trim();
  const view = useMemo(() => {
    if (list.kind !== "ready") return { rows: [] as Patient[], notice: null as null | { head: string; body?: string } };
    const matches = q ? list.items.filter((p) => p.id.toLowerCase().includes(q.toLowerCase())) : list.items;
    if (!q && !list.items.length) return { rows: [], notice: COPY.start.empty };
    if (q && SYN_ID.test(q) && !list.items.some((p) => p.id === q)) return { rows: [{ id: q }, ...matches], notice: null };
    if (matches.length) return { rows: matches, notice: null };
    if (!/^syn-/i.test(q) && !"SYN-".startsWith(q.toUpperCase())) return { rows: [], notice: { head: COPY.start.nonSynthetic } };
    return { rows: [], notice: COPY.start.noMatch(q) };
  }, [list, q]);

  const needCode = props.accessCodeRequired;
  const ready = !!picked && consent && (!needCode || !!code.trim());

  return (
    <main className="screen screen--fixed">
      <header className="appbar">
        <Wordmark size={20} />
        <button type="button" className="btn btn--ghost t-meta" aria-label={COPY.start.account(props.username)} onClick={props.onSignOut}>
          <span className="muted">{props.username}</span>
          <Icon name="log-out" className="muted" />
        </button>
      </header>

      <div className="start-scroll">
        <h1 className="t-display" style={{ marginTop: 16 }}>
          {COPY.start.title}
        </h1>
        <p className="t-body muted">{COPY.start.subtitle}</p>

        <div className="input" style={{ marginTop: 16 }}>
          <span className="adorn">
            <Icon name="search" />
          </span>
          <input
            aria-label={COPY.start.searchLabel}
            placeholder={COPY.start.searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoCapitalize="characters"
            spellCheck={false}
          />
        </div>

        {list.kind === "loading" && (
          <ul className="group" aria-busy="true" aria-label={COPY.start.loading} style={{ marginTop: 16 }}>
            <li className="sr" role="status">
              {COPY.start.loading}
            </li>
            {[0, 1, 2].map((i) => (
              <li key={i} className="skeleton" aria-hidden="true" data-testid="skeleton-row">
                <i />
                <span style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <i style={{ width: "60%" }} />
                  <i style={{ width: "40%" }} />
                </span>
              </li>
            ))}
          </ul>
        )}

        {list.kind === "error" && (
          <div className="group list-state" style={{ marginTop: 16 }} role="alert">
            <p className="t-body b">{COPY.start.loadError}</p>
            <button type="button" className="btn" onClick={load}>
              {COPY.start.reload}
            </button>
          </div>
        )}

        {list.kind === "ready" && view.notice && (
          <div className="group list-state" style={{ marginTop: 16 }} role="status">
            <p className="t-body b">{view.notice.head}</p>
            {view.notice.body && <p className="t-meta muted">{view.notice.body}</p>}
          </div>
        )}

        {list.kind === "ready" && view.rows.length > 0 && (
          <ul className="group" role="radiogroup" aria-label="ผู้ป่วยที่รอซักประวัติ" style={{ marginTop: 16 }}>
            {view.rows.map((p) => (
              <li key={p.id} role="none">
                <label className="pick">
                  <input
                    type="radio"
                    className="sr"
                    name="patient"
                    value={p.id}
                    checked={picked?.id === p.id}
                    onChange={() => setPicked(p)}
                  />
                  <span className="radio" aria-hidden="true" />
                  <span>
                    <span className="b num">{p.id}</span>
                    {p.sex && p.age !== undefined && <span className="t-body"> · {COPY.start.sexAge(p.sex, p.age)}</span>}
                    {(p.bed || p.arrived) && (
                      <>
                        <br />
                        <span className="t-meta muted">
                          {[p.bed, p.arrived ? COPY.start.arrived(p.arrived) : null].filter(Boolean).join(" · ")}
                        </span>
                      </>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <section aria-labelledby="mic-h" style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8 }}>
          <h2 id="mic-h" className="t-body b" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Icon name="mic" className="accent" />
            {COPY.start.explainHeading}
          </h2>
          <ul className="explain t-meta">
            {COPY.start.explainLines.map((l) => (
              <li key={l}>
                <Icon name="info" size="sm" />
                <span>{l}</span>
              </li>
            ))}
          </ul>
          <label className="consent t-body" style={{ marginTop: 8 }}>
            <input type="checkbox" className="sr" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span className="check" aria-hidden="true">
              <Icon name="check" size="sm" className="check-mark" />
            </span>
            {COPY.start.consent}
          </label>
          {needCode && (
            <div className="field" style={{ marginTop: 8 }}>
              <label htmlFor="code">{PROPOSED_V2C.accessCodeLabel}</label>
              <div className="input">
                <input
                  id="code"
                  ref={codeRef}
                  type="password"
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  aria-invalid={props.accessCodeError || undefined}
                  aria-describedby={props.accessCodeError ? "code-err" : undefined}
                />
              </div>
              {props.accessCodeError && (
                <p className="field-error" id="code-err">
                  {PROPOSED_V2C.accessCodeInvalid.head} {PROPOSED_V2C.accessCodeInvalid.body}
                </p>
              )}
            </div>
          )}
        </section>
      </div>

      {props.error && (
        <div className="notice notice--warn" role="alert" style={{ marginTop: 8 }}>
          <Icon name="triangle-alert" />
          <span>{props.error}</span>
        </div>
      )}
      <button
        type="button"
        className="btn btn--primary btn--block"
        style={{ marginTop: 16 }}
        disabled={!ready || props.busy}
        aria-describedby={ready ? undefined : "open-hint"}
        onClick={() => picked && props.onOpen(picked, code)}
      >
        {COPY.start.cta}
      </button>
      {!ready && (
        <p id="open-hint" className="t-meta muted" style={{ textAlign: "center", paddingTop: 8 }}>
          {COPY.start.disabledHint}
        </p>
      )}
      <Limit />
    </main>
  );
}
