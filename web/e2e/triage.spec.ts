import { expect, test, type Page } from "@playwright/test";

import { login } from "./helpers";

async function assessCase(page: Page, caseRef: string) {
  await login(page, "nurse");
  await page.goto("/nurse/triage");
  await page.getByRole("button", { name: `Assess ${caseRef}` }).click();
  await expect(page).toHaveURL(/\/nurse\/triage\/[0-9a-f]{32}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(caseRef);
}

test("red-flag case: alerts above ranking, confirm blocked until acknowledged, then confirmed", async ({ page }) => {
  await assessCase(page, "SYN-S4-002");
  const alerts = page.getByTestId("alerts-section");
  const dept = page.getByTestId("department-section");
  await expect(alerts).toBeVisible();
  await expect(alerts).toHaveAttribute("role", "alert");
  await expect(page.getByTestId("department-ranking")).toBeVisible();
  const [a, d] = [await alerts.boundingBox(), await dept.boundingBox()];
  expect(a && d && a.y < d.y).toBeTruthy();
  const domOrder = await page.evaluate(() => {
    const x = document.querySelector('[data-testid="alerts-section"]')!;
    const y = document.querySelector('[data-testid="department-section"]')!;
    return !!(x.compareDocumentPosition(y) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(domOrder).toBe(true);
  await expect(page.getByText("Suggestion for nurse review").first()).toBeVisible();

  const confirm = page.getByRole("button", { name: "Confirm department" });
  await expect(confirm).toBeDisabled();
  for (const rule of ["RF-CHEST", "RF-HR", "RF-SBP"]) {
    await page.getByLabel(`I have seen alert ${rule}`).check();
  }
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByTestId("review-result")).toContainText("Confirmed department: Cardiology");
});

test("abstained case shows the missing list and supports a manual edit", async ({ page }) => {
  await assessCase(page, "SYN-S4-023");
  await expect(page.getByTestId("missing-information")).toContainText("vitals.spo2");
  await expect(page.getByTestId("department-ranking")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Confirm department" })).toHaveCount(0);
  await page.getByLabel("Choose another department").selectOption("ORTHO");
  await page.getByLabel("Reason for the change").fill("Knee injury; manual choice by nurse");
  await page.getByRole("button", { name: "Save edited department" }).click();
  await expect(page.getByTestId("review-result")).toContainText("Orthopedics");
});

test("red-flag review works with the keyboard alone", async ({ page }) => {
  await assessCase(page, "SYN-S4-001");
  const ack = page.getByLabel("I have seen alert RF-CHEST");
  await ack.focus();
  await page.keyboard.press("Space");
  await expect(ack).toBeChecked();
  const confirm = page.getByRole("button", { name: "Confirm department" });
  for (let i = 0; i < 20 && !(await confirm.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(confirm).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("review-result")).toContainText("Confirmed department");
});
