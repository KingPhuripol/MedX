"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  connectRealtime,
  createLevelMeter,
  normaliseTranscript,
  speakEvent,
  type LevelMeter,
  type RealtimeConfig,
  type RealtimeConnection,
  type RealtimeEvent,
  type RealtimeSession,
} from "@/lib/realtime";
import type { FinishResult, NextAction, SessionState, Speaker } from "@/lib/voice";

import { ERROR_TH, HINT_TH, type LiveState } from "./copy";

const TAIL_MS = 300; // mic stays off this long after MedX stops speaking (half-duplex)
const SPEAK_START_FALLBACK_MS = 8000; // no output_audio_buffer.started after response.create
const HANDOFF_END_FALLBACK_MS = 10000; // spoken handoff never reports "stopped"
const CONNECT_TIMEOUT_MS = 15000; // no session.created after the SDP exchange
const DISCONNECT_GRACE_MS = 5000;

export interface LiveParams {
  caseId: string | null;
  runId: string | null;
  sessionParam: string | null;
  initialRef: string;
}

interface Reply<T> {
  status: number;
  data: T | null;
  body: unknown;
}

async function call<T>(url: string, init?: RequestInit): Promise<Reply<T>> {
  try {
    const resp = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch {
      /* empty body */
    }
    return { status: resp.status, data: resp.ok ? (body as T) : null, body };
  } catch {
    return { status: 0, data: null, body: null };
  }
}

function reasonOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  const reason = (detail as { reason?: unknown } | null)?.reason;
  return typeof reason === "string" ? reason : null;
}

interface TurnDraft {
  speaker: Speaker;
  text: string;
  startMs: number;
  endMs: number;
  source: "asr" | "typed";
}

interface TurnResponse {
  turn: { ended_at: string };
  next_action: NextAction;
  field_statuses: SessionState["field_statuses"];
  session: SessionState["session"];
  nurse_attention?: boolean;
}

/** Mutable call plumbing. Kept in refs so realtime callbacks never see stale React state. */
interface Machine {
  state: LiveState;
  sessionId: string | null;
  conn: RealtimeConnection | null;
  mic: MediaStream | null;
  micMeter: LevelMeter | null;
  remoteMeter: LevelMeter | null;
  audio: HTMLAudioElement | null;
  wakeLock: { release(): Promise<void> } | null;
  muted: boolean;
  blocked: boolean; // half-duplex: from response.create until stopped + tail
  speaking: boolean;
  connected: boolean;
  ending: boolean;
  finishing: boolean;
  finishFailed: boolean;
  action: NextAction | null;
  deferred: NextAction | null;
  afterSpeak: (() => void) | null;
  asrModel: string;
  lastEnd: number;
  pending: number;
  chain: Promise<void>;
  items: Map<string, { startMs: number; dropped: boolean }>;
  deadline: number | null;
  maxMs: number;
  timers: { tick?: ReturnType<typeof setInterval>; tail?: ReturnType<typeof setTimeout>; start?: ReturnType<typeof setTimeout>; end?: ReturnType<typeof setTimeout>; connect?: ReturnType<typeof setTimeout>; drop?: ReturnType<typeof setTimeout> };
}

