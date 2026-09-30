/**
 * Test doubles for jsdom: a fake WebRTC stack (RTCPeerConnection + data channel), mic, wake lock, and a
 * fetch router that answers /api/* with contract fixtures. Everything is synthetic and offline.
 */
import { act, render } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, vi } from "vitest";

import { Recording } from "@/components/Recording";
import { Recorder, type RecorderInit } from "@/lib/recorder";
import { fromStart } from "@/lib/voice";

import config from "./fixtures/realtime-config.json";
import mint from "./fixtures/realtime-session.json";
import { reviewSession, startResponse, turnResponse } from "./fixtures/scenario";

export class FakeDC {
  readyState: RTCDataChannelState = "connecting";
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  constructor(
    readonly label: string,
    private rtc: FakeRtc,
  ) {}
  send(d: string) {
    this.rtc.sent.push(d);
  }
  close() {
    this.readyState = "closed";
  }
}

export class FakeRtc {
  pcs: FakePC[] = [];
  sent: string[] = [];
  open = 0;
  maxOpen = 0;
  /** When false, the data channel does not open by itself after the answer. */
  autoOpen = true;
  ontrackCalls = 0;
  last(): FakePC {
    return this.pcs[this.pcs.length - 1];
  }
  emit(evt: Record<string, unknown>, pc: FakePC = this.last()) {
    pc.dc?.onmessage?.({ data: JSON.stringify(evt) });
  }
  /** One transcribed item: speech_started → speech_stopped → committed → completed. */
  say(id: string, text: string, pc: FakePC = this.last()) {
    this.emit({ type: "input_audio_buffer.speech_started", item_id: id }, pc);
    this.emit({ type: "input_audio_buffer.speech_stopped", item_id: id }, pc);
    this.emit({ type: "input_audio_buffer.committed", item_id: id }, pc);
    this.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: id, transcript: text }, pc);
  }
  drop(pc: FakePC = this.last()) {
    pc.connectionState = "failed";
    pc.onconnectionstatechange?.();
  }
}

export class FakePC {
  connectionState: RTCPeerConnectionState = "new";
  closed = false;
  dc: FakeDC | null = null;
  tracks: unknown[] = [];
  ontrack: ((e: unknown) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  constructor(private rtc: FakeRtc) {
    rtc.pcs.push(this);
    rtc.open += 1;
    rtc.maxOpen = Math.max(rtc.maxOpen, rtc.open);
  }
  addTrack(t: unknown) {
    this.tracks.push(t);
  }
  createDataChannel(label: string) {
    this.dc = new FakeDC(label, this.rtc);
    return this.dc;
  }
  async createOffer() {
    return { type: "offer", sdp: "v=0 fake-offer" };
  }
  async setLocalDescription() {}
  async setRemoteDescription() {
    if (!this.rtc.autoOpen) return;
    queueMicrotask(() => this.openNow());
  }
  openNow() {
    if (this.closed || !this.dc) return;
    this.dc.readyState = "open";
    this.connectionState = "connected";
    this.dc.onopen?.();
  }
  close() {
    if (!this.closed) this.rtc.open -= 1;
    this.closed = true;
    this.connectionState = "closed";
  }
}

export interface FakeTrack {
  kind: "audio";
  enabled: boolean;
  readyState: "live" | "ended";
  stop(): void;
}

export function fakeStream() {
  const track: FakeTrack = {
    kind: "audio",
    enabled: true,
    readyState: "live",
    stop() {
      this.readyState = "ended";
    },
  };
  return { track, stream: { getAudioTracks: () => [track], getTracks: () => [track] } as unknown as MediaStream };
}

export interface Browser {
  rtc: FakeRtc;
  gum: ReturnType<typeof vi.fn>;
  track: FakeTrack;
  wake: { requested: number; released: number; held: number };
}

/** Installs RTCPeerConnection, getUserMedia and wakeLock fakes on the jsdom globals. */
export function installBrowser(opts: { gumError?: string } = {}): Browser {
  const rtc = new FakeRtc();
  const { track, stream } = fakeStream();
  const gum = vi.fn(async () => {
    if (opts.gumError) throw Object.assign(new Error(opts.gumError), { name: opts.gumError });
    track.readyState = "live";
    return stream;
  });
  const wake = { requested: 0, released: 0, held: 0 };
  vi.stubGlobal(
    "RTCPeerConnection",
    class extends FakePC {
      constructor() {
        super(rtc);
      }
    },
  );
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: gum } });
  Object.defineProperty(navigator, "wakeLock", {
    configurable: true,
    value: {
      request: async () => {
        wake.requested += 1;
        wake.held += 1;
        let done = false;
        return {
          release: async () => {
            if (done) return;
            done = true;
            wake.released += 1;
            wake.held -= 1;
          },
        };
      },
    },
  });
  return { rtc, gum, track, wake };
}

type HandlerResult = { status: number; body?: unknown; headers?: Record<string, string>; text?: string } | "network";
export type Handler = (req: { url: string; method: string; body: unknown; init: RequestInit }) =>
  | HandlerResult
  | Promise<HandlerResult>;

