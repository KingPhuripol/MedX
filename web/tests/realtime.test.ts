import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { connectRealtime, normaliseTranscript, rmsLevel, speakEvent } from "@/lib/realtime";

class FakeDC {
  readyState = "open";
  onmessage: ((m: { data: string }) => void) | null = null;
  sent: string[] = [];
  constructor(readonly label: string) {}
  send(d: string) {
    this.sent.push(d);
  }
  close() {
    this.readyState = "closed";
  }
}
let pc: FakePC;
class FakePC {
  connectionState = "new";
  ontrack: unknown = null;
  onconnectionstatechange: unknown = null;
  added: unknown[] = [];
  channel!: FakeDC;
  remote: { type: string; sdp: string } | null = null;
  closed = false;
  constructor() {
    pc = this;
  }
  addTrack(t: unknown) {
    this.added.push(t);
  }
  createDataChannel(label: string) {
    this.channel = new FakeDC(label);
    return this.channel;
  }
  async createOffer() {
    return { type: "offer", sdp: "offer-sdp" };
  }
  async setLocalDescription() {}
  async setRemoteDescription(d: { type: string; sdp: string }) {
    this.remote = d;
  }
  close() {
    this.closed = true;
  }
}

function mic() {
  const track = { enabled: true } as MediaStreamTrack;
  return { stream: { getAudioTracks: () => [track] } as unknown as MediaStream, track };
}

beforeEach(() => {
  vi.stubGlobal("RTCPeerConnection", FakePC);
});
afterEach(() => vi.unstubAllGlobals());

describe("connectRealtime", () => {
  it("F1: POSTs the offer with the bearer secret, opens oai-events and sets the remote answer", async () => {
    const fetchMock = vi.fn(async () => new Response("answer-sdp", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const { stream } = mic();
    const events: unknown[] = [];
    await connectRealtime({ clientSecret: "ek_TEST", connectUrl: "https://rt.example.test/calls", micStream: stream, onEvent: (e) => events.push(e) });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://rt.example.test/calls");
    expect(init.method).toBe("POST");
    expect(init.body).toBe("offer-sdp");
    expect(init.headers).toEqual({ Authorization: "Bearer ek_TEST", "Content-Type": "application/sdp" });
    expect(pc.channel.label).toBe("oai-events");
    expect(pc.remote).toEqual({ type: "answer", sdp: "answer-sdp" });
    pc.channel.onmessage?.({ data: JSON.stringify({ type: "session.created" }) });
    pc.channel.onmessage?.({ data: "not json" });
    expect(events).toEqual([{ type: "session.created" }]);
  });

  it("closes the peer connection and reports a structured error when the SDP exchange fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 500 })));
    await expect(
      connectRealtime({ clientSecret: "ek_TEST", connectUrl: "https://rt.example.test/calls", micStream: mic().stream, onEvent: () => {} }),
    ).rejects.toMatchObject({ kind: "sdp", status: 500 });
    expect(pc.closed).toBe(true);
  });

  it("F3: only speakEvent responses and buffer clears can be sent; session.update never", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("a", { status: 201 })));
    const { stream, track } = mic();
    const conn = await connectRealtime({ clientSecret: "ek_TEST", connectUrl: "https://rt.example.test/c", micStream: stream, onEvent: () => {} });
    conn.send(speakEvent("สวัสดีค่ะ", "u1"));
    conn.send({ type: "input_audio_buffer.clear" });
    expect(() => conn.send({ type: "session.update" } as never)).toThrow();
    expect(() => conn.send({ type: "response.create", response: { instructions: "x" } } as never)).toThrow();
    const types = pc.channel.sent.map((s) => JSON.parse(s).type);
    expect(types).toEqual(["response.create", "input_audio_buffer.clear"]);
    conn.setMic(false);
    expect(track.enabled).toBe(false);
    conn.setMic(true);
    expect(track.enabled).toBe(true);
    conn.close();
    expect(pc.closed).toBe(true);
  });
});

describe("speakEvent", () => {
  it("F2: has the exact out-of-band shape with no instructions field", () => {
    expect(speakEvent("ข้อความ", "ask.x")).toEqual({
      type: "response.create",
      response: {
        conversation: "none",
        output_modalities: ["audio"],
        input: [{ type: "message", role: "user", content: [{ type: "input_text", text: "ข้อความ" }] }],
        metadata: { utterance_id: "ask.x" },
      },
    });
    expect(JSON.stringify(speakEvent("a", "b"))).not.toContain("instructions");
  });
});

describe("normaliseTranscript", () => {
  it("F13: strips trailing punctuation and whitespace", () => {
    expect(normaliseTranscript("ไม่เคยแพ้ยาค่ะ.")).toBe("ไม่เคยแพ้ยาค่ะ");
    expect(normaliseTranscript("  เจ็บหน้าอก… ")).toBe("เจ็บหน้าอก");
    expect(normaliseTranscript("ใช่!?")).toBe("ใช่");
    expect(normaliseTranscript("   ")).toBe("");
    expect(normaliseTranscript(".")).toBe("");
  });
});

describe("rmsLevel", () => {
  it("is 0 for silence and clamps to 1 for a loud signal", () => {
    const frame = (v: number) => ({ fftSize: 8, getByteTimeDomainData: (b: Uint8Array) => b.fill(v) });
    expect(rmsLevel(frame(128))).toBe(0);
    expect(rmsLevel(frame(255))).toBe(1);
  });
});
