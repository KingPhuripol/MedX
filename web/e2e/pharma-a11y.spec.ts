import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { login } from "./helpers";

// S5-A17: axe, semantics, keyboard-only decisions, claim hygiene on /pharmacist/reconcile.

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

async function focusByTab(page: Page, target: ReturnType<Page["locator"]>) {
  for (let i = 0; i < 80 && !(await target.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

test("reconcile page has no serious/critical axe violations before and after a run", async ({ page }) => {
  await login(page, "pharmacist");
  await page.goto("/pharmacist/reconcile");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Medication reconciliation");
  expect(await seriousViolations(page)).toEqual([]);

  await page.getByRole("button", { name: "Run check" }).click();
  await expect(page.getByRole("status")).toContainText(/issue\(s\)/);
  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.locator("section[aria-labelledby]").first()).toBeVisible();
  await expect(page.locator("ol.issue-list > li > article").first()).toBeVisible();
  await expect(page.getByTestId("nlm-attribution")).toContainText("National Library of Medicine");
  expect(await seriousViolations(page)).toEqual([]);

  const copy = (await page.locator("main").innerText()).toLowerCase();
  expect(copy).not.toMatch(/diagnos|prescrib|treat/);
});

test("run, confirm and dismiss work with the keyboard alone", async ({ page }) => {
  await login(page, "pharmacist");
  await page.goto("/pharmacist/reconcile");

  const runButton = page.getByRole("button", { name: "Run check" });
  await expect(runButton).toBeEnabled();
  await focusByTab(page, runButton);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText(/issue\(s\)/);

  const articles = page.locator("ol.issue-list > li > article");
  const confirm = articles.nth(0).getByRole("button", { name: "Confirm" });
  await focusByTab(page, confirm);
  await page.keyboard.press("Enter");
  await expect(articles.nth(0).getByTestId("issue-status")).toHaveText("confirmed");

  const reason = articles.nth(1).getByLabel("Reason for dismissing");
  await focusByTab(page, reason);
  await page.keyboard.type("Keyboard-only synthetic review");
  await page.keyboard.press("Tab");
  await expect(articles.nth(1).getByRole("button", { name: "Dismiss" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(articles.nth(1).getByTestId("issue-status")).toHaveText("dismissed");
});
