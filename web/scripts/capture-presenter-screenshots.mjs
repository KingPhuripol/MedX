import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const baseURL = process.env.BASE_URL || "http://127.0.0.1:3120";
const output = resolve(process.cwd(), "../docs/screenshots/medx-clinical-operations");
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
const page = await context.newPage();

async function ready() {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
}

async function shot(name, fullPage = true) {
  await ready();
  await page.screenshot({ path: resolve(output, `${name}.png`), fullPage, animations: "disabled" });
}

async function login(role) {
  const passwords = {
    nurse: "nurse1-dev-only",
    physician: "physician1-dev-only",
    pharmacist: "pharmacist1-dev-only",
  };
  await page.goto(`${baseURL}/login`);
  await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").fill(`${role}1`);
  await page.getByLabel("รหัสผ่าน").fill(passwords[role]);
  await page.getByRole("button", { name: "เข้าสู่ระบบเดโม" }).click();
  await page.waitForURL("**/app/queue");
  await ready();
}

async function logout() {
  await page.getByRole("button", { name: /ออกจากระบบ/ }).click();
  await page.waitForURL("**/login");
}

try {
  await page.goto(`${baseURL}/login`);
  await shot("01-login", false);

  await login("nurse");
  await page.goto(`${baseURL}/demo`);
  await page.getByRole("button", { name: /เริ่มรอบเดโมใหม่/ }).waitFor();
  await shot("02-demo-launcher", false);
  await page.getByRole("button", { name: /เริ่มรอบเดโมใหม่/ }).click();
  await page.waitForURL("**/app/queue");
  await page.getByRole("heading", { name: "คิวรับเข้าและคัดกรอง" }).waitFor();
  await shot("03-nurse-work-queue", false);

  const runId = await page.evaluate(() => localStorage.getItem("medx.demo.run"));
  if (!runId) throw new Error("demo run was not created");
  const caseBase = `${baseURL}/app/cases/SYN-2026-0017`;

  await page.goto(`${caseBase}/overview?run=${runId}`);
  await shot("04-case-overview");
  await page.goto(`${caseBase}/intake?run=${runId}`);
  await shot("05-nurse-intake");
  await page.goto(`${caseBase}/triage?run=${runId}`);
  await shot("06-nurse-triage-review");

  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await page.getByRole("button", { name: /ส่งต่อให้แพทย์/ }).click();
  await page.goto(`${caseBase}/timeline?run=${runId}`);
  await shot("07-case-timeline-after-nurse");
  await logout();

  await login("physician");
  await shot("08-physician-work-queue", false);
  await page.goto(`${caseBase}/care?run=${runId}`);
  await shot("09-physician-care-review");
  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await page.getByRole("button", { name: /ส่งต่อให้เภสัชกร/ }).click();
  await logout();

  await login("pharmacist");
  await shot("10-pharmacist-work-queue", false);
  await page.goto(`${caseBase}/medications?run=${runId}`);
  await shot("11-pharmacist-medication-review");
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await page.goto(`${caseBase}/activity?run=${runId}`);
  await shot("12-append-only-activity");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseURL}/app/queue`);
  await shot("13-mobile-role-queue");
  await page.goto(`${caseBase}/triage?run=${runId}`);
  await shot("14-mobile-case-companion");
} finally {
  await browser.close();
}

console.log(output);