export interface Api {
  calls: { url: string; method: string; body: unknown; init: RequestInit }[];
  posted: Record<string, unknown>[];
  turns: unknown[];
  mint: { status: number; body?: unknown; headers?: Record<string, string> }[];
  turnStatus: (number | "network")[];
  sessionGet: unknown;
  on: Record<string, Handler>;
  fetch: ReturnType<typeof vi.fn>;
}

/**
 * fetch router. `api.turns` answers successive turn POSTs (a generic 200 when empty); `api.turnStatus` forces a status
 * for the next turn POSTs; `api.mint` queues mint replies (default 200 fixture); `api.on[path]` overrides.
 */
export function installApi(patch: Partial<Api> = {}): Api {
  const api: Api = {
    calls: [],
    posted: [],
    turns: [],
    mint: [],
    turnStatus: [],
    sessionGet: reviewSession(),
    on: {},
    fetch: vi.fn(),
    ...patch,
  };
  const reply = (status: number, body?: unknown, headers: Record<string, string> = {}, text?: string) =>
    new Response(text ?? (body === undefined ? null : JSON.stringify(body)), {
      status,
      headers: { "Content-Type": text ? "application/sdp" : "application/json", ...headers },
    });
  api.fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = (init.method ?? "GET").toUpperCase();
    let body: unknown = init.body;
    try {
      body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    } catch {
      /* SDP text */
    }
    const req = { url, method, body, init };
    api.calls.push(req);
    const path = url.startsWith("http") ? new URL(url).pathname : url;
    const custom = api.on[path] ?? api.on[`${method} ${path}`];
    if (custom) {
      const r = await custom(req);
      if (r === "network") throw new TypeError("network");
      return reply(r.status, r.body, r.headers, r.text);
    }
    if (url.startsWith("https://")) return reply(201, undefined, {}, "v=0 fake-answer");
    if (path === "/api/me") return reply(200, { user: { id: 2, username: "nurse1", role: "nurse" } });
    if (path === "/api/voice/realtime/config") return reply(200, config);
    if (path === "/api/voice/realtime/session") {
      const m = api.mint.shift();
      return m ? reply(m.status, m.body, m.headers) : reply(200, mint);
    }
    if (path === "/api/voice/sessions" && method === "POST") return reply(200, startResponse());
    if (path.endsWith("/turns") && method === "POST") {
      api.posted.push(body as Record<string, unknown>);
      const forced = api.turnStatus.shift();
      if (forced === "network") throw new TypeError("network");
      if (forced !== undefined) return reply(forced, { detail: "forced" });
      const next = api.turns.shift();
      const b = body as { text: string; started_at: string };
      const id = `vt_${api.posted.length}`;
      return reply(200, next ?? turnResponse({ turnId: id, text: b.text, startedAt: b.started_at, known: {} }));
    }
    if (path.endsWith("/finish")) return reply(200, { session: {} });
    if (path.startsWith("/api/voice/sessions/") && method === "GET") return reply(200, api.sessionGet);
    if (path.startsWith("/api/auth/")) return reply(200, { user: { id: 2, username: "nurse1", role: "nurse" } });
    return reply(404, { detail: "unmocked" });
  });
  vi.stubGlobal("fetch", api.fetch);
  return api;
}

/** Let promises and zero-delay timers settle (works with fake timers). */
export async function flush(ms = 0) {
  if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(ms);
  else {
    for (let i = 0; i < 10; i++) await Promise.resolve();
    await new Promise((r) => setTimeout(r, ms));
  }
}

const liveRecorders: { dispose(): void }[] = [];
afterEach(() => liveRecorders.splice(0).forEach((r) => r.dispose()));

/** A Recorder on the start fixture with a spy for auth loss. */
export async function makeRecorder(patch: Partial<RecorderInit> = {}) {
  const start = startResponse();
  const onAuthLost = vi.fn();
  const rec = new Recorder({
    sessionId: start.session.session_id,
    scribe: fromStart(start as never),
    config: config as never,
    accessCode: "",
    onAuthLost,
    ...patch,
  });
  liveRecorders.push(rec);
  return { rec, onAuthLost, sessionId: start.session.session_id };
}

/** Render the Recording screen on a real Recorder over the fakes. */
export async function renderRecording(opts: { gumError?: string; patch?: Partial<Api>; init?: Partial<RecorderInit> } = {}) {
  const b = installBrowser({ gumError: opts.gumError });
  const api = installApi(opts.patch);
  const r = await makeRecorder(opts.init);
  const onFinished = vi.fn();
  const onBackToStart = vi.fn();
  const patient = { id: "SYN-2026-0023", sex: "หญิง", age: 46, bed: "เตียง 7" };
  const view = render(createElement(Recording, { recorder: r.rec, patient, onFinished, onBackToStart }));
  return { b, api, ...r, onFinished, onBackToStart, view };
}

/** Advance fake timers inside act() so React commits the recorder's updates. */
export async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}
