import { expect, test, type Page } from "@playwright/test";

import { login, ROLE_PAGES, startDemoRun } from "./helpers";

const EN =
  "Research prototype — not for clinical use. Outputs are suggestions for review and require confirmation by a clinician.";
const TH = "ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง ผลลัพธ์เป็นข้อเสนอที่ต้องให้บุคลากรยืนยัน";
const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
];

async function expectDisclaimer(page: Page) {
  const note = page.getByTestId("research-disclaimer");
  await expect(note).toBeVisible();
  await expect(note).toBeInViewport();
  await expect(note).toHaveAttribute("role", "note");
  await expect(note).toContainText(EN);
  await expect(note).toContainText(TH);
}

for (const vp of VIEWPORTS) {
  test.describe(vp.name, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("login, 403, and 404 pages", async ({ page }) => {
      for (const path of ["/login", "/403", "/definitely-missing"]) {
        await page.goto(path);
        await expectDisclaimer(page);
      }
      await expect(page.getByRole("heading", { level: 1 })).toContainText("404");
    });

    test("work queue, demo launcher and every role work page", async ({ page }) => {
      for (const role of ["nurse", "physician", "pharmacist"] as const) {
        await page.context().clearCookies();
        await login(page, role);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expectDisclaimer(page);
        for (const path of [...ROLE_PAGES[role], "/demo"]) {
          await page.goto(path);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          await expectDisclaimer(page);
        }
      }
    });

    test("seeded case workspace sections", async ({ page }) => {
      await login(page, "nurse");
      await startDemoRun(page);
      for (const section of ["overview", "intake", "triage", "care", "medications", "timeline", "activity"]) {
        await page.goto(`/app/cases/SYN-2026-0017/${section}`);
        // The intake section embeds the voice-intake page, which brings its own h1.
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        await expectDisclaimer(page);
      }
    });
  });
}
