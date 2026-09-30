/** V2C-C7: completed items only, exactly once, in order, across reconnect (Recorder + fake WebRTC). */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installApi, installBrowser, makeRecorder } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
});

async function listening() {
  const b = installBrowser();
  const api = installApi();
  const r = await makeRecorder();
  r.rec.press();
  await vi.advanceTimersByTimeAsync(0);
  expect(r.rec.getSnapshot().rec).toBe("listening");
  return { b, api, ...r };
}

const postedTexts = (api: { posted: Record<string, unknown>[] }) => api.posted.map((p) => p.text);
const mints = (api: { calls: { url: string }[] }) => api.calls.filter((c) => c.url === "/api/voice/realtime/session").length;

describe("transport (C7)", () => {
  it("deltas post nothing; each completed posts once; the partial line is shown then replaced", async () => {
    const { b, api, rec } = await listening();
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.delta", item_id: "i1", delta: "ปวด" });
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.delta", item_id: "i1", delta: "ท้อง" });
    await vi.advanceTimersByTimeAsync(0);
    expect(api.posted).toHaveLength(0);
    expect(rec.getSnapshot().interim?.text).toBe("ปวดท้อง");
    b.rtc.emit({ type: "input_audio_buffer.committed", item_id: "i1" });
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i1", transcript: "ปวดท้องค่ะ" });
    await vi.advanceTimersByTimeAsync(0);
    expect(postedTexts(api)).toEqual(["ปวดท้องค่ะ"]);
    expect(rec.getSnapshot().interim).toBeNull();
    expect(rec.getSnapshot().lines.map((l) => l.text)).toEqual(["ปวดท้องค่ะ"]);
    expect(api.posted[0].asr_model).toBe("fixture-transcribe");
  });

  it("reconnect script: 3 items, drop with 1 pending, reconnect, 2 more + a late duplicate → exact order, no repeats, no loss", async () => {
    const { b, api, rec } = await listening();
    const old = b.rtc.last();
    b.rtc.say("i1", "หนึ่ง");
    b.rtc.say("i2", "สอง");
    b.rtc.say("i3", "สาม");
    b.rtc.emit({ type: "input_audio_buffer.speech_started", item_id: "i4" });
    b.rtc.emit({ type: "input_audio_buffer.committed", item_id: "i4" });
    await vi.advanceTimersByTimeAsync(0);
    b.rtc.drop(old);
    expect(rec.getSnapshot().rec).toBe("reconnecting");
    expect(rec.getSnapshot().attempt).toBe(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.rtc.pcs).toHaveLength(2);
    const fresh = b.rtc.last();
    // late events from the closed connection, including a duplicate and the pending item
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i3", transcript: "สาม" }, old);
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i4", transcript: "สี่" }, old);
    b.rtc.say("i5", "ห้า", fresh);
    b.rtc.say("i6", "หก", fresh);
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i5", transcript: "ห้า" }, fresh);
    await vi.advanceTimersByTimeAsync(0);
    expect(postedTexts(api)).toEqual(["หนึ่ง", "สอง", "สาม", "ห้า", "หก"]);
    expect(rec.getSnapshot().failedSegments).toBe(1); // i4 lost with the old connection: counted, not fabricated
    expect(b.rtc.maxOpen).toBe(1);
  });

  it("a POST in flight during reconnect completes once and is never re-posted", async () => {
    const { b, api, rec } = await listening();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    let n = 0;
    api.on["/api/voice/sessions/" + rec.sessionId + "/turns"] = async (req) => {
      api.posted.push(req.body as Record<string, unknown>);
      if (++n === 1) await gate;
      return { status: 200, body: (await import("./fixtures/scenario")).turnResponse({ turnId: `vt_${n}`, text: "x", known: {} }) };
    };
    b.rtc.say("i1", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(0);
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(rec.getSnapshot().rec).toBe("listening");
    b.rtc.say("i2", "สอง");
    await vi.advanceTimersByTimeAsync(0);
    expect(postedTexts(api)).toEqual(["หนึ่ง"]);
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(postedTexts(api)).toEqual(["หนึ่ง", "สอง"]);
    expect(rec.getSnapshot().turnCount).toBe(2);
  });

  it("a failed transcription removes the partial line, posts nothing and is counted", async () => {
    const { b, api, rec } = await listening();
    b.rtc.emit({ type: "input_audio_buffer.committed", item_id: "i1" });
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.delta", item_id: "i1", delta: "ปว" });
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.failed", item_id: "i1" });
    b.rtc.say("i2", "สอง");
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().interim).toBeNull();
    expect(postedTexts(api)).toEqual(["สอง"]);
    expect(rec.getSnapshot().failedSegments).toBe(1);
  });

  it("vendor response.* / output events are ignored and never rendered; only allowed frames are ever sent", async () => {
    const { b, api, rec } = await listening();
    const before = rec.getSnapshot();
    b.rtc.emit({ type: "response.created" });
    b.rtc.emit({ type: "response.audio_transcript.delta", delta: "สวัสดีค่ะ" });
    b.rtc.emit({ type: "response.text.delta", delta: "ข้อความ" });
    b.rtc.emit({ type: "response.done" });
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().lines).toEqual(before.lines);
    expect(rec.getSnapshot().interim).toBeNull();
    expect(api.posted).toHaveLength(0);
    for (const f of b.rtc.sent) expect(JSON.parse(f).type).toBe("input_audio_buffer.clear");
  });

  it("the ambiguous failure (network error, turn already stored) posts 0 extra through the recorder", async () => {
    const { b, api, rec } = await listening();
    api.turnStatus.push("network");
    const { reviewSession, turn } = await import("./fixtures/scenario");
    api.on[`GET /api/voice/sessions/${rec.sessionId}`] = () => {
      const p = api.posted[0] as { text: string; started_at: string };
      return { status: 200, body: { ...reviewSession(), turns: [turn("vt_9", p.text, p.started_at)] } };
    };
    b.rtc.say("i1", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(api.posted).toHaveLength(1);
    expect(rec.getSnapshot().failedSegments).toBe(0);
    expect(mints(api)).toBe(1);
  });
});
