import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PASSWORDS, ROLE_PAGES, ROLES, login, startDemoRun } from "./helpers";

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
];
const CASE_SECTIONS = ["overview", "intake", "triage", "care", "medications", "timeline", "activity"];

for (const vp of VIEWPORTS) {
  test.describe(`${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("login page has no serious/critical axe violations and labelled inputs", async ({ page }) => {
      await page.goto("/login");
      await expect(page.getByLabel("ชื่อผู้ใช้สังเคราะห์")).toBeVisible();
      await expect(page.getByLabel("รหัสผ่าน")).toBeVisible();
      expect(await seriousViolations(page)).toEqual([]);
    });

    for (const role of ROLES) {
      test(`${role} work queue, demo launcher and work pages have no serious/critical axe violations`, async ({
        page,
      }) => {
        await login(page, role);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        expect(await seriousViolations(page), "/app/queue").toEqual([]);
        for (const path of ["/demo", ...ROLE_PAGES[role]]) {
          await page.goto(path);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          expect(await seriousViolations(page), path).toEqual([]);
        }
      });
    }

    test("seeded work queue and every case workspace section have no serious/critical axe violations", async ({
      page,
    }) => {
      await login(page, "nurse");
      await startDemoRun(page);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(await seriousViolations(page), "/app/queue with run").toEqual([]);
      for (const section of CASE_SECTIONS) {
        await page.goto(`/app/cases/SYN-2026-0017/${section}`);
        // The intake section embeds the voice-intake page, which brings its own h1.
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        expect(await seriousViolations(page), section).toEqual([]);
      }
    });

    for (const path of ["/403", "/definitely-missing"]) {
      test(`${path} has no serious/critical axe violations`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        expect(await seriousViolations(page)).toEqual([]);
      });
    }

    test("triage list and review pages have no serious/critical axe violations", async ({ page }) => {
      await login(page, "nurse");
      await page.goto("/nurse/triage");
      await expect(page.getByTestId("case-list")).toBeVisible();
      expect(await seriousViolations(page)).toEqual([]);
      for (const caseRef of ["SYN-S4-002", "SYN-S4-023"]) {
        await page.goto("/nurse/triage");
        await page.getByRole("button", { name: `Assess ${caseRef}` }).click();
        await expect(page.getByRole("heading", { level: 1 })).toContainText(caseRef);
        expect(await seriousViolations(page)).toEqual([]);
      }
    });

    test("care list and review pages have no serious/critical axe violations", async ({ page }) => {
      await login(page, "physician");
      await page.goto("/physician/care");
      await expect(page.getByTestId("care-case-list")).toBeVisible();
      expect(await seriousViolations(page)).toEqual([]);
      for (const [caseId, dp] of [
        ["SYNE-0011", "T2"],
        ["SYNE-0071", "T1"],
      ]) {
        await page.goto("/physician/care");
        await page.getByRole("button", { name: `Assess ${caseId} at ${dp}` }).click();
        await expect(page.getByRole("heading", { level: 1 })).toContainText(caseId);
        await expect(page.getByTestId("redflag-section")).toBeVisible();
        expect(await seriousViolations(page)).toEqual([]);
      }
    });
  });
}

test("login and logout work with the keyboard alone", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").focus();
  await page.keyboard.type("nurse1");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("รหัสผ่าน")).toBeFocused();
  await page.keyboard.type(PASSWORDS.nurse);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/app/queue");

  const signOut = page.getByRole("button", { name: "ออกจากระบบ" });
  await expect(signOut).toBeVisible();
  for (let i = 0; i < 30 && !(await signOut.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(signOut).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/login");
  await page.goto("/nurse/triage");
  await expect(page).toHaveURL("/login");
});
