/** V2C-C18 lifecycle: wake lock, visibility, online/offline, rollover, single peer connection. */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installApi, installBrowser, makeRecorder } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
});

function setVisibility(v: "hidden" | "visible") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => v });
  document.dispatchEvent(new Event("visibilitychange"));
}

async function listening() {
  const b = installBrowser();
  const api = installApi();
  const r = await makeRecorder();
  r.rec.press();
  await vi.advanceTimersByTimeAsync(0);
  expect(r.rec.getSnapshot().rec).toBe("listening");
  return { b, api, ...r };
}

const mints = (api: { calls: { url: string }[] }) => api.calls.filter((c) => c.url === "/api/voice/realtime/session").length;

describe("wake lock", () => {
  it("is requested on entering listening and released on pause", async () => {
    const { b, rec } = await listening();
    expect(b.wake.requested).toBe(1);
    expect(b.wake.held).toBe(1);
    rec.pause();
    await vi.advanceTimersByTimeAsync(0);
    expect(b.wake.held).toBe(0);
  });

  it("is released on reconnecting, error, finishing and unmount", async () => {
    const { b, api, rec } = await listening();
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().rec).toBe("reconnecting");
    expect(b.wake.held).toBe(0);
    await vi.advanceTimersByTimeAsync(1000);
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.wake.held).toBe(1);

    api.mint.push({ status: 409, body: { detail: "voice session is not active" } });
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(rec.getSnapshot().rec).toBe("error");
    expect(b.wake.held).toBe(0);

    rec.press(); // retry
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.wake.held).toBe(1);
    const done = rec.finish();
    await vi.advanceTimersByTimeAsync(0);
    expect(b.wake.held).toBe(0);
    await done;

    const second = await listening();
    second.rec.dispose();
    await vi.advanceTimersByTimeAsync(0);
    expect(second.b.wake.held).toBe(0);
  });

  it("unsupported wake lock is not an error", async () => {
    const b = installBrowser();
    Object.defineProperty(navigator, "wakeLock", { configurable: true, value: undefined });
    installApi();
    const { rec } = await makeRecorder();
    rec.press();
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.wake.requested).toBe(0);
  });
});

describe("visibility", () => {
  it("hidden while listening forces a system pause; visible does not auto-resume", async () => {
    const { b, rec } = await listening();
    setVisibility("hidden");
    expect(rec.getSnapshot().rec).toBe("paused");
    expect(rec.getSnapshot().systemPause).toBe(true);
    expect(b.track.enabled).toBe(false);
    setVisibility("visible");
    await vi.advanceTimersByTimeAsync(5000);
    expect(rec.getSnapshot().rec).toBe("paused");
  });

  it("a connection that dies while paused shows nothing; resume goes through connecting with one fresh mint", async () => {
    const { b, api, rec } = await listening();
    rec.pause();
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(rec.getSnapshot().rec).toBe("paused");
    expect(mints(api)).toBe(1);
    b.rtc.autoOpen = false;
    void rec.resume();
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().rec).toBe("connecting");
    expect(mints(api)).toBe(2);
    b.rtc.last().openNow();
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.rtc.open).toBe(1);
  });

  it("resume on a live connection re-enables the mic without a new mint", async () => {
    const { b, api, rec } = await listening();
    rec.pause();
    expect(b.track.enabled).toBe(false);
    await rec.resume();
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.track.enabled).toBe(true);
    expect(mints(api)).toBe(1);
  });
});

