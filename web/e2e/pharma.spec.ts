import { expect, test, type Page } from "@playwright/test";

import { login } from "./helpers";

// S5-A16: pharmacist reconcile flow on the slice ports (web 3105 -> API 8105). Synthetic fixtures only.

async function runDemo(page: Page, fixtureRef = "demo-01") {
  await login(page, "pharmacist");
  await page.getByRole("link", { name: "Medication reconciliation" }).click();
  await expect(page).toHaveURL(/\/pharmacist\/reconcile/);
  await expect(page.getByRole("heading", { level: 1, name: "Medication reconciliation" })).toBeVisible();
  const fixture = page.getByLabel("Synthetic patient");
  await expect(fixture.locator(`option[value="${fixtureRef}"]`)).toHaveCount(1);
  await fixture.selectOption(fixtureRef);
  await page.getByRole("button", { name: "Run check" }).click();
  await expect(page.getByRole("status")).toContainText(/issue\(s\)/);
}

test("pharmacist runs a fixture, sees allergy first with sources, confirms and dismisses; persists after reload", async ({
  page,
}) => {
  await runDemo(page);

  const articles = page.locator("ol.issue-list > li > article");
  expect(await articles.count()).toBeGreaterThanOrEqual(2);
  await expect(articles.first()).toHaveAttribute("data-type", /^allergy_/);

  // Every issue shows a sources table with caption and column headers.
  const firstTable = articles.first().locator("table");
  await expect(firstTable.locator("caption")).toContainText("Conflicting sources");
  await expect(firstTable.locator('th[scope="col"]').first()).toBeVisible();
  expect(await firstTable.locator("tbody tr").count()).toBeGreaterThanOrEqual(2);

  // Confirm the first (allergy) issue.
  const first = articles.nth(0);
  const firstTitle = (await first.locator("h3").textContent()) ?? "";
  await first.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByRole("status")).toContainText("Issue confirmed");
  await expect(articles.nth(0).getByTestId("issue-status")).toHaveText("confirmed");

  // Dismiss the second issue with a reason.
  const second = articles.nth(1);
  const secondTitle = (await second.locator("h3").textContent()) ?? "";
  await second.getByLabel("Reason for dismissing").fill("Synthetic demo: reviewed, intended by team");
  await second.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByRole("status")).toContainText("Issue dismissed");
  await expect(articles.nth(1).getByTestId("issue-status")).toHaveText("dismissed");

  // Reload: run id is in the URL; statuses come back from the append-only decision rows.
  await page.reload();
  await expect(page.getByRole("status")).toContainText("Saved run loaded");
  const byTitle = (title: string) => page.locator("ol.issue-list article").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(byTitle(firstTitle).getByTestId("issue-status")).toHaveText("confirmed");
  await expect(byTitle(secondTitle).getByTestId("issue-status")).toHaveText("dismissed");
});

test("dismiss without a reason is blocked in the UI", async ({ page }) => {
  await runDemo(page);
  const last = page.locator("ol.issue-list > li > article").last();
  await last.getByRole("button", { name: "Dismiss" }).click();
  await expect(last.getByRole("alert")).toContainText("A reason is required");
  await expect(last.getByTestId("issue-status")).toHaveText("open");
});

test("nurse gets the 403 page on /pharmacist/reconcile", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/pharmacist/reconcile");
  await expect(page.getByTestId("forbidden")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("403");
});
