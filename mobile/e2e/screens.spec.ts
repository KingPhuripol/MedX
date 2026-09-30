/** V2C-C2: 11 comp states x 2 viewports -> artifacts/factory/v2c/screens/<state>-<w>x<h>.png (production build). */
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import config from "../tests/fixtures/realtime-config.json";

import { completeFlow, loginState, mainFlow, redFlagFlow, type Visit } from "./flows";
import { login, setup } from "./harness";

const OUT = resolve(__dirname, "../../artifacts/factory/v2c/screens");
mkdirSync(OUT, { recursive: true });

async function checkLayout(page: Page) {
  // No horizontal scroll; safety text never ellipsised.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const clipped = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>(".alarm *, .slot *, .notice *, .limit")].filter(
      (el) => getComputedStyle(el).textOverflow === "ellipsis",
    ).length,
  );
  expect(clipped).toBe(0);
}

const shoot: Visit = async (state, page) => {
  await page.evaluate(() => document.fonts.ready);
  await checkLayout(page);
  const { width, height } = page.viewportSize()!;
  await page.screenshot({ path: `${OUT}/${state}-${width}x${height}.png`, animations: "disabled" });
  const full = await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight);
  if (full && state.startsWith("review")) {
    await page.addStyleTag({ content: ".bar{position:static}" });
    await page.screenshot({ path: `${OUT}/${state}-${width}x${height}-full.png`, fullPage: true, animations: "disabled" });
    await page.addStyleTag({ content: ".bar{position:sticky}" });
  }
};

test("login", async ({ page }) => loginState(page, shoot));
test("start, idle, recording, paused, reconnecting, error", async ({ page }) => {
  const api = await mainFlow(page, shoot);
  expect(api.foreign).toEqual([]);
});
test("redflag", async ({ page }) => {
  const api = await redFlagFlow(page, shoot);
  expect(api.foreign).toEqual([]);
});
test("complete, review, review-ready + not-yet-connected variant", async ({ page }, info) => {
  const api = await completeFlow(page, shoot);
  if (info.project.name === "390x844") {
    await page.getByRole("button", { name: "ยืนยันและส่งเข้าเคส" }).click();
    await expect(page.getByText("ยังส่งเข้าเคสไม่ได้")).toBeVisible();
    await expect(page.getByText("ส่งเข้าเคสแล้ว")).toHaveCount(0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await shoot("review-not-connected", page);
  }
  expect(api.foreign).toEqual([]);
});
test("access-code variant", async ({ page }, info) => {
  test.skip(info.project.name !== "390x844", "variant is 390x844 only");
  await setup(page, { config: { ...config, access_code_required: true } });
  await login(page);
  await expect(page.getByLabel("รหัสเข้าใช้บันทึกเสียง")).toBeVisible();
  await shoot("start-access-code", page);
});