export function useLiveCall(params: LiveParams) {
  const router = useRouter();
  const [state, setStateRaw] = useState<LiveState>("loading");
  const [cfg, setCfg] = useState<RealtimeConfig | null>(null);
  const [cfgFailed, setCfgFailed] = useState(false);
  const [vendorLabel, setVendorLabel] = useState<string | null>(null);
  const [cause, setCause] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [data, setData] = useState<SessionState | null>(null);
  const [summary, setSummary] = useState<FinishResult | null>(null);
  const [muted, setMutedState] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [patientRef, setPatientRef] = useState(params.initialRef);
  const [typeOpen, setTypeOpen] = useState(false);
  const [typedBusy, setTypedBusy] = useState(false);
  const [finishing, setFinishing] = useState(false);

  const m = useRef<Machine>({
    state: "loading", sessionId: null, conn: null, mic: null, micMeter: null, remoteMeter: null, audio: null,
    wakeLock: null, muted: false, blocked: false, speaking: false, connected: false, ending: false,
    finishing: false, finishFailed: false, action: null, deferred: null, afterSpeak: null, asrModel: "",
    lastEnd: 0, pending: 0, chain: Promise.resolve(), items: new Map(), deadline: null, maxMs: 0, timers: {},
  }).current;

  const setState = useCallback(
    (next: LiveState) => {
      m.state = next;
      setStateRaw(next);
    },
    [m],
  );

  const audioRef = useCallback(
    (el: HTMLAudioElement | null) => {
      m.audio = el;
    },
    [m],
  );

  // ---------------------------------------------------------------- helpers

  const applyMic = useCallback(() => {
    m.conn?.setMic(!m.muted && !m.blocked && !m.ending);
  }, [m]);

  const clearTimers = useCallback(() => {
    for (const key of Object.keys(m.timers) as (keyof Machine["timers"])[]) {
      const t = m.timers[key];
      if (t !== undefined) {
        clearTimeout(t as ReturnType<typeof setTimeout>);
        clearInterval(t as ReturnType<typeof setInterval>);
      }
      delete m.timers[key];
    }
  }, [m]);

  const releaseWakeLock = useCallback(() => {
    const lock = m.wakeLock;
    m.wakeLock = null;
    void lock?.release().catch(() => undefined);
  }, [m]);

  const acquireWakeLock = useCallback(() => {
    const wl = (navigator as unknown as { wakeLock?: { request(t: "screen"): Promise<{ release(): Promise<void> }> } }).wakeLock;
    if (!wl || m.wakeLock) return;
    wl.request("screen")
      .then((lock) => {
        if (m.connected && !m.finishing) m.wakeLock = lock;
        else void lock.release().catch(() => undefined);
      })
      .catch(() => undefined); // silent
  }, [m]);

  /** Close the realtime connection and release the mic, meters, timers and wake lock. */
  const teardown = useCallback(() => {
    clearTimers();
    m.conn?.close();
    m.conn = null;
    m.mic?.getTracks().forEach((t) => t.stop());
    m.mic = null;
    m.micMeter?.close();
    m.micMeter = null;
    m.remoteMeter?.close();
    m.remoteMeter = null;
    if (m.audio) m.audio.srcObject = null;
    releaseWakeLock();
    m.connected = false;
    m.blocked = false;
    m.speaking = false;
    m.deferred = null;
    m.afterSpeak = null;
    m.items.clear();
  }, [clearTimers, m, releaseWakeLock]);

  const goLogin = useCallback(() => router.replace("/login"), [router]);

  const refresh = useCallback(async (): Promise<SessionState | null> => {
    if (!m.sessionId) return null;
    const r = await call<SessionState>(`/api/voice/sessions/${m.sessionId}`);
    if (r.status === 401) goLogin();
    if (r.data) {
      setData(r.data);
      m.action = r.data.next_action;
      const last = Math.max(0, ...r.data.turns.map((t) => Date.parse(t.ended_at)));
      m.lastEnd = Math.max(m.lastEnd, last);
    }
    return r.data;
  }, [goLogin, m]);

  const ensureSession = useCallback(async (): Promise<string | null> => {
    if (m.sessionId) return m.sessionId;
    const r = await call<{ session: { session_id: string } }>("/api/voice/sessions", {
      method: "POST",
      body: JSON.stringify({ patient_ref: patientRef.trim(), data_class: "synthetic" }),
    });
    if (r.status === 401) goLogin();
    if (!r.data) return null;
    m.sessionId = r.data.session.session_id;
    await refresh();
    return m.sessionId;
  }, [goLogin, m, patientRef, refresh]);

  // ---------------------------------------------------------------- failure and end

  const fail = useCallback(
    (message: string) => {
      teardown();
      m.ending = false;
      setCause(message);
      setState("error");
    },
    [m, setState, teardown],
  );

  const endCall = useCallback(async () => {
    if (m.finishing) return;
    m.finishing = true;
    setFinishing(true);
    m.ending = true;
    m.finishFailed = false;
    teardown();
    if (!m.sessionId) {
      m.finishing = false;
      setFinishing(false);
      m.ending = false;
      setState("idle");
      return;
    }
    setState("processing");
    setCause(null);
    const r = await call<FinishResult>(`/api/voice/sessions/${m.sessionId}/finish`, { method: "POST" });
    if (r.status === 401) goLogin();
    if (!r.data) {
      m.finishing = false;
      setFinishing(false);
      m.finishFailed = true;
      setCause(ERROR_TH.finish);
      setState("error");
      return;
    }
    setSummary(r.data);
    await refresh();
    setState("ended");
  }, [goLogin, m, refresh, setState, teardown]);

  // ---------------------------------------------------------------- speaking (half-duplex)

  const speak = useCallback(
    (action: NextAction, final: boolean) => {
      const conn = m.conn;
      if (!conn || !m.connected) return;
      m.blocked = true;
      applyMic();
      setHint((h) => (h === HINT_TH.audioFailed ? null : h));
      setState("processing");
      if (final) {
        m.afterSpeak = () => void endCall();
        m.timers.end = setTimeout(() => void endCall(), HANDOFF_END_FALLBACK_MS);
      }
      m.timers.start = setTimeout(() => {
        // The model never started speaking: show the question on screen and hand the floor back.
        setHint(HINT_TH.audioFailed);
        unblock();
      }, SPEAK_START_FALLBACK_MS);
      conn.send(speakEvent(action.utterance_th, action.utterance_id));

      function unblock() {
        m.blocked = false;
        m.speaking = false;
        applyMic();
        if (final) return;
        if (m.state === "processing" || m.state === "speaking") setState("listening");
      }
    },
    [applyMic, endCall, m, setState],
  );

  /** Speak the server's next action once no newer turn is queued. */
  const afterServer = useCallback(
    (action: NextAction) => {
      m.action = action;
      if (!m.conn || !m.connected || m.finishing || m.pending > 0) return;
      if (m.blocked) {
        m.deferred = action;
        return;
      }
      if (action.action === "handoff") m.ending = true;
      applyMic();
      speak(action, action.action === "handoff");
    },
    [applyMic, m, speak],
  );

  const onSpeakStart = useCallback(() => {
    clearTimeout(m.timers.start);
    m.speaking = true;
    m.blocked = true;
    applyMic();
    setState("speaking");
  }, [applyMic, m, setState]);

  const onSpeakStop = useCallback(() => {
    m.speaking = false;
    clearTimeout(m.timers.tail);
    m.timers.tail = setTimeout(() => {
      m.blocked = false;
      applyMic();
      const after = m.afterSpeak;
      if (after) {
        m.afterSpeak = null;
        clearTimeout(m.timers.end);
        after();
        return;
      }
      m.conn?.send({ type: "input_audio_buffer.clear" });
      const deferred = m.deferred;
      if (deferred) {
        m.deferred = null;
        afterServer(deferred);
        return;
      }
      if (m.state === "speaking" || m.state === "processing") setState("listening");
    }, TAIL_MS);
  }, [afterServer, applyMic, m, setState]);

  // ---------------------------------------------------------------- turns

  const postTurn = useCallback(
    async (draft: TurnDraft) => {
      if (!m.sessionId) return;
      const startedMs = Math.max(draft.startMs, m.lastEnd);
      const endedMs = Math.max(draft.endMs, startedMs);
      const body: Record<string, unknown> = {
        speaker: draft.speaker,
        text: draft.text,
        started_at: new Date(startedMs).toISOString(),
        ended_at: new Date(endedMs).toISOString(),
        source: draft.source,
      };
      if (draft.source === "asr") body.asr_model = m.asrModel;
      const r = await call<TurnResponse>(`/api/voice/sessions/${m.sessionId}/turns`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (r.status === 401) goLogin();
      if (!r.data) {
        setHint(HINT_TH.turnFailed);
        return;
      }
      const resp = r.data;
      m.lastEnd = Math.max(m.lastEnd, Date.parse(resp.turn.ended_at), endedMs);
      setHint((h) => (h === HINT_TH.notHeard || h === HINT_TH.turnFailed ? null : h));
      if (resp.nurse_attention || resp.session?.nurse_attention) {
        // Red flag: stop listening at once; the alert renders from the session payload below.
        m.ending = true;
        applyMic();
      }
      setData((prev) =>
        prev ? { ...prev, session: resp.session, field_statuses: resp.field_statuses, next_action: resp.next_action } : prev,
      );
      await refresh();
      afterServer(resp.next_action);
    },
    [afterServer, applyMic, goLogin, m, refresh],
  );

  const enqueueTurn = useCallback(
    (draft: TurnDraft) => {
      m.pending += 1;
      if (m.state === "listening") setState("processing");
      m.chain = m.chain
        .then(() => postTurn(draft))
        .catch(() => setHint(HINT_TH.turnFailed))
        .finally(() => {
          m.pending -= 1;
          if (m.pending === 0 && !m.blocked && !m.ending && m.connected && m.state === "processing") setState("listening");
        });
      return m.chain;
    },
    [m, postTurn, setState],
  );

  const speakerRef = useRef<Speaker>("patient");

  const onEvent = useCallback(
    (evt: RealtimeEvent) => {
      const itemId = typeof evt.item_id === "string" ? evt.item_id : "?";
      switch (evt.type) {
        case "session.created":
          if (m.connected || m.finishing) return;
          m.connected = true;
          clearTimeout(m.timers.connect);
          setState("listening");
          m.deadline = Date.now() + m.maxMs;
          m.timers.tick = setInterval(() => {
            const left = Math.ceil(((m.deadline ?? 0) - Date.now()) / 1000);
            setRemaining(Math.max(0, left));
            if (left <= 0) void endCall();
          }, 500);
          acquireWakeLock();
          if (m.action) afterServer(m.action);
          break;
        case "input_audio_buffer.speech_started":
          m.items.set(itemId, { startMs: Date.now(), dropped: m.blocked || m.speaking });
          break;
        case "conversation.item.input_audio_transcription.completed": {
          const info = m.items.get(itemId);
          m.items.delete(itemId);
          if (info?.dropped || m.ending || m.finishing) return;
          const text = normaliseTranscript(typeof evt.transcript === "string" ? evt.transcript : "");
          if (!text) {
            setHint(HINT_TH.notHeard);
            return;
          }
          void enqueueTurn({ speaker: speakerRef.current, text, startMs: info?.startMs ?? Date.now(), endMs: Date.now(), source: "asr" });
          break;
        }
        case "conversation.item.input_audio_transcription.failed": {
          const info = m.items.get(itemId);
          m.items.delete(itemId);
          if (!info?.dropped && !m.ending) setHint(HINT_TH.notHeard);
          break;
        }
        case "output_audio_buffer.started":
          onSpeakStart();
          break;
        case "output_audio_buffer.stopped":
          onSpeakStop();
          break;
        case "response.done": {
          const status = (evt.response as { status?: string } | undefined)?.status;
          if (status && status !== "completed") {
            setHint(HINT_TH.audioFailed);
            clearTimeout(m.timers.start);
            m.blocked = false;
            m.speaking = false;
            applyMic();
            if (m.afterSpeak) {
              const after = m.afterSpeak;
              m.afterSpeak = null;
              clearTimeout(m.timers.end);
              after();
            } else if (m.state === "processing" || m.state === "speaking") setState("listening");
          }
          break;
        }
        default:
          break; // `error` and everything else are non-fatal; connection health comes from the peer connection
      }
    },
    [acquireWakeLock, afterServer, applyMic, endCall, enqueueTurn, m, onSpeakStart, onSpeakStop, setState],
  );

  // ---------------------------------------------------------------- start

  const start = useCallback(async () => {
    if (m.state !== "idle" && m.state !== "error") return;
    if (m.finishFailed) {
      void endCall();
      return;
    }
    setCause(null);
    setCodeError(null);
    setHint(null);
    if (cfg?.access_code_required && !accessCode.trim()) {
      setCodeError(ERROR_TH.codeMissing);
      setState("idle");
      return;
    }
    if (window.isSecureContext === false || !navigator.mediaDevices?.getUserMedia) {
      fail(ERROR_TH.insecure);
      return;
    }
    m.ending = false;
    setState("connecting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      fail(ERROR_TH.mic);
      return;
    }
    m.mic = stream;
    m.micMeter = createLevelMeter(stream);
    m.muted = false;
    setMutedState(false);

    const sid = await ensureSession();
    if (!sid) {
      fail(ERROR_TH.connect);
      return;
    }
    const r = await call<RealtimeSession>("/api/voice/realtime/session", {
      method: "POST",
      body: JSON.stringify({ voice_session_id: sid, access_code: accessCode.trim() || null }),
    });
    if (r.status === 401) goLogin();
    if (!r.data) {
      const reason = reasonOf(r.body);
      if (r.status === 403 && reason === "access_code_invalid") {
        teardown();
        setCodeError(ERROR_TH.codeInvalid);
        setState("idle");
      } else if (r.status === 429) fail(ERROR_TH.rateLimited);
      else fail(ERROR_TH.connect);
      return;
    }
    const session = r.data;
    m.asrModel = session.transcribe_model;
    m.maxMs = session.max_session_seconds * 1000; // the countdown starts at session.created
    setRemaining(session.max_session_seconds);
    setVendorLabel(session.vendor_label);
    try {
      m.timers.connect = setTimeout(() => fail(ERROR_TH.connect), CONNECT_TIMEOUT_MS);
      m.conn = await connectRealtime({
        clientSecret: session.client_secret,
        connectUrl: session.connect_url,
        micStream: stream,
        onEvent,
        onRemoteStream: (remote) => {
          if (m.audio) {
            m.audio.srcObject = remote;
            void m.audio.play?.()?.catch(() => undefined);
          }
          m.remoteMeter?.close();
          m.remoteMeter = createLevelMeter(remote);
        },
        onConnectionState: (s) => {
          if (m.ending || m.finishing) return;
          if (s === "failed") fail(ERROR_TH.connect);
          else if (s === "disconnected") m.timers.drop = setTimeout(() => fail(ERROR_TH.connect), DISCONNECT_GRACE_MS);
          else if (s === "connected") clearTimeout(m.timers.drop);
        },
      });
      applyMic();
    } catch {
      fail(ERROR_TH.connect);
    }
  }, [accessCode, applyMic, cfg, endCall, ensureSession, fail, goLogin, m, onEvent, setState, teardown]);

  // ---------------------------------------------------------------- controls

  const toggleMute = useCallback(() => {
    m.muted = !m.muted;
    setMutedState(m.muted);
    applyMic();
  }, [applyMic, m]);

  const close = useCallback(() => {
    teardown();
    const home = params.caseId && params.runId ? `/app/cases/${params.caseId}/overview?run=${encodeURIComponent(params.runId)}` : "/app/queue";
    router.push(home);
  }, [params.caseId, params.runId, router, teardown]);

  const submitTyped = useCallback(
    async (speaker: Speaker, text: string): Promise<boolean> => {
      const clean = text.trim();
      if (!clean || m.finishing) return false;
      setTypedBusy(true);
      try {
        const sid = await ensureSession();
        if (!sid) {
          setHint(HINT_TH.turnFailed);
          return false;
        }
        const now = Date.now();
        await enqueueTurn({ speaker, text: clean, startMs: now, endMs: now, source: "typed" });
        return true;
      } finally {
        setTypedBusy(false);
      }
    },
    [enqueueTurn, ensureSession, m],
  );

  // ---------------------------------------------------------------- lifecycle

  useEffect(() => {
    let active = true;
    (async () => {
      const c = await call<RealtimeConfig>("/api/voice/realtime/config");
      if (!active) return;
      if (c.status === 401) {
        goLogin();
        return;
      }
      if (params.sessionParam) {
        const r = await call<SessionState>(`/api/voice/sessions/${params.sessionParam}`);
        if (active && r.data && r.data.session.status === "active") {
          m.sessionId = params.sessionParam;
          setData(r.data);
          m.action = r.data.next_action;
          m.lastEnd = Math.max(0, ...r.data.turns.map((t) => Date.parse(t.ended_at)));
          setPatientRef(r.data.session.patient_ref);
        }
      }
      if (!active) return;
      if (c.data) {
        setCfg(c.data);
        setVendorLabel(c.data.vendor_label);
      } else setCfgFailed(true);
      if (c.data?.enabled) setState("idle");
      else {
        setState("disabled");
        await ensureSession();
      }
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && m.connected && !m.finishing) acquireWakeLock();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [acquireWakeLock, m]);

  useEffect(() => () => teardown(), [teardown]);

  const getLevel = useCallback((): number => {
    const meter = m.state === "speaking" ? m.remoteMeter : m.state === "listening" && !m.muted ? m.micMeter : null;
    return meter?.level() ?? 0;
  }, [m]);

  return {
    state, cfg, cfgFailed, vendorLabel, cause, hint, data, summary, muted, remaining, accessCode, codeError, patientRef,
    typeOpen, typedBusy, finishing,
    setAccessCode, setPatientRef, setTypeOpen, setSpeaker: (s: Speaker) => void (speakerRef.current = s),
    start, endCall, close, toggleMute, submitTyped, getLevel, audioRef,
    retry: () => (m.finishFailed ? void endCall() : void start()),
  };
}
