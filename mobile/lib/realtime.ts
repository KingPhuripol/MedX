/**
 * Transcription-only realtime transport (slice v2c SPEC §11 T1–T3). Ported from web/lib/realtime.ts, not imported.
 *
 * The phone streams mic audio to the vendor and only receives transcription events. The client never makes
 * the model speak: the data-channel sender has a frozen allowlist (T2), no media element is ever created for
 * a remote track, and the vendor URL comes only from the server mint (`connect_url`).
 */

export interface RealtimeConfig {
  enabled: boolean;
  reason: string | null;
  access_code_required: boolean;
  ambient_supported?: boolean;
  ambient_model?: string;
  max_session_seconds: number;
  vendor_label: string;
}

export interface RealtimeSession {
  client_secret: string;
  expires_at: number;
  connect_url: string;
  data_channel: string;
  model: string;
  transcribe_model: string;
  vendor_label: string;
  max_session_seconds: number;
  instructions_version: string;
}

/** A server event received on the data channel. Only `type` is relied on; other fields are read defensively. */
export type RealtimeEvent = { type: string } & Record<string, unknown>;

/** T2: the only client event type that may ever be sent. Everything else throws before `send`. */
export const ALLOWED_CLIENT_EVENTS: readonly string[] = Object.freeze(["input_audio_buffer.clear"]);

export class RealtimeConnectError extends Error {
  constructor(
    readonly kind: "sdp" | "network" | "url",
    readonly status?: number,
  ) {
    super(`realtime connect failed (${kind}${status ? ` ${status}` : ""})`);
  }
}

/** Trim, then strip trailing punctuation the rule extractor cannot match (ported). */
export function normaliseTranscript(s: string): string {
  return s.trim().replace(/[.!?,…。\s]+$/u, "");
}

/** RMS of the analyser's current time-domain frame, scaled to 0..1 (ported). */
export function rmsLevel(analyser: Pick<AnalyserNode, "fftSize" | "getByteTimeDomainData">): number {
  const buf = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (const v of buf) {
    const x = (v - 128) / 128;
    sum += x * x;
  }
  return Math.min(1, Math.sqrt(sum / (buf.length || 1)) * 4);
}

export interface LevelMeter {
  level(): number;
  close(): void;
}

/** Web Audio meter over the mic stream. Returns null when Web Audio is unavailable. */
export function createLevelMeter(stream: MediaStream): LevelMeter | null {
  const Ctx: typeof AudioContext | undefined =
    typeof window === "undefined"
      ? undefined
      : (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext);
  if (!Ctx) return null;
  try {
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    return {
      level: () => rmsLevel(analyser),
      close: () => void ctx.close().catch(() => undefined),
    };
  } catch {
    return null;
  }
}

export interface ConnectOptions {
  clientSecret: string;
  connectUrl: string;
  dataChannel: string;
  micStream: MediaStream;
  onEvent: (evt: RealtimeEvent) => void;
  onOpen: () => void;
  /** Unexpected data-channel close or peer-connection state change. */
  onClose: () => void;
  onConnectionState: (state: RTCPeerConnectionState) => void;
}

export interface RealtimeConnection {
  send(evt: { type: string }): void;
  setMic(on: boolean): void;
  isOpen(): boolean;
  close(): void;
}

/** T2 sender: refuses (throws) any event type outside the frozen allowlist and sends nothing. */
export function makeSender(dc: Pick<RTCDataChannel, "readyState" | "send">) {
  return (evt: { type: string }) => {
    const type = evt?.type;
    if (typeof type !== "string" || !ALLOWED_CLIENT_EVENTS.includes(type)) {
      throw new Error(`client event not allowed: ${String(type)}`);
    }
    if (dc.readyState === "open") dc.send(JSON.stringify({ type }));
  };
}

/** T1: WebRTC handshake. The SDP POST carries only the SDP body and the two required headers. */
export async function connectRealtime(opts: ConnectOptions): Promise<RealtimeConnection> {
  if (!/^https:\/\//.test(opts.connectUrl)) throw new RealtimeConnectError("url");
  const pc = new RTCPeerConnection();
  const tracks = opts.micStream.getAudioTracks();
  for (const track of tracks) pc.addTrack(track, opts.micStream);
  pc.ontrack = () => {
    /* transcription only: no remote audio is attached anywhere */
  };
  let closed = false;
  pc.onconnectionstatechange = () => {
    if (!closed) opts.onConnectionState(pc.connectionState);
  };

  const dc = pc.createDataChannel(opts.dataChannel || "oai-events");
  dc.onopen = () => {
    if (!closed) opts.onOpen();
  };
  dc.onclose = () => {
    if (!closed) opts.onClose();
  };
  dc.onmessage = (m: MessageEvent) => {
    if (closed) return;
    try {
      const evt = JSON.parse(String(m.data)) as RealtimeEvent;
      if (evt && typeof evt.type === "string") opts.onEvent(evt);
    } catch {
      /* malformed frame: ignore */
    }
  };

  const shutdown = () => {
    closed = true;
    dc.onmessage = null;
    dc.onopen = null;
    dc.onclose = null;
    pc.onconnectionstatechange = null;
    pc.ontrack = null;
    try {
      dc.close();
    } catch {
      /* already closed */
    }
    pc.close();
  };

  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const resp = await fetch(opts.connectUrl, {
      method: "POST",
      body: offer.sdp,
      headers: { Authorization: `Bearer ${opts.clientSecret}`, "Content-Type": "application/sdp" },
    });
    if (!resp.ok) throw new RealtimeConnectError("sdp", resp.status);
    await pc.setRemoteDescription({ type: "answer", sdp: await resp.text() });
  } catch (err) {
    shutdown();
    throw err instanceof RealtimeConnectError ? err : new RealtimeConnectError("network");
  }

  const send = makeSender(dc);
  return {
    send,
    setMic(on) {
      for (const track of tracks) track.enabled = on;
    },
    isOpen: () => !closed && dc.readyState === "open",
    close: shutdown,
  };
}
