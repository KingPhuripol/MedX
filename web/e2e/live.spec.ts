/**
 * Slice v1 — MedX Live browser checks (E1-E7 plus error, red-flag and screenshot runs).
 * The real backend (mock gateway) serves sessions, turns and facts. The realtime service is fully faked:
 * the two realtime endpoints and the SDP endpoint are routed, RTCPeerConnection is replaced, and a request
 * guard fails the test if any request leaves 127.0.0.1/localhost.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { login } from "./helpers";

const WEB_PORT = process.env.WEB_PORT || "3000";
const ORIGIN = `http://127.0.0.1:${WEB_PORT}`;
const SHOTS_DIR = process.env.V1_SHOTS_DIR || join(__dirname, "..", "..", "artifacts", "factory", "v1", "web");

const Q1 = "วันนี้มีอาการอะไรมาคะ";
const Q_SEVERITY = "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ";

test.use({
  launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] },
  permissions: ["microphone"],
});

const CONFIG = {
  enabled: true,
  reason: null,
  access_code_required: false,
  max_session_seconds: 300,
  vendor_label: "TestVendor",
  model: "model-test",
  transcribe_model: "transcribe-test",
};
const SESSION = {
  client_secret: "ek_FAKE",
  expires_at: 4102444800,
  connect_url: `${ORIGIN}/__fake-rt/calls`,
  data_channel: "oai-events",
  model: "model-test",
  transcribe_model: "transcribe-test",
  vendor_label: "TestVendor",
  max_session_seconds: 300,
  instructions_version: "v1-live-0.1.0",
};

type Sent = { type: string; response?: { input?: { content?: { text?: string }[] }[] } };
declare global {
  interface Window {
    __liveFake: { sent: Sent[]; emit(evt: object): void; dc: unknown; tracks: MediaStreamTrack[]; answer?: { sdp: string } };
  }
}

interface FakeOptions {
  config?: { status: number; body: object };
  session?: { status: number; body: object };
  sdpStatus?: number;
}

/** Fake realtime peer connection and routed endpoints; returns the list of off-host requests (must stay empty). */
async function installFakes(page: Page, opts: FakeOptions = {}): Promise<string[]> {
  const external: string[] = [];
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (["data:", "blob:", "about:"].includes(url.protocol)) return;
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") external.push(req.url());
  });
  await page.addInitScript(() => {
    const fake = { sent: [] as unknown[], emit(evt: object) { (fake.dc as { onmessage?: (m: { data: string }) => void } | null)?.onmessage?.({ data: JSON.stringify(evt) }); }, dc: null as unknown, tracks: [] as MediaStreamTrack[] };
    (window as unknown as { __liveFake: unknown }).__liveFake = fake;
    class FakeDC {
      readyState = "open";
      onmessage: ((m: { data: string }) => void) | null = null;
      constructor(public label: string) { fake.dc = this; }
      send(data: string) { fake.sent.push(JSON.parse(data)); }
      close() { this.readyState = "closed"; }
    }
    class FakePC {
      connectionState = "new";
      ontrack: unknown = null;
      onconnectionstatechange: unknown = null;
      addTrack(t: MediaStreamTrack) { fake.tracks.push(t); return {}; }
      createDataChannel(label: string) { return new FakeDC(label); }
      async createOffer() { return { type: "offer", sdp: "v=0 fake-offer" }; }
      async setLocalDescription() {}
      async setRemoteDescription(d: { sdp: string }) { (fake as unknown as { answer: unknown }).answer = d; }
      close() { this.connectionState = "closed"; }
    }
    (window as unknown as { RTCPeerConnection: unknown }).RTCPeerConnection = FakePC;
  });
  const json = (o: { status: number; body: object }) => ({ status: o.status, contentType: "application/json", body: JSON.stringify(o.body) });
  await page.route("**/api/voice/realtime/config", (r) => r.fulfill(json(opts.config ?? { status: 200, body: CONFIG })));
  await page.route("**/api/voice/realtime/session", (r) => r.fulfill(json(opts.session ?? { status: 200, body: SESSION })));
  await page.route("**/__fake-rt/calls", (r) =>
    r.fulfill({ status: opts.sdpStatus ?? 201, contentType: "application/sdp", body: "v=0 fake-answer" }),
  );
  return external;
}

