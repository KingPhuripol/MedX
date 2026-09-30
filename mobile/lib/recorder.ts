/**
 * Recording controller (SPEC §3.1 state machine, §11 T1–T9). Framework-free so it can be driven with fake
 * timers; React reads it through `subscribe`/`getSnapshot`. Lifecycle logic is ported from
 * web/components/live/useLiveCall.ts and adapted to transcription-only events.
 */
import { call, post, reasonOf } from "./api";
import {
  connectRealtime,
  createLevelMeter,
  normaliseTranscript,
  type LevelMeter,
  type RealtimeConfig,
  type RealtimeConnection,
  type RealtimeEvent,
  type RealtimeSession,
} from "./realtime";
import { TurnQueue, type TurnBody } from "./turnQueue";
import { applyGet, applyTurn, isRedFlag, type Scribe, type SessionGet, type TurnResponse } from "./voice";

export type RecState =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "listening"
  | "paused"
  | "reconnecting"
  | "error"
  | "permission_denied"
  | "finishing";

export type ErrorKind = "attempts" | "no_mic" | "voice_unavailable" | "access_code" | "session_ended";

export const MAX_ATTEMPTS = 3;
export const BACKOFF_MS = [1000, 2000, 4000] as const;
export const DISCONNECT_GRACE_MS = 2000;
export const OPEN_TIMEOUT_MS = 15000;
export const ROLLOVER_QUIET_MS = 30000;
export const ROLLOVER_HARD_MS = 5000;
export const ROLLOVER_DRAIN_MS = 3000;
export const FINISH_DRAIN_MS = 5000;

export interface Line {
  key: string;
  text: string;
  atMs: number;
}

export interface RedFlag {
  quote: string;
  atMs: number;
}

export interface RecSnapshot {
  rec: RecState;
  errorKind: ErrorKind | null;
  systemPause: boolean;
  attempt: number;
  lines: Line[];
  interim: Line | null;
  failedSegments: number;
  turnCount: number;
  scribe: Scribe;
  redFlag: RedFlag | null;
  ackAtMs: number | null;
  finishBlocked: boolean;
  /** Last `suggested_question_th` ever received (kept when the slot goes neutral). */
  lastQuestion: string | null;
  clockMs: number;
  clockSince: number | null;
}

export interface RecorderInit {
  sessionId: string;
  scribe: Scribe;
  config: RealtimeConfig | null;
  accessCode: string;
  onAuthLost: () => void;
}

type Attempt =
  | { kind: "ok" }
  | { kind: "aborted" }
  | { kind: "fatal"; error: ErrorKind }
  | { kind: "retry"; retryAfterMs?: number };

type WakeLock = { release(): Promise<void> };

const LISTENABLE: RecState[] = ["connecting", "reconnecting", "listening"];

export class Recorder {
  private snap: RecSnapshot;
  private subs = new Set<() => void>();
  private conn: RealtimeConnection | null = null;
  private gen = 0;
  private mic: MediaStream | null = null;
  private meter: LevelMeter | null = null;
  private wake: WakeLock | null = null;
  private wakePending = false;
  private inflight = false;
  private disposed = false;
  private speaking = false;
  private openedAt = 0;
  private maxMs = 0;
  private asrModel = "";
  private accessCode: string;
  private config: RealtimeConfig | null;
  private t: Partial<Record<"backoff" | "grace" | "open" | "roll", ReturnType<typeof setTimeout>>> = {};
  readonly queue: TurnQueue<TurnResponse, SessionGet>;
  readonly sessionId: string;
  private onAuthLost: () => void;

