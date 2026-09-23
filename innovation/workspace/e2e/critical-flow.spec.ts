import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
async function createCase(page: Page, id: string) {
  await page.goto("/nurse");
  await page.getByRole("button", { name: "เริ่มเคสจำลอง", exact: true }).click();
  await page.getByRole("textbox", { name: "รหัสเคส", exact: true }).fill(id);
  await page.getByLabel("อายุผู้ป่วยสมมติ").fill("42");
  await page.getByLabel("ยืนยันว่าเคสนี้ไม่มีข้อมูลที่ระบุตัวผู้ป่วยจริง").check();
  await page.getByRole("button", { name: "สร้างและเปิดเคส" }).click();
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toBeVisible();
}
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  const blocking = result.violations.filter(v => ["critical", "serious"].includes(v.impact || ""));
  expect(blocking, JSON.stringify(blocking.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) })))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)).toBe(false);
}
test("separate products and legacy intake redirect", async ({ page }) => {
  await page.goto("/platform");
  await expect(page).toHaveTitle("MedX Clinical Review · Clinical Front Door");
  await expect(page.getByRole("button", { name: "เริ่มเคสจำลอง" })).toHaveCount(0);
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toHaveCount(0);
  await accessible(page);
  await page.goto("/platform#/cases/legacy-medx/intake");
  await expect(page).toHaveURL(/\/nurse#\/voice\/legacy-medx\/intake/);
  await expect(page).toHaveTitle("MedX Intake · Clinical Front Door");
  await expect(page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" })).toHaveCount(0);
});
test("intake to clinical review, revision safety and accessibility", async ({ page }, info) => {
  const id = `medx-${info.project.name}-${Date.now()}`;
  await createCase(page, id);
  await page.getByLabel("ข้อความถึงผู้ช่วย").fill("อาการ: ไอสองวัน เป็นข้อมูลสังเคราะห์");
  await page.getByRole("button", { name: "ส่งข้อความ" }).click();
  await page.getByRole("button", { name: /มีข้อมูลจากผู้ช่วยรอตรวจ 1 รายการ/ }).click();
  await page.getByRole("button", { name: /ยืนยันข้อมูลที่เลือก 1 รายการ/ }).click();
  await expect(page.getByRole("button", { name: "เตรียมร่างส่งตรวจ", exact: true })).toBeEnabled();
  await accessible(page);
  await page.screenshot({ path: path.resolve(`../../artifacts/medx/intake-${info.project.name}.png`), fullPage: true });
  await page.getByRole("button", { name: "เตรียมร่างส่งตรวจ", exact: true }).click();
  await page.getByRole("link", { name: "เปิดร่างใน Clinical Review" }).click();
  await expect(page.getByRole("heading", { name: "ตรวจร่างฉบับที่ 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "เตรียมร่างส่งตรวจ" })).toHaveCount(0);
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toHaveCount(0);
  await page.getByRole("button", { name: "แก้ไขข้อความ", exact: true }).click();
  await page.getByLabel("ข้อความสรุป").fill("ร่างสังเคราะห์ที่ผู้ตรวจแก้ไขแล้ว");
  await page.getByLabel(/รายละเอียดเหตุผล/).fill("ปรับภาษาให้ชัดเจน");
  await expect(page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" })).toBeDisabled();
  await page.getByRole("button", { name: "บันทึกเป็นฉบับใหม่" }).click();
  await expect(page.getByRole("heading", { name: "ตรวจร่างฉบับที่ 2" })).toBeVisible();
  await page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" }).click();
  await expect(page.locator(".draft-review .status-badge", { hasText: "ยืนยันแล้ว" })).toBeVisible();
  await accessible(page);
  await page.screenshot({ path: path.resolve(`../../artifacts/medx/review-${info.project.name}.png`), fullPage: true });
  await page.getByRole("link", { name: "แก้ข้อมูลต้นทางใน Intake" }).click();
  await page.getByRole("button", { name: "เพิ่มข้อมูลด้วยตัวเอง" }).click();
  await page.getByLabel("ข้อมูลที่ตรวจแล้ว").fill("ข้อมูลเพิ่มเติมสังเคราะห์");
  await page.getByRole("button", { name: "ตรวจแล้ว บันทึกข้อมูล" }).click();
  await page.goto(`/platform#/cases/${id}/draft`);
  await expect(page.getByRole("button", { name: "ยืนยันร่างฉบับนี้" })).toBeDisabled();
});
test("keyboard and unsent input survive reload", async ({ page }) => {
  await createCase(page, `reload-${Date.now()}`);
  await page.evaluate(() => { document.body.tabIndex = -1; document.body.focus(); });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "ข้ามไปเนื้อหา" })).toBeFocused();
  await page.getByLabel("ข้อความถึงผู้ช่วย").fill("ข้อมูลสังเคราะห์ที่ยังไม่ส่ง");
  await page.reload();
  await expect(page.getByLabel("ข้อความถึงผู้ช่วย")).toHaveValue("ข้อมูลสังเคราะห์ที่ยังไม่ส่ง");
});
test("review navigation focus and expired session", async ({ page }, info) => {
  await page.goto("/platform");
  if (info.project.name === "tablet") {
    const menu = page.getByRole("button", { name: "เมนู", exact: true });
    await menu.click();
    await page.getByRole("button", { name: "ปิดเมนู", exact: true }).click();
    await expect(menu).toBeFocused();
  }
  const search = page.getByRole("button", { name: "ค้นหา", exact: true });
  await expect(search).toBeVisible();
  await page.route("**/v2/encounters?**", route => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "AUTHENTICATION_REQUIRED" }) }));
  await search.click();
  await expect(page.getByRole("heading", { name: "ยินดีต้อนรับกลับ" })).toBeVisible();
});