const state = (page: Page) => page.getByTestId("live-root");
const emit = (page: Page, evt: object) => page.evaluate((e) => window.__liveFake.emit(e), evt);
const sent = (page: Page) => page.evaluate(() => window.__liveFake.sent);

async function openLive(page: Page, query = "") {
  await page.goto(`/live${query}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/MedX\s*Live/);
}

async function startCall(page: Page) {
  await expect(state(page)).toHaveAttribute("data-state", "idle");
  await page.getByTestId("live-start").click();
  await page.waitForFunction(() => Boolean(window.__liveFake.dc));
  await emit(page, { type: "session.created" });
  await expect(state(page)).toHaveAttribute("data-state", "listening");
}

async function medxSpeaks(page: Page) {
  await emit(page, { type: "output_audio_buffer.started", response_id: "r" });
  await expect(state(page)).toHaveAttribute("data-state", "speaking");
  await emit(page, { type: "output_audio_buffer.stopped", response_id: "r" });
  await expect(state(page)).toHaveAttribute("data-state", "listening");
}

async function patientSays(page: Page, item: string, transcript: string) {
  await emit(page, { type: "input_audio_buffer.speech_started", item_id: item, audio_start_ms: 0 });
  await emit(page, { type: "input_audio_buffer.speech_stopped", item_id: item, audio_end_ms: 900 });
  await emit(page, { type: "conversation.item.input_audio_transcription.completed", item_id: item, content_index: 0, transcript });
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

async function layoutChecks(page: Page, button: string) {
  const vp = page.viewportSize()!;
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow at ${vp.width}`).toBeLessThanOrEqual(0);
  const box = await page.getByTestId(button).boundingBox();
  expect(box, button).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height, `${button} bottom edge at ${vp.width}x${vp.height}`).toBeLessThanOrEqual(vp.height);
  expect(box!.x + box!.width).toBeLessThanOrEqual(vp.width);
}

