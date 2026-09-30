/** V2C-C11 motion + V2C-C5 computed style: reduced motion freezes the meter and loaders; safety states never animate. */
import { expect, test, type Page } from "@playwright/test";

import { mainFlow, redFlagFlow, type Visit } from "./flows";

/** A fake Web Audio analyser with a changing level, so the meter has something to animate. */
const FAKE_AUDIO = () => {
  let n = 0;
  class FakeCtx {
    createAnalyser() {
      return {
        fftSize: 512,
        getByteTimeDomainData(buf: Uint8Array) {
          n += 1;
          buf.fill(128 + 8 * (n % 6)); // varying level across the 0..1 range, so the bars visibly move
        },
      };
    }
    createMediaStreamSource() {
      return { connect() {} };
    }
    close() {
      return Promise.resolve();
    }
  }
  (window as unknown as { AudioContext: unknown }).AudioContext = FakeCtx;
};

const meterTransforms = (page: Page) =>
  page.evaluate(() => [...document.querySelectorAll<HTMLElement>("[data-testid=meter] i")].map((i) => i.style.transform).join("|"));

const noMotion = (page: Page, sel: string) =>
  page.evaluate((sel) => {
    return [...document.querySelectorAll(`${sel}, ${sel} *`)]
      .map((el) => getComputedStyle(el))
      .filter((cs) => cs.animationName !== "none" || cs.transitionDuration.split(",").some((d) => parseFloat(d) > 0)).length;
  }, sel);

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("level meter is static and loaders do not rotate", async ({ page }) => {
    await page.addInitScript(FAKE_AUDIO);
    const seen: Record<string, boolean> = {};
    const visit: Visit = async (state, p) => {
      if (state === "recording") {
        const a = await meterTransforms(p);
        await p.clock.fastForward(500);
        expect(await meterTransforms(p)).toBe(a);
        seen.recording = true;
      }
      if (state === "reconnecting") {
        const spins = await p.evaluate(() =>
          [...document.querySelectorAll(".spin")].map((el) => {
            const cs = getComputedStyle(el);
            return cs.animationName === "none" || parseFloat(cs.animationDuration) === 0;
          }),
        );
        expect(spins.length).toBeGreaterThan(0);
        expect(spins.every(Boolean)).toBe(true);
        seen.reconnecting = true;
      }
    };
    await mainFlow(page, visit);
    expect(seen).toEqual({ recording: true, reconnecting: true });
  });
});

test("control: without reduced motion the meter follows the input level", async ({ page }, info) => {
  test.skip(info.project.name !== "390x844", "one viewport is enough for the control");
  await page.addInitScript(FAKE_AUDIO);
  let moved = false;
  await mainFlow(page, async (state, p) => {
    if (state !== "recording") return;
    const a = await meterTransforms(p);
    await p.clock.fastForward(500);
    const b = await meterTransforms(p);
    moved = b !== a;
  });
  expect(moved).toBe(true);
});

test("red-flag alert appears with no animation or transition (C5)", async ({ page }) => {
  await redFlagFlow(page, async (state, p) => {
    if (state !== "redflag") return;
    expect(await noMotion(p, "[role=alert]")).toBe(0);
    expect(await p.evaluate(() => document.activeElement?.closest("[role=alert]") !== null && document.activeElement?.tagName)).toBe("H2");
  });
});
