"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { call, post } from "@/lib/api";
import { COPY, PROPOSED_V2C } from "@/lib/copy";
import type { RealtimeConfig } from "@/lib/realtime";
import { Recorder } from "@/lib/recorder";
import type { Patient } from "@/lib/roster";
import { fromStart, type StartResponse } from "@/lib/voice";

import { Login, type User } from "./Login";
import { Recording } from "./Recording";
import { Review, Submitted } from "./Review";
import { Start } from "./Start";

type Screen = "boot" | "login" | "start" | "recording" | "review" | "submitted";

/**
 * The whole app is one in-memory state machine (T11): transcript, facts, decisions and the access code live
 * only in React memory and the Recorder. Nothing is written to any browser storage.
 */
export function ScribeApp() {
  const [screen, setScreen] = useState<Screen>("boot");
  const [user, setUser] = useState<User | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [config, setConfig] = useState<RealtimeConfig | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [consentAt, setConsentAt] = useState<number | null>(null);
  const [recorder, setRecorder] = useState<Recorder | null>(null);
  const [startBusy, setStartBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState(false);
  const recRef = useRef<Recorder | null>(null);
  recRef.current = recorder;

  /** Clear every piece of in-memory session state. */
  const reset = useCallback(() => {
    recRef.current?.dispose();
    setRecorder(null);
    setPatient(null);
    setConsentAt(null);
    setStartError(null);
    setCodeError(false);
  }, []);

  const authLost = useCallback(() => {
    reset();
    setUser(null);
    setLoginError(null);
    setScreen("login");
  }, [reset]);

  const accept = useCallback(async (u: User) => {
    if (u.role !== "nurse") {
      await post("/api/auth/logout");
      setUser(null);
      setLoginError(COPY.login.wrongRole);
      setScreen("login");
      return;
    }
    setUser(u);
    setLoginError(null);
    setScreen("start");
  }, []);

  useEffect(() => {
    let live = true;
    call<{ user: User }>("/api/me").then((r) => {
      if (!live) return;
      if (r.data?.user) void accept(r.data.user);
      else setScreen("login");
    });
    return () => {
      live = false;
    };
  }, [accept]);

  useEffect(() => {
    if (screen !== "start" || config) return;
    call<RealtimeConfig>("/api/voice/realtime/config").then((r) => {
      if (r.status === 401) authLost();
      else if (r.data) setConfig(r.data);
    });
  }, [screen, config, authLost]);

  useEffect(() => () => recRef.current?.dispose(), []);

  async function signOut() {
    reset();
    await post("/api/auth/logout");
    setUser(null);
    setScreen("login");
  }

  async function open(p: Patient, accessCode: string) {
    setStartError(null);
    // Same patient after an access-code error: keep the session and its captured data, retry with the new code.
    if (recorder && patient?.id === p.id) {
      recorder.setAccessCode(accessCode);
      setCodeError(false);
      setScreen("recording");
      if (recorder.getSnapshot().rec === "error") void recorder.retry();
      return;
    }
    reset();
    setStartBusy(true);
    const r = await post<StartResponse>("/api/voice/sessions", { patient_ref: p.id, data_class: "synthetic", mode: "ambient" });
    setStartBusy(false);
    if (r.status === 401) return authLost();
    if (!r.data) return setStartError(PROPOSED_V2C.startFailed);
    const rec = new Recorder({
      sessionId: r.data.session.session_id,
      scribe: fromStart(r.data),
      config,
      accessCode,
      onAuthLost: authLost,
    });
    setRecorder(rec);
    setPatient(p);
    setConsentAt(Date.now());
    setScreen("recording");
  }

  if (screen === "boot") return <main className="screen" aria-busy="true" />;
  if (screen === "login" || !user) return <Login key={loginError ?? "login"} onUser={accept} initialError={loginError} />;

  if (screen === "recording" && recorder && patient) {
    return (
      <Recording
        recorder={recorder}
        patient={patient}
        onFinished={() => setScreen("review")}
        onBackToStart={(why) => {
          if (why === "session_ended") reset();
          else setCodeError(true);
          setScreen("start");
        }}
      />
    );
  }

  if (screen === "review" && recorder && patient && consentAt !== null) {
    const s = recorder.getSnapshot();
    return (
      <Review
        patient={patient}
        scribe={s.scribe}
        durationMs={s.clockMs}
        redFlag={s.redFlag}
        ackAtMs={s.ackAtMs}
        consentAtMs={consentAt}
        onContinue={() => {
          recorder.reopen();
          setScreen("recording");
        }}
        onSubmitted={() => setScreen("submitted")}
        onAuthLost={authLost}
      />
    );
  }

  if (screen === "submitted" && patient) {
    return (
      <Submitted
        patientId={patient.id}
        onNext={() => {
          reset();
          setScreen("start");
        }}
      />
    );
  }

  return (
    <Start
      username={user.username}
      accessCodeRequired={!!config?.access_code_required}
      accessCodeError={codeError}
      initialPatient={codeError ? patient : null}
      initialConsent={codeError}
      busy={startBusy}
      error={startError}
      onSignOut={signOut}
      onOpen={open}
    />
  );
}
