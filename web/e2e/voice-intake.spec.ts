import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

import { login } from "./helpers";

interface FixtureTurn {
  turn_id: string;
  speaker: string;
  text: string;
}

// Synthetic fixture 01 (hand-written script; no real patient).
const fixture = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../backend/tests/voice/fixtures/th_intake_01.json"), "utf-8"),
) as { turns: FixtureTurn[] };
const patientTurns = fixture.turns.filter((t) => t.speaker !== "agent");

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

async function tabTo(page: Page, name: string) {
  const target = page.getByRole("button", { name });
  await expect(target).toBeVisible();
  for (let i = 0; i < 40 && !(await target.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

test("nurse runs a synthetic Thai intake end to end with the keyboard only", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/nurse/intake");
  await expect(page.getByTestId("research-disclaimer")).toBeVisible();

  const refInput = page.getByLabel("Synthetic patient ref");
  await refInput.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("SYN-S3-E2E");
  await page.keyboard.press("Enter");

  const question = page.getByRole("status");
  await expect(question).toHaveText("วันนี้มีอาการอะไรมาคะ");
  expect(await seriousViolations(page)).toEqual([]);

  const rows = page.getByTestId("fact-row");
  for (const [i, turn] of patientTurns.entries()) {
    const before = (await question.textContent()) ?? "";
    await expect(page.getByLabel("Turn text")).toBeFocused();
    await page.keyboard.type(turn.text);
    await page.keyboard.press("Enter");
    await expect(question).not.toHaveText(before);
    await expect(rows).toHaveCount(i + 1);
    const row = rows.nth(i);
    await expect(row).toContainText("KNOWN");
    await expect(row.getByTestId("source-link")).toHaveAttribute("href", /^#turn-/);
    await expect(row.locator("time")).toHaveAttribute("datetime", /\d{4}-\d{2}-\d{2}T/);
  }

  await expect(page.getByTestId("handoff-banner")).toContainText("All intake fields answered");
  await expect(page.getByTestId("missing-list")).toContainText("None missing");
  expect(await seriousViolations(page)).toEqual([]);

  await tabTo(page, "Finish intake");
  await page.keyboard.press("Enter");
  const summary = page.getByTestId("intake-summary");
  await expect(summary).toContainText("Handoff reason: All intake fields answered");
  await expect(summary).toContainText("Missing fields: none");
  await expect(summary).toContainText("Evidence items recorded: 7");
  await expect(page.getByTestId("research-disclaimer")).toBeVisible();
  expect(await seriousViolations(page)).toEqual([]);
});

test("finishing early lists the MISSING fields", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/nurse/intake");
  await page.getByLabel("Synthetic patient ref").fill("SYN-S3-E2E-EARLY");
  await page.getByRole("button", { name: "Start intake" }).click();
  await page.getByLabel("Turn text").fill("ปวดหัวค่ะ");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("fact-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Finish intake" }).click();
  const summary = page.getByTestId("intake-summary");
  await expect(summary).toContainText("Finished by nurse");
  await expect(summary).toContainText("Drug allergy status");
  await expect(page.getByTestId("missing-list")).toContainText("Drug allergy status");
});

test("physician sees the 403 page on /nurse/intake", async ({ page }) => {
  await login(page, "physician");
  await page.goto("/nurse/intake");
  await expect(page.getByTestId("forbidden")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("403");
  await expect(page.getByLabel("Synthetic patient ref")).toHaveCount(0);
});
