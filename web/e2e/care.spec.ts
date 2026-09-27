import { expect, test, type Page } from "@playwright/test";

import { login } from "./helpers";

// Dev-split synthetic cases (seed 20260926): SYNE-0011 T2 has vitals alerts (RF-CONSC, RF-QSOFA) and a suggestion;
// SYNE-0071 abstains (duration, allergy_status missing).
async function assessCase(page: Page, caseId: string, dp: "T1" | "T2") {
  await login(page, "physician");
  await page.goto("/physician/care");
  await page.getByRole("button", { name: `Assess ${caseId} at ${dp}` }).click();
  await expect(page).toHaveURL(/\/physician\/care\/[0-9a-f]{32}$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(caseId);
}

test("vitals alert case: red-flag region above suggestions, confirm blocked until acknowledged, then confirmed", async ({
  page,
}) => {
  await assessCase(page, "SYNE-0011", "T2");
  const red = page.getByTestId("redflag-section");
  const sugg = page.getByTestId("suggestion-section");
  await expect(page.getByTestId("alerts")).toHaveAttribute("role", "alert");
  await expect(page.getByTestId("screening-banner")).toContainText("RED-FLAG SCREENING INCOMPLETE");
  await expect(page.getByTestId("next-information")).toBeVisible();
  const [a, s] = [await red.boundingBox(), await sugg.boundingBox()];
  expect(a && s && a.y < s.y).toBeTruthy();
  const domOrder = await page.evaluate(() => {
    const x = document.querySelector('[data-testid="redflag-section"]')!;
    const y = document.querySelector('[data-testid="suggestion-section"]')!;
    return !!(x.compareDocumentPosition(y) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(domOrder).toBe(true);
  await expect(page.getByText("Suggestion for physician review — research prototype").first()).toBeVisible();

  const confirm = page.getByRole("button", { name: "Confirm suggestion" });
  await expect(confirm).toBeDisabled();
  for (const rule of ["RF-CONSC", "RF-QSOFA"]) await page.getByLabel(`I have seen alert ${rule}`).check();
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/I have seen that red-flag screening incomplete/).check();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByTestId("review-result")).toContainText("Confirmed: next information NI-LAB-LACTATE");
  const confirmed = await page.request.get("/api/care/cases/SYNE-0011/confirmed");
  expect(confirmed.status()).toBe(200);
});

test("abstained case shows the exact missing list, no suggestions, and supports edit", async ({ page }) => {
  await assessCase(page, "SYNE-0071", "T1");
  await expect(page.getByTestId("abstained")).toBeVisible();
  await expect(page.getByTestId("missing-information").locator("li")).toHaveText(["duration", "allergy_status"]);
  await expect(page.getByTestId("next-information")).toHaveCount(0);
  await expect(page.getByTestId("pathway-options")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Confirm suggestion" })).toHaveCount(0);
  await page.getByLabel(/I have seen that red-flag screening incomplete/).check();
  await page.getByLabel(/Repeat full set of vital signs/).check();
  await page.getByLabel("Reason for the edit").fill("Collect the missing history first");
  await page.getByRole("button", { name: "Save edited suggestion" }).click();
  await expect(page.getByTestId("review-result")).toContainText("Edited: next information NI-OBS-REPEAT-VITALS");
});

test("abstained case supports reject", async ({ page }) => {
  await assessCase(page, "SYNE-0089", "T2");
  await page.getByLabel(/I have seen that red-flag screening incomplete/).check();
  await page.getByLabel("Reason for rejecting").fill("Not useful yet");
  await page.getByRole("button", { name: "Reject suggestion" }).click();
  await expect(page.getByTestId("review-result")).toContainText("Suggestion rejected");
});

test("care review works with the keyboard alone", async ({ page }) => {
  await assessCase(page, "SYNE-0030", "T2");
  for (const label of ["I have seen alert RF-SPO2", /I have seen that red-flag screening incomplete/]) {
    const box = page.getByLabel(label);
    await box.focus();
    await page.keyboard.press("Space");
    await expect(box).toBeChecked();
  }
  const confirm = page.getByRole("button", { name: "Confirm suggestion" });
  for (let i = 0; i < 20 && !(await confirm.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(confirm).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("review-result")).toContainText("Confirmed");
});

test("a nurse cannot open the care pages (pharmacist: backend role matrix)", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/physician/care");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("403");
  const resp = await page.request.get("/api/care/cases");
  expect(resp.status()).toBe(403);
});