describe("network", () => {
  it("offline while listening → reconnecting; online → an attempt within 100 ms", async () => {
    const { api, rec } = await listening();
    api.mint.push({ status: 502, body: {} });
    window.dispatchEvent(new Event("offline"));
    expect(rec.getSnapshot().rec).toBe("reconnecting");
    await vi.advanceTimersByTimeAsync(1000); // attempt 1 fails, attempt 2 waits 2 s
    expect(mints(api)).toBe(2);
    window.dispatchEvent(new Event("online"));
    await vi.advanceTimersByTimeAsync(100);
    expect(mints(api)).toBe(3);
    expect(rec.getSnapshot().rec).toBe("listening");
  });

  it("peer connection 'disconnected' waits 2 s before reconnecting; recovery inside the grace keeps listening", async () => {
    const { b, rec } = await listening();
    const pc = b.rtc.last();
    pc.connectionState = "disconnected";
    pc.onconnectionstatechange?.();
    await vi.advanceTimersByTimeAsync(1500);
    pc.connectionState = "connected";
    pc.onconnectionstatechange?.();
    await vi.advanceTimersByTimeAsync(5000);
    expect(rec.getSnapshot().rec).toBe("listening");
    pc.connectionState = "disconnected";
    pc.onconnectionstatechange?.();
    await vi.advanceTimersByTimeAsync(2000);
    expect(rec.getSnapshot().rec).toBe("reconnecting");
  });

  it("429 waits Retry-After instead of the backoff", async () => {
    const { b, api, rec } = await listening();
    api.mint.push({ status: 429, body: {}, headers: { "Retry-After": "7" } });
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(mints(api)).toBe(2);
    await vi.advanceTimersByTimeAsync(6900);
    expect(mints(api)).toBe(2);
    await vi.advanceTimersByTimeAsync(100);
    expect(mints(api)).toBe(3);
    expect(rec.getSnapshot().rec).toBe("listening");
  });
});

describe("planned rollover", () => {
  it("rolls over at max_session_seconds − 30 s when quiet: 0 duplicate, 0 lost, one open pc", async () => {
    const { b, api, rec } = await listening();
    b.rtc.say("i1", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(569_000);
    expect(b.rtc.pcs).toHaveLength(1);
    b.rtc.say("i2", "สอง");
    await vi.advanceTimersByTimeAsync(1_500);
    expect(b.rtc.pcs).toHaveLength(2);
    expect(rec.getSnapshot().rec).toBe("listening");
    b.rtc.say("i3", "สาม");
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i2", transcript: "สอง" }, b.rtc.pcs[0]);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.posted.map((p) => p.text)).toEqual(["หนึ่ง", "สอง", "สาม"]);
    expect(b.rtc.maxOpen).toBe(1);
  });

  it("waits for speech to stop, but forces the rollover at max − 5 s", async () => {
    const { b } = await listening();
    b.rtc.emit({ type: "input_audio_buffer.speech_started", item_id: "long" });
    await vi.advanceTimersByTimeAsync(580_000);
    expect(b.rtc.pcs).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(16_000);
    expect(b.rtc.pcs.length).toBeGreaterThanOrEqual(2);
    expect(b.rtc.open).toBe(1);
  });

  it("drains a committed-not-completed item for up to 3 s before closing, so it is not lost", async () => {
    const { b, api } = await listening();
    await vi.advanceTimersByTimeAsync(569_000);
    const pc0 = b.rtc.pcs[0];
    b.rtc.emit({ type: "input_audio_buffer.speech_started", item_id: "i1" }, pc0);
    b.rtc.emit({ type: "input_audio_buffer.speech_stopped", item_id: "i1" }, pc0);
    b.rtc.emit({ type: "input_audio_buffer.committed", item_id: "i1" }, pc0);
    await vi.advanceTimersByTimeAsync(2_000); // rollover started at 570 s and is draining
    expect(pc0.closed).toBe(false);
    b.rtc.emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i1", transcript: "หนึ่ง" }, pc0);
    await vi.advanceTimersByTimeAsync(200);
    expect(pc0.closed).toBe(true);
    expect(api.posted.map((p) => p.text)).toEqual(["หนึ่ง"]);
    expect(b.rtc.open).toBe(1);
  });
});

describe("single peer connection", () => {
  it("never holds two open connections across drops, retries and resume", async () => {
    const { b, api, rec } = await listening();
    for (let i = 0; i < 3; i++) {
      b.rtc.drop();
      await vi.advanceTimersByTimeAsync(1000);
    }
    api.mint.push({ status: 502, body: {} }, { status: 502, body: {} }, { status: 502, body: {} });
    b.rtc.drop();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(rec.getSnapshot().rec).toBe("error");
    rec.press();
    await vi.advanceTimersByTimeAsync(0);
    expect(rec.getSnapshot().rec).toBe("listening");
    expect(b.rtc.maxOpen).toBe(1);
    expect(b.rtc.open).toBe(1);
  });
});
