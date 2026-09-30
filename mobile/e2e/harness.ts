/**
 * Browser harness: fakes getUserMedia, RTCPeerConnection + data channel and wakeLock (init script),
 * mocks every /api call with contract fixtures, and fails on any request to a non-local host.
 */
import { expect, type Page, type Route } from "@playwright/test";

import me from "../tests/fixtures/auth-login.json";
import config from "../tests/fixtures/realtime-config.json";
import mint from "../tests/fixtures/realtime-session.json";
import { reviewSession, startResponse } from "../tests/fixtures/scenario";

export const FAKE_BROWSER = () => {
  const w = window as unknown as Record<string, unknown>;
  const rtc = { pcs: [] as unknown[], sent: [] as string[], open: 0, maxOpen: 0 };
  w.__rtc = rtc;
  class FakeDC {
    readyState = "connecting";
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((m: { data: string }) => void) | null = null;
    constructor(readonly label: string) {}
    send(d: string) {
      rtc.sent.push(d);
    }
    close() {
      this.readyState = "closed";
    }
  }
  class FakePC {
    connectionState = "new";
    closed = false;
    dc: FakeDC | null = null;
    ontrack: unknown = null;
    onconnectionstatechange: (() => void) | null = null;
    constructor() {
      rtc.pcs.push(this);
      rtc.open += 1;
      rtc.maxOpen = Math.max(rtc.maxOpen, rtc.open);
    }
    addTrack() {}
    createDataChannel(label: string) {
      this.dc = new FakeDC(label);
      return this.dc;
    }
    async createOffer() {
      return { type: "offer", sdp: "v=0 fake-offer" };
    }
    async setLocalDescription() {}
    async setRemoteDescription() {
      queueMicrotask(() => {
        if (this.closed || !this.dc) return;
        this.dc.readyState = "open";
        this.connectionState = "connected";
        this.dc.onopen?.();
      });
    }
    close() {
      if (!this.closed) rtc.open -= 1;
      this.closed = true;
      this.connectionState = "closed";
    }
  }
  w.RTCPeerConnection = FakePC;
  const track = { kind: "audio", enabled: true, readyState: "live", stop() { this.readyState = "ended"; } };
  const stream = { getAudioTracks: () => [track], getTracks: () => [track] };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: async () => stream } });
  Object.defineProperty(navigator, "wakeLock", { configurable: true, value: { request: async () => ({ release: async () => undefined }) } });
  w.__emit = (evt: unknown) => {
    const pc = rtc.pcs[rtc.pcs.length - 1] as FakePC;
    pc.dc?.onmessage?.({ data: JSON.stringify(evt) });
  };
  w.__drop = () => {
    const pc = rtc.pcs[rtc.pcs.length - 1] as FakePC;
    pc.connectionState = "failed";
    pc.onconnectionstatechange?.();
  };
};

export interface ApiState {
  meStatus: number;
  mintStatus: number;
  turns: unknown[];
  posted: Record<string, unknown>[];
  sessionGet: unknown;
  finishStatus: number;
  reviewStatus: number;
  config: typeof config;
  foreign: string[];
  start: ReturnType<typeof startResponse>;
}

const json = (route: Route, status: number, body: unknown) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export async function setup(page: Page, patch: Partial<ApiState> = {}): Promise<ApiState> {
  const api: ApiState = {
    meStatus: 200,
    mintStatus: 200,
    turns: [],
    posted: [],
    sessionGet: reviewSession(),
    finishStatus: 200,
    reviewStatus: 404,
    config,
    foreign: [],
    start: startResponse(),
    ...patch,
  };
  page.on("request", (req) => {
    const u = new URL(req.url());
    if (u.hostname !== "127.0.0.1" && u.hostname !== "localhost") api.foreign.push(req.url());
  });
  await page.context().route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (r) => r.abort());
  await page.addInitScript(FAKE_BROWSER);
  await page.route("https://127.0.0.1/**", (route) => {
    const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization, content-type" };
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    return route.fulfill({ status: 201, headers: { ...cors, "content-type": "application/sdp" }, body: "v=0 fake-answer" });
  });
  await page.route("**/api/**", (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const m = req.method();
    if (path === "/api/me") return api.meStatus === 200 ? json(route, 200, me) : json(route, api.meStatus, { detail: "no" });
    if (path === "/api/auth/login" || path === "/api/auth/demo-login") return json(route, 200, me);
    if (path === "/api/auth/logout") return route.fulfill({ status: 204 });
    if (path === "/api/voice/realtime/config") return json(route, 200, api.config);
    if (path === "/api/voice/realtime/session") {
      return api.mintStatus === 200 ? json(route, 200, mint) : json(route, api.mintStatus, { detail: { reason: "upstream_error" } });
    }
    if (path === "/api/voice/sessions" && m === "POST") return json(route, 200, api.start);
    if (path.endsWith("/turns") && m === "POST") {
      api.posted.push(req.postDataJSON());
      const next = api.turns.shift();
      return next ? json(route, 200, next) : json(route, 500, { detail: "no fixture" });
    }
    if (path.endsWith("/finish")) return json(route, api.finishStatus, { session: {} });
    if (path.endsWith("/review")) return json(route, api.reviewStatus, { detail: "Not Found" });
    if (path.startsWith("/api/voice/sessions/") && m === "GET") return json(route, 200, api.sessionGet);
    return json(route, 404, { detail: "unmocked" });
  });
  return api;
}

/** Emit one transcribed item: started → stopped → committed → completed. */
export async function say(page: Page, id: string, text: string) {
  await page.evaluate(
    ([id, text]) => {
      const emit = (window as unknown as { __emit: (e: unknown) => void }).__emit;
      emit({ type: "input_audio_buffer.speech_started", item_id: id });
      emit({ type: "input_audio_buffer.speech_stopped", item_id: id });
      emit({ type: "input_audio_buffer.committed", item_id: id });
      emit({ type: "conversation.item.input_audio_transcription.completed", item_id: id, transcript: text });
    },
    [id, text],
  );
}

export async function partial(page: Page, id: string, delta: string) {
  await page.evaluate(
    ([id, delta]) =>
      (window as unknown as { __emit: (e: unknown) => void }).__emit({
        type: "conversation.item.input_audio_transcription.delta",
        item_id: id,
        delta,
      }),
    [id, delta],
  );
}

export async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "เลือกผู้ป่วย" })).toBeVisible();
}

export async function openRecording(page: Page, id = "SYN-2026-0023") {
  await page.getByRole("radio", { name: new RegExp(id) }).check({ force: true });
  await page.getByRole("checkbox", { name: "แจ้งผู้ป่วยแล้วว่าจะบันทึกเสียงบทสนทนา" }).check({ force: true });
  await page.getByRole("button", { name: "เปิดหน้าบันทึก" }).click();
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "idle");
}

export async function startListening(page: Page) {
  await page.getByTestId("rec-button").click();
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "listening");
}
