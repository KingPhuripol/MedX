/**
 * Drives the production build through all 11 comp states (SPEC §8 / V2C-C2) with the comp's synthetic data.
 * `visit(state)` is called once per state; specs screenshot, run axe or measure touch targets there.
 */
import { expect, type Page } from "@playwright/test";

import { fact, reviewSession, startResponse, turnResponse } from "../tests/fixtures/scenario";

import { login, openRecording, partial, say, setup, startListening } from "./harness";

export type Visit = (state: string, page: Page) => Promise<void>;

const T = (hms: string) => new Date(`2026-09-30T${hms}+07:00`);
const at = (hms: string) => `2026-09-30T${hms}+07:00`;

export async function loginState(page: Page, visit: Visit) {
  await setup(page, { meStatus: 401 });
  await page.goto("/");
  await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").fill("nurse1");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("nurse1-dev");
  await page.getByLabel("รหัสผ่าน", { exact: true }).focus();
  await visit("login", page);
}

/** start, idle, recording, paused, reconnecting, error (patient SYN-2026-0023). */
export async function mainFlow(page: Page, visit: Visit) {
  await page.clock.install({ time: T("10:28:18") });
  const api = await setup(page, {
    turns: [
      turnResponse({ turnId: "vt_1", text: "ปวดท้องใต้ลิ้นปี่ค่ะ", facts: [fact("chief_complaint", "abdominal_pain", "ปวดท้องใต้ลิ้นปี่", "vt_1")], known: { chief_complaint: "KNOWN" } }),
      turnResponse({ turnId: "vt_2", text: "ถ้าให้คะแนนเต็มสิบ ประมาณเท่าไรคะ", known: { chief_complaint: "KNOWN" } }),
      turnResponse({ turnId: "vt_3", text: "น่าจะเจ็ดค่ะ", facts: [fact("severity", 7, "7 จาก 10", "vt_3")], known: { chief_complaint: "KNOWN", severity: "KNOWN" } }),
    ],
  });
  await login(page);
  await page.getByRole("radio", { name: /SYN-2026-0023/ }).check({ force: true });
  await page.getByRole("checkbox", { name: "แจ้งผู้ป่วยแล้วว่าจะบันทึกเสียงบทสนทนา" }).check({ force: true });
  await visit("start", page);

  await page.getByRole("button", { name: "เปิดหน้าบันทึก" }).click();
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "idle");
  await visit("idle", page);

  await startListening(page);
  await page.clock.fastForward(222_000); // 03:42 of listening, 10:32
  await say(page, "item_1", "ปวดท้องใต้ลิ้นปี่ค่ะ");
  await say(page, "item_2", "ถ้าให้คะแนนเต็มสิบ ประมาณเท่าไรคะ");
  await say(page, "item_3", "น่าจะเจ็ดค่ะ");
  await partial(page, "item_4", "เริ่มปวดตั้งแต่เมื่อคืน");
  await expect(page.getByText("2 จาก 6 หัวข้อ")).toBeVisible();
  await expect.poll(() => api.posted.length).toBe(3);
  await visit("recording", page);

  await page.getByTestId("rec-button").click();
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "paused");
  await visit("paused", page);

  await page.getByTestId("rec-button").click();
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "listening");
  await page.clock.fastForward(16_000); // 03:58
  api.mintStatus = 502;
  await page.evaluate(() => (window as unknown as { __drop: () => void }).__drop());
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "reconnecting");
  await page.clock.fastForward(1_000); // attempt 1 fails -> attempt 2 waits 2 s
  await expect(page.getByText("กำลังเชื่อมต่อใหม่ (ครั้งที่ 2 จาก 3)")).toBeVisible();
  await visit("reconnecting", page);

  await page.clock.fastForward(2_000);
  await expect(page.getByText("กำลังเชื่อมต่อใหม่ (ครั้งที่ 3 จาก 3)")).toBeVisible();
  await page.clock.fastForward(4_000);
  await expect(page.getByTestId("rec-button")).toHaveAttribute("data-state", "error");
  await visit("error", page);
  return api;
}

/** redflag (patient SYN-2026-0017, comp 03e). */
export async function redFlagFlow(page: Page, visit: Visit) {
  await page.clock.install({ time: T("10:06:34") });
  const api = await setup(page, {
    start: startResponse("SYN-2026-0017"),
    turns: [
      turnResponse({ turnId: "vt_1", text: "เจ็บแน่นหน้าอกค่ะ", facts: [fact("chief_complaint", "chest_pain", "เจ็บแน่นหน้าอก", "vt_1")], known: { chief_complaint: "KNOWN" } }),
      turnResponse({ turnId: "vt_2", text: "เป็นมาประมาณครึ่งชั่วโมงค่ะ", facts: [fact("onset_duration", "PT30M", "ประมาณ 30 นาที", "vt_2")], known: { chief_complaint: "KNOWN", onset_duration: "KNOWN" } }),
      turnResponse({ turnId: "vt_3", text: "แน่นหน้าอก หายใจไม่ค่อยออก เหงื่อออก", known: { chief_complaint: "KNOWN", onset_duration: "KNOWN" }, nurseAttention: true }),
    ],
  });
  await login(page);
  await openRecording(page, "SYN-2026-0017");
  await startListening(page);
  await page.clock.fastForward(86_000); // 01:26, 10:08
  await say(page, "item_1", "เจ็บแน่นหน้าอกค่ะ");
  await say(page, "item_2", "เป็นมาประมาณครึ่งชั่วโมงค่ะ");
  await say(page, "item_3", "แน่นหน้าอก หายใจไม่ค่อยออก เหงื่อออก");
  await expect(page.getByRole("alert")).toBeVisible();
  await visit("redflag", page);
  return api;
}

