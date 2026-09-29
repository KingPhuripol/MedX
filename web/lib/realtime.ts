/**
 * Client realtime layer for MedX Live (slice v1, SPEC section 2.10 and 4).
 *
 * The realtime service is used for speech in and speech out only. The client:
 *  - speaks only text that the server policy chose (`speakEvent` is the sole builder of `response.create`);
 *  - never sends `session.update` or any other event type;
 *  - never stores, renders or posts the model's own output transcript.
 * The vendor name and URL come only from the server (`connect_url`, `vendor_label`).
 */

export interface RealtimeConfig {
  enabled: boolean;
  reason: null | "voice_disabled" | "not_configured" | "access_code_not_configured";
  access_code_required: boolean;
  max_session_seconds: number;
  vendor_label: string;
  model: string;
  transcribe_model: string;
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

export type ClientEvent =
  | ReturnType<typeof speakEvent>
  | { type: "input_audio_buffer.clear" };

export const ALLOWED_CLIENT_EVENTS = ["response.create", "input_audio_buffer.clear"] as const;

export class RealtimeConnectError extends Error {
  constructor(
    readonly kind: "sdp" | "network",
    readonly status?: number,
  ) {
    super(`realtime connect failed (${kind}${status ? ` ${status}` : ""})`);
  }
}

/** Events built by `speakEvent`; `send` refuses any `response.create` that did not come from it. */
const SPOKEN = new WeakSet<object>();

/** The only `response.create` shape: out-of-band, one user message holding the server-chosen text. */
export function speakEvent(utteranceTh: string, utteranceId: string) {
  const evt = {
    type: "response.create" as const,
    response: {
      conversation: "none" as const,
      output_modalities: ["audio" as const],
      input: [
        {
          type: "message" as const,
          role: "user" as const,
          content: [{ type: "input_text" as const, text: utteranceTh }],
        },
      ],
      metadata: { utterance_id: utteranceId },
    },
  };
  SPOKEN.add(evt);
  return evt;
}

/** Trim, then strip trailing punctuation the rule extractor cannot match (SPEC finding 3). */
export function normaliseTranscript(s: string): string {
  return s.trim().replace(/[.!?,…。\s]+$/u, "");
}

/** RMS of the analyser's current time-domain frame, scaled to 0..1 (speech sits far below full scale). */
export function rmsLevel(analyser: Pick<AnalyserNode, "fftSize" | "getByteTimeDomainData">): number {
  const buf = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (const v of buf) {
    const x = (v - 128) / 128;
    sum += x * x;
  }
  const rms = Math.sqrt(sum / (buf.length || 1));
  return Math.min(1, rms * 4);
}

export interface LevelMeter {
  /** Smoothing is done by the caller; this is the raw 0..1 level of the current frame. */
  level(): number;
  close(): void;
}

/** Web Audio meter over a media stream. Returns null when Web Audio is unavailable. */
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
      close: () => {
        void ctx.close().catch(() => undefined);
      },
    };
  } catch {
    return null;
  }
}

export interface ConnectOptions {
  clientSecret: string;
  connectUrl: string;
  micStream: MediaStream;
  onEvent: (evt: RealtimeEvent) => void;
  onRemoteStream?: (stream: MediaStream) => void;
  onConnectionState?: (state: RTCPeerConnectionState) => void;
}

export interface RealtimeConnection {
  send(evt: ClientEvent): void;
  /** Enable or disable the outgoing mic track (half-duplex and mute). */
  setMic(on: boolean): void;
  close(): void;
}

/** Browser WebRTC handshake: SDP offer POSTed to `connect_url` with the short-lived client secret. */
export async function connectRealtime(opts: ConnectOptions): Promise<RealtimeConnection> {
  const pc = new RTCPeerConnection();
  const tracks = opts.micStream.getAudioTracks();
  for (const track of tracks) pc.addTrack(track, opts.micStream);
  pc.ontrack = (e) => {
    const stream = e.streams?.[0];
    if (stream) opts.onRemoteStream?.(stream);
  };
  pc.onconnectionstatechange = () => opts.onConnectionState?.(pc.connectionState);

  const dc = pc.createDataChannel("oai-events");
  dc.onmessage = (m: MessageEvent) => {
    try {
      const evt = JSON.parse(String(m.data)) as RealtimeEvent;
      if (evt && typeof evt.type === "string") opts.onEvent(evt);
    } catch {
      /* malformed frame: ignore */
    }
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
    pc.close();
    throw err instanceof RealtimeConnectError ? err : new RealtimeConnectError("network");
  }

  return {
    send(evt) {
      const type = (evt as { type: string }).type;
      if (!(ALLOWED_CLIENT_EVENTS as readonly string[]).includes(type)) throw new Error(`client event not allowed: ${type}`);
      if (type === "response.create" && !SPOKEN.has(evt)) throw new Error("response.create must be built by speakEvent");
      if (dc.readyState === "open") dc.send(JSON.stringify(evt));
    },
    setMic(on) {
      for (const track of tracks) track.enabled = on;
    },
    close() {
      dc.onmessage = null;
      pc.onconnectionstatechange = null;
      try {
        dc.close();
      } catch {
        /* already closed */
      }
      pc.close();
    },
  };
}
