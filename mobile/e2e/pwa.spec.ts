/** V2C-C11 PWA: manifest + icons on the production build; the service worker registers and never caches. */
import { expect, test } from "@playwright/test";

import { setup } from "./harness";

test.use({ serviceWorkers: "allow" });

test("manifest, icons and a registered no-cache service worker", async ({ page, request }, info) => {
  test.skip(info.project.name !== "390x844", "viewport-independent");
  await setup(page);
  await page.goto("/");
  const href = await page.getAttribute('link[rel="manifest"]', "href");
  expect(href).toBe("/manifest.webmanifest");

  const m = await (await request.get(href!)).json();
  expect(m).toMatchObject({ lang: "th", start_url: "/", scope: "/", display: "standalone", orientation: "portrait" });
  expect(m.name).toBeTruthy();
  expect(m.short_name).toBeTruthy();
  const want = ["192x192 any", "512x512 any", "512x512 maskable"];
  expect(m.icons.map((i: { sizes: string; purpose?: string }) => `${i.sizes} ${i.purpose ?? "any"}`).sort()).toEqual(want);
  for (const icon of m.icons as { src: string; sizes: string }[]) {
    const png = await (await request.get(icon.src)).body();
    const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)]; // PNG IHDR
    expect(`${w}x${h}`).toBe(icon.sizes);
  }

  const reg = await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    return !!(await navigator.serviceWorker.getRegistration());
  });
  expect(reg).toBe(true);
  const sw = await (await request.get("/sw.js")).text();
  expect(sw).not.toMatch(/caches|cache\.put|\/api|addEventListener\(["']fetch/);
  expect(await page.evaluate(async () => (await caches.keys()).length)).toBe(0);
});