test.describe("MedX Live", () => {
  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
  });

  test("E1-E3: a spoken intake fills the sheet and hands off to the nurse", async ({ page }) => {
    const external = await installFakes(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, "nurse");
    await openLive(page);
    await expect(page.getByTestId("research-disclaimer")).toBeVisible();
    await startCall(page);

    // E1: question 1 is spoken from the server text, then the patient answers.
    await expect(page.getByTestId("live-question")).toHaveText(Q1);
    expect((await sent(page)).filter((e) => e.type === "response.create")[0].response!.input![0].content![0].text).toBe(Q1);
    await medxSpeaks(page);
    await patientSays(page, "item_1", "เจ็บหน้าอกมาสองชั่วโมงค่ะ");
    await expect(page.getByTestId("live-fact-row")).toHaveCount(2);
    for (const field of ["chief_complaint", "onset_duration"]) {
      await expect(page.locator(`[data-testid=live-fact-row][data-field=${field}]`)).toContainText("จากประโยค #2");
    }
    await expect(page.getByTestId("live-question")).toHaveText(Q_SEVERITY);
    await expect.poll(async () => (await sent(page)).filter((e) => e.type === "response.create").length).toBe(2);
    const spoken = (await sent(page)).filter((e) => e.type === "response.create")[1];
    expect(spoken.response!.input![0].content![0].text).toBe(Q_SEVERITY);
    await expect(page.getByTestId("live-last-utterance")).toContainText("เจ็บหน้าอกมาสองชั่วโมงค่ะ");
    expect((await sent(page)).every((e) => ["response.create", "input_audio_buffer.clear"].includes(e.type))).toBe(true);

    // E2: a trailing full stop from the recogniser is stripped, so the rule extractor still matches.
    await medxSpeaks(page);
    await patientSays(page, "item_2", "ไม่เคยแพ้ยาค่ะ.");
    const allergy = page.locator("[data-testid=live-fact-row][data-field=allergy_status]");
    await expect(allergy).toContainText("จากประโยค #4");
    await expect(allergy).toContainText("none");

    // E3: END -> finish -> summary -> handoff link.
    await page.getByTestId("live-end").click();
    await expect(state(page)).toHaveAttribute("data-state", "ended");
    const summary = page.getByTestId("live-summary");
    await expect(summary).toContainText("พยาบาลจบการสนทนา");
    await expect(summary).toContainText("ความรุนแรง");
    await expect(summary).toContainText("หลักฐานที่บันทึก:");
    await expect(summary.getByRole("heading", { level: 2 })).toBeFocused();
    await page.getByTestId("live-handoff").click();
    await expect(page).toHaveURL(/\/nurse\/triage$/);
    expect(external, "no request may leave localhost").toEqual([]);
  });

  test("E4: axe is clean in idle, listening (sheet open) and ended; layout fits at 390 and 430", async ({ page }) => {
    const external = await installFakes(page);
    await login(page, "nurse");
    for (const vp of [
      { width: 390, height: 844 },
      { width: 430, height: 932 },
    ]) {
      await page.setViewportSize(vp);
      await openLive(page);
      await expect(state(page)).toHaveAttribute("data-state", "idle");
      await layoutChecks(page, "live-start");
      if (vp.width === 390) expect(await seriousViolations(page)).toEqual([]);
      await startCall(page);
      await layoutChecks(page, "live-end");
      if (vp.width === 390) {
        await medxSpeaks(page);
        await patientSays(page, "item_1", "เจ็บหน้าอกมาสองชั่วโมงค่ะ");
        await expect(page.getByTestId("live-fact-row")).toHaveCount(2);
        await page.getByTestId("live-sheet-toggle").click();
        await expect(page.getByTestId("live-sheet-toggle")).toHaveAttribute("aria-expanded", "true");
        await expect(page.getByTestId("live-missing-chip").first()).toBeVisible();
        expect(await seriousViolations(page)).toEqual([]);
        await page.getByTestId("live-end").click();
        await expect(state(page)).toHaveAttribute("data-state", "ended");
        expect(await seriousViolations(page)).toEqual([]);
      }
    }
    // Usable at 1280: two columns, the sheet is a visible right panel and needs no toggle.
    await page.setViewportSize({ width: 1280, height: 800 });
    await openLive(page);
    await startCall(page);
    await expect(page.getByTestId("live-sheet")).toBeVisible();
    await expect(page.getByTestId("live-sheet-toggle")).toHaveCount(0);
    await layoutChecks(page, "live-end");
    expect(await seriousViolations(page)).toEqual([]);
    expect(external).toEqual([]);
  });

  test("E5: voice disabled shows the reason and a typed turn fills a row", async ({ page }) => {
    const external = await installFakes(page, {
      config: { status: 200, body: { ...CONFIG, enabled: false, reason: "voice_disabled" } },
    });
    await login(page, "nurse");
    await openLive(page);
    await expect(state(page)).toHaveAttribute("data-state", "disabled");
    await expect(page.getByTestId("live-status")).toHaveText("โหมดเสียงยังไม่เปิดใช้งาน — ใช้การพิมพ์แทนได้");
    await expect(page.getByTestId("live-disabled")).toHaveText("ผู้ดูแลระบบยังไม่เปิดโหมดเสียง");
    await expect(page.getByTestId("live-vendor-banner")).toHaveCount(0);
    await expect(page.getByTestId("live-type-form")).toBeVisible();
    await expect(page.getByTestId("live-question")).toHaveText(Q1);
    await page.getByLabel("ข้อความ").fill("เจ็บหน้าอกมาสองชั่วโมงค่ะ");
    await page.getByRole("button", { name: "ส่ง", exact: true }).click();
    await expect(page.locator("[data-testid=live-fact-row][data-field=chief_complaint]")).toContainText("จากประโยค #2");
    expect(await seriousViolations(page)).toEqual([]);
    expect(external).toEqual([]);
  });

  test("E6: a physician sees the forbidden view", async ({ page }) => {
    await installFakes(page);
    await login(page, "physician");
    await page.goto("/live");
    await expect(page.getByTestId("forbidden")).toBeVisible();
    await expect(page.getByTestId("live-root")).toHaveCount(0);
  });

  test("E7: reduced motion keeps the orb static", async ({ page }) => {
    await installFakes(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page, "nurse");
    await openLive(page);
    await startCall(page);
    const orb = page.getByTestId("live-orb");
    await emit(page, { type: "output_audio_buffer.started", response_id: "r" });
    await page.waitForTimeout(250);
    const css = await orb.evaluate((el) => ({ animation: getComputedStyle(el).animationName, transform: getComputedStyle(el).transform }));
    expect(css.animation).toBe("none");
    expect(css.transform).toBe("none");
    await expect(page.getByTestId("live-status")).toHaveText("MedX กำลังพูด…");
  });

  test("errors: mint failures, code, rate limit and connect failure keep the screen safe", async ({ page }) => {
    await login(page, "nurse");
    const fail = async (session: FakeOptions["session"], sdpStatus?: number, config?: FakeOptions["config"]) => {
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await installFakes(page, { session, sdpStatus, config });
      await openLive(page);
    };
    // access code invalid returns to idle with a field error
    await fail(
      { status: 403, body: { detail: { reason: "access_code_invalid" } } },
      undefined,
      { status: 200, body: { ...CONFIG, access_code_required: true } },
    );
    await expect(page.getByTestId("live-access-code")).toBeVisible();
    await page.getByTestId("live-access-code").fill("wrong-code");
    await page.getByTestId("live-start").click();
    await expect(page.getByText("รหัสเข้าใช้ไม่ถูกต้อง")).toBeVisible();
    await expect(state(page)).toHaveAttribute("data-state", "idle");
    // 429
    await fail({ status: 429, body: { detail: { reason: "rate_limited" } } });
    await page.getByTestId("live-start").click();
    await expect(state(page)).toHaveAttribute("data-state", "error");
    await expect(page.getByTestId("live-error")).toHaveText("เริ่มสนทนาบ่อยเกินไป ลองใหม่ในอีกสักครู่");
    await expect(page.getByTestId("live-retry")).toBeVisible();
    await expect(page.getByTestId("live-type-toggle")).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
    // upstream failure
    await fail({ status: 502, body: { detail: { reason: "upstream_error", upstream_status: 500 } } });
    await page.getByTestId("live-start").click();
    await expect(page.getByTestId("live-error")).toHaveText("เชื่อมต่อบริการเสียงไม่สำเร็จ");
    // SDP failure
    await fail(undefined, 500);
    await page.getByTestId("live-start").click();
    await expect(page.getByTestId("live-error")).toHaveText("เชื่อมต่อบริการเสียงไม่สำเร็จ");
    // voice turned off after the config check
    await fail({ status: 503, body: { detail: { reason: "not_configured" } } });
    await page.getByTestId("live-start").click();
    await expect(state(page)).toHaveAttribute("data-state", "disabled");
    await expect(page.getByTestId("live-disabled")).toHaveText("ยังไม่ได้ตั้งค่าบริการเสียง");
  });

  test("a red-flag phrase shows a critical alert, stops listening and ends the call", async ({ page }) => {
    await installFakes(page);
    await login(page, "nurse");
    await openLive(page);
    await startCall(page);
    await medxSpeaks(page);
    await patientSays(page, "item_1", "หมดสติไปครู่หนึ่งค่ะ");
    const alert = page.getByTestId("live-alert-nurse-attention");
    await expect(alert).toBeVisible();
    await expect(alert).toHaveAttribute("role", "alert");
    await expect(alert).toContainText("พบสัญญาณอันตราย");
    expect(await page.evaluate(() => window.__liveFake.tracks.every((t) => !t.enabled))).toBe(true);
    // the handoff sentence is spoken, then the call ends by itself
    await emit(page, { type: "output_audio_buffer.started", response_id: "r" });
    await emit(page, { type: "output_audio_buffer.stopped", response_id: "r" });
    await expect(state(page)).toHaveAttribute("data-state", "ended");
    await expect(page.getByTestId("live-summary")).toContainText("พบคำพูดที่ต้องให้พยาบาลประเมินทันที");
    await expect(page.getByTestId("live-alert-nurse-attention")).toBeVisible();
  });

  test("screens: every state at 390x844, 430x932 and 1280x800", async ({ page }) => {
    mkdirSync(SHOTS_DIR, { recursive: true });
    await login(page, "nurse");
    const shot = (name: string) => page.screenshot({ path: join(SHOTS_DIR, `${name}.png`) });
    const sizes = [
      { width: 390, height: 844 },
      { width: 430, height: 932 },
    ];
    for (const vp of sizes) {
      const tag = `${vp.width}x${vp.height}`;
      await page.setViewportSize(vp);
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await installFakes(page, { config: { status: 200, body: { ...CONFIG, access_code_required: true } } });
      await openLive(page, "?case=SYN-2026-0017&run=demo-run");
      await page.getByTestId("live-access-code").fill("demo-code");
      await shot(`idle-${tag}`);
      await page.getByTestId("live-start").click();
      await page.waitForFunction(() => Boolean(window.__liveFake.dc));
      await shot(`connecting-${tag}`);
      await emit(page, { type: "session.created" });
      await expect(state(page)).toHaveAttribute("data-state", "listening");
      await expect(page.getByTestId("live-question")).toHaveText(Q1);
      await shot(`listening-empty-${tag}`);
      await medxSpeaks(page);
      await patientSays(page, "item_1", "เจ็บหน้าอกมาสองชั่วโมงค่ะ");
      await expect(page.getByTestId("live-fact-row")).toHaveCount(2);
      await shot(`processing-or-speaking-${tag}`);
      await emit(page, { type: "output_audio_buffer.started", response_id: "r" });
      await expect(state(page)).toHaveAttribute("data-state", "speaking");
      await shot(`speaking-${tag}`);
      await emit(page, { type: "output_audio_buffer.stopped", response_id: "r" });
      await expect(state(page)).toHaveAttribute("data-state", "listening");
      await shot(`listening-collapsed-${tag}`);
      await page.getByTestId("live-mute").click();
      await expect(page.getByTestId("live-status")).toHaveText("ปิดไมค์อยู่ — แตะปุ่มไมค์เพื่อเปิด");
      await shot(`muted-${tag}`);
      await page.getByTestId("live-mute").click();
      await page.getByTestId("live-sheet-toggle").click();
      await shot(`listening-expanded-${tag}`);
      await page.getByTestId("live-sheet-toggle").click();
      await page.getByTestId("live-type-toggle").click();
      await shot(`type-form-${tag}`);
      await page.getByTestId("live-type-toggle").click();
      await page.getByTestId("live-end").click();
      await expect(state(page)).toHaveAttribute("data-state", "ended");
      await shot(`ended-${tag}`);

      // error and disabled
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await installFakes(page, { session: { status: 502, body: { detail: { reason: "upstream_error", upstream_status: 500 } } } });
      await openLive(page);
      await page.getByTestId("live-start").click();
      await expect(state(page)).toHaveAttribute("data-state", "error");
      await shot(`error-${tag}`);
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await installFakes(page, { config: { status: 200, body: { ...CONFIG, enabled: false, reason: "voice_disabled" } } });
      await openLive(page);
      await expect(state(page)).toHaveAttribute("data-state", "disabled");
      await page.getByLabel("ข้อความ").fill("มีไข้มาสามวันค่ะ");
      await page.getByRole("button", { name: "ส่ง", exact: true }).click();
      await expect(page.getByTestId("live-fact-row").first()).toBeVisible();
      await shot(`disabled-${tag}`);

      // red flag
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await installFakes(page);
      await openLive(page);
      await startCall(page);
      await medxSpeaks(page);
      await patientSays(page, "item_9", "หมดสติไปครู่หนึ่งค่ะ");
      await expect(page.getByTestId("live-alert-nurse-attention")).toBeVisible();
      await shot(`red-flag-${tag}`);
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await installFakes(page);
    await openLive(page);
    await shot("idle-1280x800");
    await startCall(page);
    await medxSpeaks(page);
    await patientSays(page, "item_1", "เจ็บหน้าอกมาสองชั่วโมงค่ะ");
    await expect(page.getByTestId("live-fact-row")).toHaveCount(2);
    await shot("listening-1280x800");
    await page.getByTestId("live-end").click();
    await expect(state(page)).toHaveAttribute("data-state", "ended");
    await shot("ended-1280x800");
  });
});
