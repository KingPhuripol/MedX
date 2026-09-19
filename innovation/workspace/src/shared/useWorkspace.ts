import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiCall, clearPendingRequest, createIdempotencyKey, hasPendingRequest, jobError, setCsrfToken, synthesizeSpeech, transcribeAudio } from "./api";
import type { Capability, Case, Draft, Fact, Job, Run, Session } from "./types";

export type VoiceState = "idle" | "recording" | "transcribing";

/** Session, case data and assistant actions shared by the nurse and platform apps.
 *
 * Routing, navigation and page composition stay in each app; this hook only talks to /v2. */
export function useWorkspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [caps, setCaps] = useState<Capability | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [current, setCurrent] = useState<Case | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [query, setQuery] = useState("");
  const [caseStatus, setCaseStatus] = useState("");
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [editing, setEditing] = useState<Fact | null>(null);
  const [dirtyEntries, setDirtyEntries] = useState<Record<string, boolean>>({});
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const messageRef = useRef(message);
  const currentRef = useRef(current);
  const dirty = Object.values(dirtyEntries).some(Boolean);
  const unsaved = Boolean(message || dirty || editing);
  messageRef.current = message;
  currentRef.current = current;

  const trackDirty = useCallback((id: string, value: boolean) => setDirtyEntries((previous) => previous[id] === value ? previous : { ...previous, [id]: value }), []);
  const work = useCallback(async (action: () => Promise<void>, silentAuthentication = false) => {
    setBusy(true); setError("");
    try { await action(); } catch (reason) {
      if (reason instanceof ApiError && ["AUTHENTICATION_REQUIRED", "CSRF_REQUIRED"].includes(reason.code)) {
        // A latched request cannot be replayed across sign-in: its CSRF token died with the session.
        setCsrfToken(""); clearPendingRequest(); setSession(null); setCaps(null); setCurrent(null);
        if (silentAuthentication) return;
      }
      setError(reason instanceof Error ? reason.message : "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง");
    }
    finally { setBusy(false); }
  }, []);
  const loadList = useCallback(async (offset = 0, append = false) => {
    const response = await apiCall<{ items: Case[]; next_offset: number | null }>(`/encounters?q=${encodeURIComponent(query)}&status=${caseStatus}&offset=${offset}`);
    setCases((previous) => append ? [...previous, ...response.items] : response.items); setNextOffset(response.next_offset);
  }, [query, caseStatus]);
  const load = useCallback(async (id: string) => {
    const [encounter, snapshot, encounterRuns, encounterDrafts] = await Promise.all([
      apiCall<Case>(`/encounters/${id}?include_history=false`), apiCall<{ evidence: Fact[] }>(`/encounters/${id}/snapshot`),
      apiCall<Run[]>(`/encounters/${id}/turns`), apiCall<Draft[]>(`/encounters/${id}/drafts`),
    ]);
    setCurrent(encounter); setFacts(snapshot.evidence); setRuns(encounterRuns); setDrafts(encounterDrafts);
    setMessage(sessionStorage.getItem(`frontdoor-message:${id}`) || "");
    return { encounter, facts: snapshot.evidence, runs: encounterRuns, drafts: encounterDrafts };
  }, []);
  const loadLatest = useCallback(async () => {
    const latest = await apiCall<{ items: Case[] }>(`/encounters?offset=0&limit=1`);
    if (latest.items.length) await load(latest.items[0].encounter_id);
  }, [load]);
  /** Sign-in state, capabilities, the case list and any job left running before a reload. */
  const bootstrap = useCallback(async () => {
    const activeSession = await apiCall<Session>("/session"); setCsrfToken(activeSession.csrf); setSession(activeSession);
    setCaps(await apiCall<Capability>("/capabilities")); await loadList();
    const savedJob = sessionStorage.getItem("frontdoor-job");
    if (savedJob) { try { setJob(await apiCall<Job>(`/jobs/${savedJob}`)); } catch { sessionStorage.removeItem("frontdoor-job"); } }
    return activeSession;
  }, [loadList]);

  useEffect(() => {
    if (!current) return; const storageKey = `frontdoor-message:${current.encounter_id}`;
    if (message) sessionStorage.setItem(storageKey, message); else sessionStorage.removeItem(storageKey);
  }, [message, current?.encounter_id]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return; let stopped = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await apiCall<Job>(`/jobs/${job.job_id}`); if (stopped) return; setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          sessionStorage.removeItem("frontdoor-job"); if (currentRef.current?.encounter_id === next.encounter_id) await load(next.encounter_id);
          if (next.status === "completed" && next.result?.user_text === messageRef.current) setMessage("");
          if (next.status === "failed") setError(jobError(next.error_code));
        }
      } catch { if (!stopped) setError("อ่านสถานะงานไม่ได้ ระบบจะตรวจให้อีกครั้ง"); }
    }, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [job?.job_id, job?.status, load]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (unsaved || hasPendingRequest()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  const act = async (path: string, body: unknown) => work(async () => { await apiCall(path, "POST", body); if (currentRef.current) await load(currentRef.current.encounter_id); await loadList(); });
  const startRun = async (intent: "conversation" | "draft", customText?: string) => {
    if (!current) return;
    await work(async () => {
      const textToRun = customText !== undefined ? customText : (message || "เตรียมร่างส่งต่อ");
      const created = await apiCall<Job>(`/encounters/${current.encounter_id}/jobs`, "POST", { expected_revision: current.case_revision, idempotency_key: createIdempotencyKey(), text: textToRun, decision_time: new Date().toISOString(), intent, design_id: intent === "draft" ? "fixed" : "single" });
      setJob(created);
      if (["queued", "running"].includes(created.status)) sessionStorage.setItem("frontdoor-job", created.job_id);
      else { await load(current.encounter_id); if (created.status === "completed" && intent === "conversation" && created.result?.user_text === messageRef.current) setMessage(""); if (created.status === "failed") throw Error(jobError(created.error_code)); }
    });
  };
  const cancelJob = () => job && work(async () => setJob(await apiCall<Job>(`/jobs/${job.job_id}/cancel`, "POST")));
  const record = async () => {
    if (recorder.current?.state === "recording") { recorder.current.stop(); return; }
    let stream: MediaStream | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const activeRecorder = new MediaRecorder(stream); recorder.current = activeRecorder; const chunks: BlobPart[] = [];
      activeRecorder.ondataavailable = (event) => chunks.push(event.data);
      activeRecorder.onerror = () => { stream?.getTracks().forEach((track) => track.stop()); setVoiceState("idle"); setError("บันทึกเสียงไม่ได้ กรุณาใช้ข้อความต่อ"); };
      activeRecorder.onstop = () => {
        stream?.getTracks().forEach((track) => track.stop()); setVoiceState("transcribing");
        work(async () => {
          const transcribed = await transcribeAudio(new Blob(chunks, { type: activeRecorder.mimeType }));
          setMessage([messageRef.current, transcribed].filter(Boolean).join("\n"));
        }).finally(() => setVoiceState("idle"));
      };
      activeRecorder.start(); setVoiceState("recording"); const timer = window.setTimeout(() => { if (activeRecorder.state === "recording") activeRecorder.stop(); }, 60000); activeRecorder.addEventListener("stop", () => window.clearTimeout(timer), { once: true });
    } catch { stream?.getTracks().forEach((track) => track.stop()); setVoiceState("idle"); setError("เปิดไมโครโฟนไม่ได้ กรุณาตรวจสิทธิ์หรือพิมพ์ข้อความ"); }
  };
  const speak = async (text: string, runId?: string) => {
    if (runId && caps?.synthesis) {
      await work(async () => {
        audioRef.current?.pause();
        const url = URL.createObjectURL(await synthesizeSpeech(runId)); const audio = new Audio(url); audioRef.current = audio;
        audio.onended = () => URL.revokeObjectURL(url); audio.onerror = () => { URL.revokeObjectURL(url); };
        try { await audio.play(); } catch { /* Autoplay restriction handled safely */ }
      }); return;
    }
    const voice = window.speechSynthesis?.getVoices().find((item) => item.localService && item.lang.startsWith("th")); if (!voice) { setError("ยังไม่มีเสียงภาษาไทยในเครื่อง ใช้ข้อความต่อได้"); return; }
    speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.voice = voice; speechSynthesis.speak(utterance);
  };
  const stopAudio = () => { window.speechSynthesis?.cancel(); audioRef.current?.pause(); };
  const signOut = () => work(async () => { await apiCall("/session", "DELETE"); setCsrfToken(""); setSession(null); setCurrent(null); setRuns([]); setDrafts([]); setFacts([]); });

  return {
    session, caps, cases, current, facts, runs, drafts, message, setMessage, error, busy, job,
    query, setQuery, caseStatus, setCaseStatus, nextOffset, editing, setEditing, voiceState, dirty, unsaved, currentRef,
    trackDirty, work, load, loadList, loadLatest, bootstrap, act, startRun, cancelJob, record, speak, stopAudio, signOut,
  };
}

export type Workspace = ReturnType<typeof useWorkspace>;