/** complete, review, review-ready (comp 03f, 04, 04b). */
export async function completeFlow(page: Page, visit: Visit) {
  await page.clock.install({ time: T("10:29:48") });
  const all = { chief_complaint: "KNOWN", onset_duration: "KNOWN", severity: "KNOWN", allergy_status: "KNOWN" } as const;
  const api = await setup(page, {
    sessionGet: reviewSession(),
    turns: [
      turnResponse({ turnId: "vt_1", text: "ปวดท้องใต้ลิ้นปี่ค่ะ", facts: [fact("chief_complaint", "abdominal_pain", "ปวดท้องใต้ลิ้นปี่", "vt_1")], known: { chief_complaint: "KNOWN" } }),
      turnResponse({ turnId: "vt_2", text: "ประมาณวันนึงค่ะ", facts: [fact("onset_duration", "P1D", "ประมาณ 1 วัน", "vt_2")], known: { chief_complaint: "KNOWN", onset_duration: "KNOWN" } }),
      turnResponse({ turnId: "vt_3", text: "น่าจะเจ็ดค่ะ", facts: [fact("severity", 7, "7 จาก 10", "vt_3")], known: { chief_complaint: "KNOWN", onset_duration: "KNOWN", severity: "KNOWN" } }),
      turnResponse({
        turnId: "vt_4",
        text: "เคยกินอะม็อกซี่แล้วผื่นขึ้นค่ะ",
        facts: [fact("allergy_status", "present", "แพ้ยา", "vt_4"), fact("allergens", ["amoxicillin"], "แพ้อะม็อกซีซิลลิน", "vt_4")],
        known: all,
      }),
      turnResponse({ turnId: "vt_5", text: "กินยาลดกรดอยู่ค่ะ", facts: [fact("current_medications", ["ยาลดกรด"], "ยาลดกรด", "vt_5")], known: { ...all, current_medications: "KNOWN" } }),
      turnResponse({ turnId: "vt_6", text: "มีโรคประจำตัวไหมคะ", known: { ...all, current_medications: "KNOWN" } }),
      turnResponse({ turnId: "vt_7", text: "ความดันสูงค่ะ กินยาทุกเช้า", facts: [fact("relevant_history", ["hypertension"], "ความดันโลหิตสูง", "vt_7")], known: { ...all, current_medications: "KNOWN", relevant_history: "KNOWN" } }),
      turnResponse({ turnId: "vt_8", text: "จำชื่อยาไม่ได้ค่ะ", known: { ...all, current_medications: "KNOWN", relevant_history: "KNOWN" } }),
    ],
  });
  await login(page);
  await openRecording(page);
  await startListening(page);
  await page.clock.fastForward(300_000);
  for (const [i, text] of ["ปวดท้องใต้ลิ้นปี่ค่ะ", "ประมาณวันนึงค่ะ", "น่าจะเจ็ดค่ะ", "เคยกินอะม็อกซี่แล้วผื่นขึ้นค่ะ", "กินยาลดกรดอยู่ค่ะ"].entries()) {
    await say(page, `item_${i + 1}`, text);
  }
  await expect.poll(() => api.posted.length).toBe(5);
  await page.clock.fastForward(48_000); // 10:35:36
  await say(page, "item_6", "มีโรคประจำตัวไหมคะ");
  await say(page, "item_7", "ความดันสูงค่ะ กินยาทุกเช้า");
  await expect.poll(() => api.posted.length).toBe(7);
  await page.clock.fastForward(24_000); // 10:36:00, 06:12
  await say(page, "item_8", "จำชื่อยาไม่ได้ค่ะ");
  await expect.poll(() => api.posted.length).toBe(8);
  await expect(page.getByText("ได้ข้อมูลครบ 6 หัวข้อแล้ว")).toBeVisible();
  await visit("complete", page);

  await page.getByRole("button", { name: "จบการบันทึก" }).click();
  await expect(page.getByRole("heading", { name: "ตรวจทานข้อมูล" })).toBeVisible();
  const item = (label: string) => page.locator(`li[data-field="${label}"]`);
  await item("chief_complaint").getByRole("button", { name: "ยืนยัน" }).click();
  await item("onset_duration").getByRole("button", { name: "ยืนยัน" }).click();
  await item("current_medications").getByRole("button", { name: "แก้ไข" }).click();
  await page.getByLabel("ค่าที่ถูกต้อง").fill("ยาลดกรด ไม่ทราบชื่อ ญาติจะนำซองยามาให้ดู");
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.evaluate(() => window.scrollTo(0, 0));
  await visit("review", page);

  await page.getByRole("button", { name: "บันทึกการแก้ไข" }).click();
  for (const f of ["severity", "allergy_status", "relevant_history"]) await item(f).getByRole("button", { name: "ยืนยัน" }).click();
  await expect(page.getByText("ตรวจครบ 6 หัวข้อ")).toBeVisible();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.evaluate(() => window.scrollTo(0, 0));
  await visit("review-ready", page);
  return api;
}

export { at };
