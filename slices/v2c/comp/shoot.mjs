// Render every comp at 390x844 (DPR 2) into png/. Run from any web/ checkout that has playwright:
//   cd web && node ../slices/v2c/comp/shoot.mjs
import { createRequire } from "node:module";
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(process.cwd() + "/")("playwright");
const dir = dirname(fileURLToPath(import.meta.url));
const pages = readdirSync(dir).filter((f) => f.endsWith(".html")).sort();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
for (const f of pages) {
  await page.goto("file://" + join(dir, f));
  await page.evaluate(() => document.fonts.ready);
  const name = f.replace(".html", "");
  await page.screenshot({ path: join(dir, "png", name + ".png") });
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  if (h > 844) {
    // Full-page capture: unstick the review bar so it sits at the end, as it would after scrolling.
    await page.addStyleTag({ content: ".bar{position:static}" });
    await page.screenshot({ path: join(dir, "png", name + "-full.png"), fullPage: true });
  }
  const bad = await page.evaluate(() => [...document.fonts].filter((x) => x.status === "error").length);
  console.log(name, "height", h, "fontErrors", bad);
}
await browser.close();
