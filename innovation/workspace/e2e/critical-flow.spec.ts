import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.goto("/workspace#/cases");
  await expect(page.getByRole("heading", { name: "รับข้อมูลให้ครบ ส่งต่ออย่างชัดเจน" })).toBeVisible();
});

test("critical synthetic intake flow and accessibility", async ({ page }, testInfo) => {
  const caseId = `pilot-${testInfo.project.name}-${Date.now()}`;
  await page.getByRole("button", { name: "เริ่มเคสจำลอง" }).click();
  await page.getByRole("textbox", { name: "รหัสเคส", exact: true }).fill(caseId);
  await page.getByLabel("อายุผู้ป่วยสมมติ").fill("42");
  await page.getByLabel("ยืนยันว่าเคสนี้ไม่มีข้อมูลที่ระบุตัวผู้ป่วยจริง").check();
  await page.getByRole("button", { name: "สร้างและเปิดเคส" }).click();
  await expect(page.getByRole("heading", { name: caseId })).toBeVisible();

  await page.getByLabel("ข้อความถึงผู้ช่วย").fill("อาการ: ไอสองวัน เป็นข้อมูลสังเคราะห์");
  await page.getByRole("button", { name: "ส่งข้อความ" }).click();
  await expect(page.getByRole("heading", { name: "ตรวจข้อเสนอจากผู้ช่วย" })).toBeVisible();
  await page.getByRole("button", { name: /ยืนยันข้อมูลที่เลือก 1 รายการ/ }).click();
  await expect(page.getByText("ไอสองวัน เป็นข้อมูลสังเคราะห์", { exact: false }).first()).toBeVisible();

  await page.getByRole("button", { name: "เตรียมร่างส่งต่อ" }).click();
  await expect(page.getByRole("heading", { name: /ตรวจร่างฉบับที่/ }).first()).toBeVisible();
  await expect(page.getByText(/CHIEF_COMPLAINT|HISTORY|STALE|CONFIRM/, { exact: false })).toHaveCount(0);
  await page.getByRole("button", { name: "แก้ไขหรือปฏิเสธ" }).first().click();
  await page.getByLabel("ข้อความสรุป").first().fill("ร่างส่งต่อที่ตรวจแก้แล้วสำหรับสถานการณ์จำลอง");
  await page.getByLabel("เหตุผลที่แก้ไขหรือปฏิเสธ").first().fill("ปรับภาษาให้ชัดเจน");
  await expect(page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" }).first()).toBeDisabled();
  await page.getByRole("button", { name: "บันทึกเป็นฉบับใหม่" }).first().click();
  await expect(page.getByRole("heading", { name: "ตรวจร่างฉบับที่ 2" })).toBeVisible();
  await page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" }).first().click();
  await expect(page.locator(".status-badge", { hasText: "ยืนยันแล้ว" }).first()).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
  expect(blocking, blocking.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
});

test("keyboard focus and unsent message survive reload", async ({ page }) => {
  await page.evaluate(() => { document.body.tabIndex = -1; document.body.focus(); });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "ข้ามไปเนื้อหา" })).toBeFocused();
  await page.getByRole("button", { name: "เริ่มเคสจำลอง" }).focus();
  await page.keyboard.press("Enter");
  const caseId = `reload-${Date.now()}`;
  await page.getByRole("textbox", { name: "รหัสเคส", exact: true }).fill(caseId);
  await page.getByLabel("อายุผู้ป่วยสมมติ").fill("35");
  await page.getByLabel("ยืนยันว่าเคสนี้ไม่มีข้อมูลที่ระบุตัวผู้ป่วยจริง").check();
  await page.getByRole("button", { name: "สร้างและเปิดเคส" }).click();
  await page.getByRole("button", { name: "ควรถามอะไรต่อ" }).click();
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toContainText("ควรถามอะไรต่อ");
  await page.getByLabel("ข้อความถึงผู้ช่วย").fill("ข้อความที่ยังไม่ส่ง");
  await page.reload();
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toHaveValue("ข้อความที่ยังไม่ส่ง");
});

test("responsive navigation, focus return, and narrow reflow", async ({ page }, testInfo) => {
  if (testInfo.project.name === "tablet") {
    const menu = page.getByRole("button", { name: "เมนู" });
    await menu.click();
    await expect(page.locator(".navigation")).toBeVisible();
    await page.getByRole("button", { name: "ปิดเมนู" }).click();
    await expect(menu).toBeFocused();
  } else {
    await page.setViewportSize({ width: 720, height: 900 });
    await expect(page.getByRole("button", { name: "เริ่มเคสจำลอง" })).toBeVisible();
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
});

test("expired session returns to a recoverable sign-in screen", async ({ page }) => {
  await page.route("**/v2/encounters?**", async (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ error: "AUTHENTICATION_REQUIRED" }),
  }));
  await page.getByRole("button", { name: "ค้นหา" }).click();
  await expect(page.getByRole("heading", { name: "เข้าสู่พื้นที่ทำงาน" })).toBeVisible();
  await expect(page.getByText("เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")).toBeVisible();
});
