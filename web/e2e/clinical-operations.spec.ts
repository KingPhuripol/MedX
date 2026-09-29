import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login, startDemoRun } from "./helpers";

async function assertNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(
    0,
  );
}

async function assertTouchTargets(page: Page) {
  const undersized = await page.locator("button, a.ui-button, .nav-link, .case-tab").evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 43.5);
      })
      .map((node) => node.textContent?.trim()),
  );
  expect(undersized).toEqual([]);
}

async function assertA11y(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
}

test("login and seeded launcher preserve authentication and synthetic boundary", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง", { exact: false })).toBeVisible();
  await login(page, "nurse");
  await expect(page.getByRole("heading", { name: /คิวงานตามบทบาท|คิวรับเข้าและคัดกรอง/ })).toBeVisible();
  await startDemoRun(page);
  await expect(page.getByRole("heading", { name: "คิวรับเข้าและคัดกรอง" })).toBeVisible();
  await expect(page.getByText("SYN-2026-0017").first()).toBeVisible();
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`queue and case workspace are safe at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, "nurse");
    await startDemoRun(page);
    await assertNoOverflow(page);
    await assertTouchTargets(page);
    await page
      .getByRole("link", { name: /เปิดเคส/ })
      .nth(1)
      .click();
    await expect(page.getByRole("heading", { name: "ทบทวนข้อเสนอการคัดกรอง" })).toBeVisible();
    await expect(page.getByText("พบสัญญาณที่ต้องประเมินเร่งด่วน", { exact: true })).toBeVisible();
    await assertNoOverflow(page);
    await assertTouchTargets(page);
    await assertA11y(page);
  });
}

test("complete synthetic journey nurse to physician to pharmacist is append-only", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  await page
    .getByRole("link", { name: /เปิดเคส/ })
    .nth(1)
    .click();
  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await expect(page.getByText("ตรวจทานโดยบุคลากรแล้ว")).toBeVisible();
  await page.getByRole("button", { name: /ส่งต่อให้แพทย์/ }).click();
  await page.getByRole("button", { name: /ออกจากระบบ/ }).click();

  await login(page, "physician");
  await page.getByRole("link", { name: /เปิดเคส/ }).click();
  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await page.getByRole("button", { name: /ส่งต่อให้เภสัชกร/ }).click();
  await page.getByRole("button", { name: /ออกจากระบบ/ }).click();

  await login(page, "pharmacist");
  await page.getByRole("link", { name: /เปิดเคส/ }).click();
  await expect(page.getByRole("heading", { name: "Medication reconciliation" })).toBeVisible();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await expect(page.getByText("ตรวจทานแล้ว", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "กิจกรรม" }).click();
  await expect(page.getByText("ส่งต่อเคสแล้ว").first()).toBeVisible();
  await expect(page.getByText("บันทึก medication review แล้ว")).toBeVisible();
});

test("legacy role homes redirect to the canonical queue; role work pages stay in the shell", async ({ page }) => {
  await login(page, "nurse");
  for (const path of ["/nurse", "/physician", "/pharmacist"]) {
    await page.goto(path);
    await expect(page).toHaveURL("/app/queue");
  }
  // Domain work pages are not redirected into the seeded demo case (a different synthetic patient).
  for (const [path, heading] of [
    ["/nurse/triage", "Triage cases"],
    ["/nurse/intake", "Voice intake"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("navigation").getByRole("link", { name: /คิวงาน/ })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
  }
});

test("review flow is keyboard operable and guarded by acknowledgement", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  await page
    .getByRole("link", { name: /เปิดเคส/ })
    .nth(1)
    .focus();
  await page.keyboard.press("Enter");
  const confirm = page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ });
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/รับทราบ red flag/).focus();
  await page.keyboard.press("Space");
  await expect(confirm).toBeEnabled();
  await confirm.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("ตรวจทานโดยบุคลากรแล้ว")).toBeVisible();
});

// U5 WP-A: role tool links (A-4), compact tablet/phone nav (A-2), 403/404 exits (A-5).
const TOOL_LINKS = { nurse: 2, physician: 1, pharmacist: 1 } as const;
for (const role of ["nurse", "physician", "pharmacist"] as const) {
  test(`${role} queue lists ${TOOL_LINKS[role]} role tool link(s) without a demo run`, async ({ page }) => {
    await login(page, role);
    const tools = page.getByRole("region", { name: "เครื่องมือของบทบาท" });
    await expect(tools).toBeVisible();
    await expect(tools.getByRole("link")).toHaveCount(TOOL_LINKS[role]);
    await expect(page.getByRole("link", { name: "ไปที่รอบเดโม" })).toBeVisible();
  });
}

test("tablet and phone shell: compact top bar and nav, sign-out never below the nav", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  for (const [width, height, maxH1] of [
    [768, 1024, 260],
    [390, 844, 340],
  ]) {
    await page.setViewportSize({ width, height });
    const m = await page.evaluate(() => {
      const box = (el: Element | null) => (el ? el.getBoundingClientRect() : null);
      const links = [...document.querySelectorAll(".nav-link")];
      const logout = [...document.querySelectorAll("button")].find((b) => /ออกจากระบบ/.test(b.textContent || ""));
      return {
        nav: box(document.querySelector(".app-nav"))!.height,
        h1: box(document.querySelector("h1"))!.top + scrollY,
        lastNav: box(links[links.length - 1])!.top,
        logout: box(logout || null)!.top,
      };
    });
    expect(m.nav, `nav height at ${width}`).toBeLessThanOrEqual(128);
    expect(m.h1, `h1 top at ${width}`).toBeLessThanOrEqual(maxH1);
    expect(m.logout, "sign-out sits in the top bar row").toBeLessThanOrEqual(m.lastNav);
    await assertNoOverflow(page);
  }
});

test("403 and 404 offer a way back to the queue", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/physician/care");
  await expect(page.getByTestId("forbidden")).toBeVisible();
  await expect(page.getByRole("link", { name: "กลับไปคิวงาน" })).toBeVisible();
  await page.goto("/definitely-missing");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("404");
  await expect(page.getByRole("link", { name: "กลับไปคิวงาน" })).toBeVisible();
});
