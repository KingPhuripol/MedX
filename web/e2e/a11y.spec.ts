import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PASSWORDS, ROLES, login } from "./helpers";

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

for (const vp of VIEWPORTS) {
  test.describe(`${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("login page has no serious/critical axe violations and labelled inputs", async ({ page }) => {
      await page.goto("/login");
      await expect(page.getByLabel("Username")).toBeVisible();
      await expect(page.getByLabel("Password")).toBeVisible();
      expect(await seriousViolations(page)).toEqual([]);
    });

    for (const role of ROLES) {
      test(`${role} home has no serious/critical axe violations`, async ({ page }) => {
        await login(page, role);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        expect(await seriousViolations(page)).toEqual([]);
      });
    }

    for (const path of ["/403", "/definitely-missing"]) {
      test(`${path} has no serious/critical axe violations`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        expect(await seriousViolations(page)).toEqual([]);
      });
    }
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

test("login and logout work with the keyboard alone", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").focus();
  await page.keyboard.type("nurse1");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password")).toBeFocused();
  await page.keyboard.type(PASSWORDS.nurse);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/nurse");

  const signOut = page.getByRole("button", { name: "Sign out" });
  await expect(signOut).toBeVisible();
  for (let i = 0; i < 20 && !(await signOut.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(signOut).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/login");
  await page.goto("/nurse");
  await expect(page).toHaveURL("/login");
});