  constructor(init: RecorderInit) {
    this.sessionId = init.sessionId;
    this.accessCode = init.accessCode;
    this.config = init.config;
    this.onAuthLost = init.onAuthLost;
    this.snap = {
      rec: "idle",
      errorKind: null,
      systemPause: false,
      attempt: 0,
      lines: [],
      interim: null,
      failedSegments: 0,
      turnCount: 0,
      scribe: init.scribe,
      redFlag: null,
      ackAtMs: null,
      finishBlocked: false,
      lastQuestion: init.scribe.next_action?.suggested_question_th ?? null,
      clockMs: 0,
      clockSince: null,
    };
    this.queue = new TurnQueue<TurnResponse, SessionGet>({
      post: (body) => post<TurnResponse>(`/api/voice/sessions/${this.sessionId}/turns`, body),
      fetchSession: async () => {
        const r = await call<SessionGet>(`/api/voice/sessions/${this.sessionId}`);
        if (r.status === 401) this.authLost();
        return r.data ? { turns: r.data.turns, data: r.data } : null;
      },
      onPosted: (body, resp) => this.onServer(body, resp, applyTurn(this.snap.scribe, resp), this.snap.turnCount + 1),
      onReconciled: (body, data) => this.onServer(body, data, applyGet(this.snap.scribe, data), data.turns.length),
      onFatal: (kind) => {
        if (kind === "auth") this.authLost();
        else this.setError("session_ended");
      },
      onFailed: () => this.patch({ failedSegments: this.snap.failedSegments + 1 }),
      asrModel: () => this.asrModel,
      now: () => Date.now(),
    });
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", this.onVisibility);
      window.addEventListener("online", this.onOnline);
      window.addEventListener("offline", this.onOffline);
    }
  }

  // ------------------------------------------------------------------ store

  subscribe = (fn: () => void) => {
    this.subs.add(fn);
    return () => void this.subs.delete(fn);
  };

  getSnapshot = () => this.snap;

  private patch(p: Partial<RecSnapshot>) {
    this.snap = { ...this.snap, ...p };
    for (const fn of this.subs) fn();
  }

  private setRec(rec: RecState, extra: Partial<RecSnapshot> = {}) {
    const prev = this.snap.rec;
    const now = Date.now();
    let { clockMs, clockSince } = this.snap;
    if (prev === "listening" && rec !== "listening" && clockSince !== null) {
      clockMs += now - clockSince;
      clockSince = null;
    }
    if (rec === "listening" && prev !== "listening") clockSince = now;
    this.patch({ rec, clockMs, clockSince, ...extra });
    if (rec === "listening") this.acquireWake();
    else this.releaseWake();
  }

  // ------------------------------------------------------------------ public controls

  /** The centre record button (SPEC §3.1 table). */
  press() {
    switch (this.snap.rec) {
      case "idle":
      case "permission_denied":
        return void this.start();
      case "listening":
        return this.pause();
      case "paused":
        return void this.resume();
      case "error":
        return void this.retry();
      default:
        return;
    }
  }

  pause(system = false) {
    if (this.snap.rec !== "listening") return;
    this.conn?.setMic(false);
    this.setRec("paused", { systemPause: system });
  }

  async resume() {
    if (this.snap.rec !== "paused") return;
    this.patch({ systemPause: false });
    if (!this.micLive()) return this.start();
    if (this.conn?.isOpen()) {
      this.conn.setMic(true);
      this.setRec("listening");
      return;
    }
    this.closeConn();
    this.connectFresh();
  }

  async retry() {
    if (this.snap.rec !== "error") return;
    if (!this.micLive()) return this.start();
    this.connectFresh();
  }

  acknowledge() {
    if (!this.snap.redFlag || this.snap.ackAtMs !== null) return;
    this.patch({ ackAtMs: Date.now(), finishBlocked: false });
  }

  setAccessCode(code: string) {
    this.accessCode = code;
  }

  canFinish(): boolean {
    const { rec, turnCount } = this.snap;
    if (["listening", "paused", "reconnecting", "error"].includes(rec)) return true;
    return (rec === "connecting" || rec === "permission_denied") && turnCount > 0;
  }

  /** T9. "blocked" when a red flag is unacknowledged (the alert takes focus instead). */
  async finish(): Promise<"blocked" | "done" | "busy"> {
    if (this.snap.redFlag && this.snap.ackAtMs === null) {
      this.patch({ finishBlocked: true });
      return "blocked";
    }
    if (!this.canFinish()) return "busy";
    this.conn?.setMic(false);
    this.stopMic();
    this.setRec("finishing");
    await this.queue.waitIdle(FINISH_DRAIN_MS);
    this.closeConn();
    this.queue.dropPending();
    const r = await call<SessionGet>(`/api/voice/sessions/${this.sessionId}`);
    if (r.status === 401) this.authLost();
    if (r.data) this.patch({ scribe: applyGet(this.snap.scribe, r.data) });
    return "done";
  }

  /** "บันทึกต่อ" from review: back to recording, paused, on the same active session. */
  reopen() {
    this.queue.restart();
    this.setRec("paused", { systemPause: false, errorKind: null });
  }

  hasMeter(): boolean {
    return !!this.meter;
  }

  /** Mic level 0..1 for the meter; 0 unless listening. */
  getLevel(): number {
    return this.snap.rec === "listening" ? (this.meter?.level() ?? 0) : 0;
  }

  dispose() {
    this.disposed = true;
    this.queue.stop();
    this.closeConn();
    this.stopMic();
    this.releaseWake();
    for (const k of Object.keys(this.t) as (keyof typeof this.t)[]) clearTimeout(this.t[k]);
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", this.onVisibility);
      window.removeEventListener("online", this.onOnline);
      window.removeEventListener("offline", this.onOffline);
    }
    this.subs.clear();
  }

  // ------------------------------------------------------------------ mic and connect (T1, T7)

  private micLive(): boolean {
    return !!this.mic && this.mic.getAudioTracks().some((t) => t.readyState !== "ended");
  }

  private stopMic() {
    this.mic?.getTracks().forEach((t) => t.stop());
    this.mic = null;
    this.meter?.close();
    this.meter = null;
  }

  private async start() {
    const rec = this.snap.rec;
    if (rec !== "idle" && rec !== "permission_denied" && rec !== "paused" && rec !== "error") return;
    this.setRec("requesting_permission", { errorKind: null });
    const md = typeof navigator !== "undefined" ? navigator.mediaDevices : undefined;
    if (!md?.getUserMedia) return this.setError("no_mic");
    let stream: MediaStream;
    try {
      stream = await md.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    } catch (err) {
      if (this.disposed) return;
      const name = (err as { name?: string } | null)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") return this.setRec("permission_denied");
      return this.setError("no_mic");
    }
    if (this.disposed) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    this.mic = stream;
    this.meter = createLevelMeter(stream);
    this.connectFresh();
  }

  private connectFresh() {
    this.patch({ attempt: 0, errorKind: null });
    this.setRec("connecting");
    void this.attemptNow();
  }

  private async attemptNow() {
    clearTimeout(this.t.backoff);
    this.t.backoff = undefined;
    if (this.inflight || this.disposed) return;
    this.inflight = true;
    let res: Attempt;
    try {
      res = await this.connect();
    } finally {
      this.inflight = false;
    }
    if (this.disposed) return;
    if (res.kind === "fatal") this.setError(res.error);
    else if (res.kind === "retry") this.scheduleReconnect(res.retryAfterMs);
  }

  private async connect(): Promise<Attempt> {
    const cfg = this.config;
    if (cfg && (!cfg.enabled || cfg.ambient_supported === false)) return { kind: "fatal", error: "voice_unavailable" };
    const token = this.gen;
    const body: Record<string, unknown> = { voice_session_id: this.sessionId, purpose: "ambient" };
    if (this.accessCode.trim()) body.access_code = this.accessCode.trim();
    const r = await post<RealtimeSession>("/api/voice/realtime/session", body);
    if (token !== this.gen || !LISTENABLE.includes(this.snap.rec)) return { kind: "aborted" };
    if (r.status === 401) {
      this.authLost();
      return { kind: "aborted" };
    }
    if (!r.data) {
      if (r.status === 403) {
        return { kind: "fatal", error: reasonOf(r.body) === "access_code_invalid" ? "access_code" : "voice_unavailable" };
      }
      if (r.status === 404 || r.status === 409) return { kind: "fatal", error: "session_ended" };
      if (r.status === 503) return { kind: "fatal", error: "voice_unavailable" };
      if (r.status === 429) return { kind: "retry", retryAfterMs: r.retryAfterMs ?? undefined };
      return { kind: "retry" };
    }
    const s = r.data;
    if (typeof s.connect_url !== "string" || !s.connect_url.startsWith("https://")) {
      return { kind: "fatal", error: "voice_unavailable" };
    }
    if (!this.micLive()) return { kind: "fatal", error: "no_mic" };
    this.asrModel = s.transcribe_model;
    this.maxMs = Math.max(0, s.max_session_seconds) * 1000;
    this.closeConn(); // at most one peer connection at any time
    const gen = this.gen;
    try {
      const conn = await connectRealtime({
        clientSecret: s.client_secret,
        connectUrl: s.connect_url,
        dataChannel: s.data_channel,
        micStream: this.mic as MediaStream,
        onEvent: (e) => gen === this.gen && this.onEvent(e),
        onOpen: () => gen === this.gen && this.onOpen(),
        onClose: () => gen === this.gen && this.onDrop(),
        onConnectionState: (st) => gen === this.gen && this.onPcState(st),
      });
      if (gen !== this.gen || !LISTENABLE.includes(this.snap.rec)) {
        conn.close();
        return { kind: "aborted" };
      }
      this.conn = conn;
      conn.setMic(true);
      if (this.snap.rec !== "listening") {
        this.t.open = setTimeout(() => gen === this.gen && this.snap.rec !== "listening" && this.onDrop(), OPEN_TIMEOUT_MS);
      }
      return { kind: "ok" };
    } catch (err) {
      if ((err as { kind?: string }).kind === "url") return { kind: "fatal", error: "voice_unavailable" };
      return { kind: "retry" };
    }
  }

  /** Close the current connection. Bumping `gen` makes every late callback and in-flight connect stale. */
  private closeConn() {
    this.gen += 1;
    clearTimeout(this.t.grace);
    clearTimeout(this.t.open);
    clearTimeout(this.t.roll);
    this.conn?.close();
    this.conn = null;
    this.speaking = false;
  }

  private setError(kind: ErrorKind) {
    clearTimeout(this.t.backoff);
    this.closeConn();
    this.queue.dropPending();
    this.mic?.getAudioTracks().forEach((t) => (t.enabled = false));
    this.setRec("error", { errorKind: kind });
  }

  private authLost() {
    this.dispose();
    this.onAuthLost();
  }

  // ------------------------------------------------------------------ connection health (T6)

  private onOpen() {
    clearTimeout(this.t.open);
    this.openedAt = Date.now();
    this.mic?.getAudioTracks().forEach((t) => (t.enabled = true));
    if (this.snap.rec === "connecting" || this.snap.rec === "reconnecting") this.setRec("listening", { attempt: 0 });
    this.scheduleRollover();
  }

  private onPcState(st: RTCPeerConnectionState) {
    if (st === "failed" || st === "closed") return this.onDrop();
    if (st === "disconnected") {
      clearTimeout(this.t.grace);
      const gen = this.gen;
      this.t.grace = setTimeout(() => gen === this.gen && this.onDrop(), DISCONNECT_GRACE_MS);
    } else if (st === "connected") clearTimeout(this.t.grace);
  }

  /** Unexpected loss of the connection. While paused it is silent: resume re-mints (T8). */
  private onDrop() {
    const rec = this.snap.rec;
    if (rec === "paused") {
      this.closeConn();
      this.queue.dropPending();
      return;
    }
    if (!LISTENABLE.includes(rec)) return;
    this.closeConn();
    this.queue.dropPending();
    this.scheduleReconnect();
  }

  private scheduleReconnect(retryAfterMs?: number) {
    if (this.snap.attempt >= MAX_ATTEMPTS) return this.setError("attempts");
    const attempt = this.snap.attempt + 1;
    this.setRec("reconnecting", { attempt });
    clearTimeout(this.t.backoff);
    this.t.backoff = setTimeout(() => void this.attemptNow(), retryAfterMs ?? BACKOFF_MS[attempt - 1]);
  }

  private scheduleRollover() {
    clearTimeout(this.t.roll);
    if (!this.maxMs) return;
    const gen = this.gen;
    const quietAt = this.maxMs - ROLLOVER_QUIET_MS;
    const hardAt = this.maxMs - ROLLOVER_HARD_MS;
    const check = () => {
      if (gen !== this.gen) return;
      const elapsed = Date.now() - this.openedAt;
      if (elapsed >= hardAt || (elapsed >= quietAt && !this.speaking)) return void this.rollover();
      this.t.roll = setTimeout(check, elapsed < quietAt ? quietAt - elapsed : 250);
    };
    this.t.roll = setTimeout(check, Math.max(0, quietAt));
  }

  /** Planned rollover before the vendor's session limit: drain, close, re-mint through the same path. */
  private async rollover() {
    if (this.snap.rec === "paused") {
      this.closeConn();
      this.queue.dropPending();
      return;
    }
    if (this.snap.rec !== "listening") return;
    const gen = this.gen;
    const until = Date.now() + ROLLOVER_DRAIN_MS;
    while (this.queue.pendingCompletions() > 0 && Date.now() < until && gen === this.gen) {
      await new Promise((r) => setTimeout(r, 100));
    }
    if (gen !== this.gen) return;
    this.closeConn();
    this.queue.dropPending();
    if (this.snap.rec !== "listening") return;
    this.patch({ attempt: 0 });
    this.setRec("connecting");
    void this.attemptNow();
  }

  // ------------------------------------------------------------------ events (T3)

  private onEvent(e: RealtimeEvent) {
    const id = typeof e.item_id === "string" ? e.item_id : null;
    switch (e.type) {
      case "input_audio_buffer.speech_started":
        this.speaking = true;
        if (id) this.queue.speechStarted(id);
        return;
      case "input_audio_buffer.speech_stopped":
        this.speaking = false;
        if (id) this.queue.speechStopped(id);
        return;
      case "input_audio_buffer.committed":
        if (id) this.queue.committed(id);
        return;
      case "conversation.item.input_audio_transcription.delta": {
        if (!id || typeof e.delta !== "string") return;
        const prev = this.snap.interim?.key === id ? this.snap.interim.text : "";
        this.patch({ interim: { key: id, text: prev + e.delta, atMs: this.snap.interim?.atMs ?? Date.now() } });
        return;
      }
      case "conversation.item.input_audio_transcription.completed": {
        if (!id) return;
        const transcript = typeof e.transcript === "string" ? e.transcript : "";
        const interim = this.snap.interim?.key === id ? null : this.snap.interim;
        const atMs = this.snap.interim?.key === id ? this.snap.interim.atMs : Date.now();
        const fresh = this.queue.completed(id, transcript);
        const text = normaliseTranscript(transcript);
        this.patch({ interim, lines: fresh && text ? [...this.snap.lines, { key: id, text, atMs }] : this.snap.lines });
        return;
      }
      case "conversation.item.input_audio_transcription.failed":
        if (!id) return;
        if (this.snap.interim?.key === id) this.patch({ interim: null });
        this.queue.failed(id);
        return;
      case "error":
        return this.onDrop();
      default:
        return; // response.*, output audio/text and everything else: ignored, never rendered
    }
  }

  private onServer(body: TurnBody, payload: TurnResponse | SessionGet, scribe: Scribe, turnCount: number) {
    const q = scribe.next_action?.suggested_question_th;
    let redFlag = this.snap.redFlag;
    if (!redFlag && isRedFlag(payload)) {
      redFlag = { quote: body.text, atMs: Date.parse(body.started_at) };
      try {
        navigator.vibrate?.([200, 100, 200]);
      } catch {
        /* unsupported */
      }
    }
    this.patch({ scribe, turnCount, redFlag, lastQuestion: q ?? this.snap.lastQuestion });
  }

  // ------------------------------------------------------------------ lifecycle (T8)

  private onVisibility = () => {
    if (document.visibilityState === "hidden" && this.snap.rec === "listening") this.pause(true);
  };

  private onOnline = () => {
    if (this.snap.rec === "reconnecting" && this.t.backoff !== undefined) void this.attemptNow();
  };

  private onOffline = () => {
    if (this.snap.rec === "listening") this.onDrop();
  };

  private acquireWake() {
    const wl = (navigator as unknown as { wakeLock?: { request(t: "screen"): Promise<WakeLock> } }).wakeLock;
    if (!wl || this.wake || this.wakePending) return;
    this.wakePending = true;
    wl.request("screen")
      .then((lock) => {
        this.wakePending = false;
        if (this.snap.rec === "listening" && !this.disposed) this.wake = lock;
        else void lock.release().catch(() => undefined);
      })
      .catch(() => {
        this.wakePending = false;
      });
  }

  private releaseWake() {
    const lock = this.wake;
    this.wake = null;
    void lock?.release().catch(() => undefined);
  }
}
