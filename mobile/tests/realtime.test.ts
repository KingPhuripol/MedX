/** T1–T3 transport: handshake order and headers, https-only URL, send allowlist (C8), no media element. */
import { describe, expect, it } from "vitest";

import { ALLOWED_CLIENT_EVENTS, connectRealtime, makeSender, normaliseTranscript, RealtimeConnectError } from "@/lib/realtime";

import { installApi, installBrowser } from "./helpers";

const FORBIDDEN = ["response.create", "response.cancel", "conversation.item.create", "session.update", "transcription_session.update"];

function opts(b: ReturnType<typeof installBrowser>, patch: Partial<Parameters<typeof connectRealtime>[0]> = {}) {
  const events: unknown[] = [];
  const o = {
    clientSecret: "ek_fixtureSecret0000",
    connectUrl: "https://127.0.0.1/v1/realtime/calls",
    dataChannel: "oai-events",
    micStream: { getAudioTracks: () => [b.track], getTracks: () => [b.track] } as unknown as MediaStream,
    onEvent: (e: unknown) => events.push(e),
    onOpen: () => events.push("open"),
    onClose: () => events.push("close"),
    onConnectionState: () => undefined,
    ...patch,
  };
  return { o, events };
}

describe("connectRealtime", () => {
  it("adds the mic track, opens the named data channel, POSTs only SDP with two headers, then applies the answer", async () => {
    const b = installBrowser();
    const api = installApi();
    const { o, events } = opts(b);
    const conn = await connectRealtime(o);
    await Promise.resolve();
    const pc = b.rtc.last();
    expect(pc.tracks).toEqual([b.track]);
    expect(pc.dc?.label).toBe("oai-events");
    const sdp = api.calls.find((c) => c.url.startsWith("https://"))!;
    expect(sdp.method).toBe("POST");
    expect(sdp.init.body).toBe("v=0 fake-offer");
    expect(sdp.init.headers).toEqual({ Authorization: "Bearer ek_fixtureSecret0000", "Content-Type": "application/sdp" });
    expect(sdp.init.credentials).toBeUndefined();
    expect(JSON.stringify(sdp.init)).not.toContain("SYN-");
    expect(events).toContain("open");
    expect(conn.isOpen()).toBe(true);
  });

  it("rejects a non-https connect_url before creating any peer connection", async () => {
    const b = installBrowser();
    const api = installApi();
    for (const url of ["http://127.0.0.1/x", "wss://x", "javascript:alert(1)", ""]) {
      await expect(connectRealtime(opts(b, { connectUrl: url }).o)).rejects.toMatchObject({ kind: "url" });
    }
    expect(b.rtc.pcs).toHaveLength(0);
    expect(api.calls).toHaveLength(0);
  });

  it("closes the peer connection when the SDP POST fails", async () => {
    const b = installBrowser();
    installApi({ on: { "/v1/realtime/calls": () => ({ status: 401, body: {} }) } });
    const err = await connectRealtime(opts(b).o).catch((e) => e);
    expect(err).toBeInstanceOf(RealtimeConnectError);
    expect(err.status).toBe(401);
    expect(b.rtc.last().closed).toBe(true);
    expect(b.rtc.open).toBe(0);
  });

  it("attaches no media element on ontrack and forwards vendor events untouched (response.* included)", async () => {
    const b = installBrowser();
    installApi();
    const { o, events } = opts(b);
    await connectRealtime(o);
    b.rtc.last().ontrack?.({ streams: [{}] });
    expect(document.querySelectorAll("audio, video")).toHaveLength(0);
    b.rtc.emit({ type: "response.audio_transcript.delta", delta: "สวัสดี" });
    b.rtc.last().dc?.onmessage?.({ data: "not json" });
    expect(events.filter((e) => typeof e === "object")).toHaveLength(1);
  });

  it("setMic toggles track.enabled; close stops callbacks and closes the pc", async () => {
    const b = installBrowser();
    installApi();
    const { o, events } = opts(b);
    const conn = await connectRealtime(o);
    conn.setMic(false);
    expect(b.track.enabled).toBe(false);
    conn.setMic(true);
    expect(b.track.enabled).toBe(true);
    conn.close();
    const before = events.length;
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "x", transcript: "late" });
    expect(events.length).toBe(before);
    expect(b.rtc.open).toBe(0);
  });
});

describe("T2 send allowlist (C8)", () => {
  it("is frozen to input_audio_buffer.clear", () => {
    expect(ALLOWED_CLIENT_EVENTS).toEqual(["input_audio_buffer.clear"]);
    expect(Object.isFrozen(ALLOWED_CLIENT_EVENTS)).toBe(true);
  });

  it.each(FORBIDDEN)("throws on %s and sends nothing", (type) => {
    const sent: string[] = [];
    const send = makeSender({ readyState: "open", send: (d: string) => sent.push(d) } as unknown as RTCDataChannel);
    expect(() => send({ type })).toThrow(/not allowed/);
    expect(sent).toEqual([]);
  });

  it("sends only the allowed type (extra fields dropped)", () => {
    const sent: string[] = [];
    const send = makeSender({ readyState: "open", send: (d: string) => sent.push(d) } as unknown as RTCDataChannel);
    send({ type: "input_audio_buffer.clear", instructions: "speak" } as { type: string });
    expect(sent).toEqual([JSON.stringify({ type: "input_audio_buffer.clear" })]);
  });

  it("the connection sender refuses response.create over a live channel", async () => {
    const b = installBrowser();
    installApi();
    const conn = await connectRealtime(opts(b).o);
    await Promise.resolve();
    expect(() => conn.send({ type: "response.create" })).toThrow();
    expect(b.rtc.sent).toEqual([]);
  });
});

describe("normaliseTranscript", () => {
  it("trims and strips trailing punctuation", () => {
    expect(normaliseTranscript("  ปวดท้องค่ะ.  ")).toBe("ปวดท้องค่ะ");
    expect(normaliseTranscript("เจ็บ…")).toBe("เจ็บ");
    expect(normaliseTranscript(" . ")).toBe("");
  });
});
