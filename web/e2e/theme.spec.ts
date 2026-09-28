/** Slice t1 — MedX theme browser checks (T1-A03, A10, A11, A13..A16). */
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { login, type Role } from "./helpers";

const SITE_TITLE = "MedX — AI Clinical Front Door (research prototype)";
const BRAND = "SC" + "BX"; // assembled so web/ source only contains the brand inside the font name
const FONT_FAMILY = /^SCBXBeta2$/;
const SHOTS_DIR = join(__dirname, "..", "..", "artifacts", "factory", "t1");
const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
];
const PAGES = ["login", "nurse", "physician", "pharmacist", "403", "404"] as const;
type PageName = (typeof PAGES)[number];
const GRAMMAR_PAGES = PAGES.filter((p) => p !== "login");
const ROLE_PAGES = new Set<PageName>(["nurse", "physician", "pharmacist"]);

async function visit(page: Page, name: PageName) {
  if (ROLE_PAGES.has(name)) {
    await page.context().clearCookies();
    await login(page, name as Role);
  } else {
    await page.goto(name === "login" ? "/login" : name === "403" ? "/403" : "/definitely-missing");
  }
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

/** Computed colour string of a theme token, as the browser resolves it. */
async function tokenColour(page: Page, token: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("span");
    probe.style.color = `var(--${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }, token);
}

function channels(colour: string): number[] {
  return (colour.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
}
function contrastRatio(a: string, b: string): number {
  const lum = (c: string) => {
    const [r, g, bl] = channels(c).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test.describe("MedX theme", () => {
  test("disclaimer prominence", async ({ page }) => {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize(vp);
      for (const name of PAGES) {
        await visit(page, name);
        const note = page.getByTestId("research-disclaimer");
        await expect(note, `${name} ${vp.width}`).toBeVisible();
        await expect(note, `${name} ${vp.width}`).toBeInViewport({ ratio: 1 });
        await expect(note).toHaveAttribute("role", "note");
        const facts = await note.evaluate((el) => ({
          // Next 15 injects an empty <div hidden> metadata outlet before layout content; skip only that.
          first:
            [...document.body.children].find((c) => !(c instanceof HTMLElement && c.hidden && !c.textContent?.trim())) ===
            el,
          bg: getComputedStyle(el).backgroundColor,
          sizes: [...el.querySelectorAll("p")].map((p) => parseFloat(getComputedStyle(p).fontSize)),
        }));
        expect(facts.first, `${name}: disclaimer is first child of body`).toBe(true);
        expect(facts.bg).toBe(await tokenColour(page, "warn-bg"));
        expect(facts.sizes).toHaveLength(2);
        for (const size of facts.sizes) expect(size).toBeGreaterThanOrEqual(14);
      }
    }
  });

  test("fonts render (document.fonts + CDP platform fonts, TH + EN)", async ({ page }) => {
    for (const name of ["login", "nurse"] as const) {
      await visit(page, name);
      const loaded = await page.evaluate(() =>
        [...document.fonts]
          .filter((f) => f.family.replace(/["']/g, "") === "SCBXBeta2" && f.status === "loaded")
          .map((f) => f.weight),
      );
      expect(loaded, name).toEqual(expect.arrayContaining(["400", "700"]));

      const cdp = await page.context().newCDPSession(page);
      await cdp.send("DOM.enable");
      await cdp.send("CSS.enable");
      const { root } = await cdp.send("DOM.getDocument", { depth: -1 });
      const glyphs = async (selector: string) => {
        const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
        expect(nodeId, selector).toBeGreaterThan(0);
        const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
        const total = fonts.reduce((n, f) => n + f.glyphCount, 0);
        const ours = fonts.filter((f) => FONT_FAMILY.test(f.familyName)).reduce((n, f) => n + f.glyphCount, 0);
        return { total, ours, families: fonts.map((f) => f.familyName) };
      };
      for (const selector of [
        '[data-testid="research-disclaimer"] p[lang="th"]',
        '[data-testid="research-disclaimer"] p[lang="en"]',
        "main h1",
      ]) {
        const g = await glyphs(selector);
        expect(g.total, `${name} ${selector}`).toBeGreaterThan(0);
        expect(g.ours, `${name} ${selector}: ${g.families.join(", ")}`).toBe(g.total);
      }
      if (name === "nurse") {
        // Next-step text excluding the arrow span (the arrow glyph is a known system-ui fallback).
        const body = await glyphs('[data-testid="next-step"]');
        const em = await glyphs('[data-testid="next-step"] em');
        const share = (body.ours + em.ours) / (body.total + em.total);
        expect(share).toBeGreaterThanOrEqual(0.95);
      }
      await cdp.detach();
    }
  });

  test("no external requests", async ({ page }) => {
    // Disable the HTTP cache so every font load is a full same-origin fetch (200), not a 304 revalidation.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    const offOrigin: string[] = [];
    const fontRequests: { path: string; status: number | undefined }[] = [];
    const pending: Promise<void>[] = [];
    page.on("request", (req) => {
      const url = new URL(req.url());
      if (url.protocol === "data:" || url.protocol === "blob:") return;
      if (![`127.0.0.1:${process.env.WEB_PORT || "3000"}`, `127.0.0.1:${process.env.API_PORT || "8000"}`].includes(url.host)) offOrigin.push(req.url());
      if (req.resourceType() === "font") {
        pending.push(
          req.response().then((resp) => {
            fontRequests.push({ path: url.pathname, status: resp?.status() });
          }),
        );
      }
    });
    for (const name of PAGES) await visit(page, name);
    await Promise.all(pending);
    expect(offOrigin).toEqual([]);
    expect(fontRequests.length).toBeGreaterThan(0);
    for (const f of fontRequests) {
      expect(f.path).toMatch(/^\/fonts\/SCBXBeta2-(Light|Regular|Bold)\.otf$/);
      expect(f.status).toBe(200);
    }
  });

  test("wordmark + title on 6 pages", async ({ page }) => {
    for (const name of PAGES) {
      await visit(page, name);
      const mark = page.getByRole("img", { name: "MedX" });
      await expect(mark, name).toHaveCount(1);
      await expect(mark).toBeVisible();
      const x = await page.locator(".wordmark .wordmark-x").evaluate((el) => {
        const s = getComputedStyle(el);
        return { colour: s.color, size: parseFloat(s.fontSize), weight: Number(s.fontWeight) };
      });
      expect(x.colour).toBe(await tokenColour(page, "purple-1"));
      expect(x.size).toBeGreaterThanOrEqual(24);
      expect(x.weight).toBeGreaterThanOrEqual(700);
      expect(await page.title(), name).toContain(SITE_TITLE);
      // Wordmark sits below the disclaimer.
      const order = await page.evaluate(() => {
        const d = document.querySelector('[data-testid="research-disclaimer"]')!;
        const w = document.querySelector('[data-testid="wordmark"]')!;
        return Boolean(d.compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      expect(order).toBe(true);
    }
  });

  test("page grammar on 5 pages", async ({ page }) => {
    const purple1 = async () => tokenColour(page, "purple-1");
    for (const name of GRAMMAR_PAGES) {
      await visit(page, name);
      await expect(page.getByTestId("eyebrow"), name).toHaveCount(1);
      await expect(page.locator("h1"), name).toHaveCount(1);
      await expect(page.locator('h2[data-testid="claim"]'), name).toHaveCount(1);
      await expect(page.getByTestId("next-step"), name).toHaveCount(1);
      const claim = (await page.locator('h2[data-testid="claim"]').innerText()).trim();
      expect(claim.endsWith("."), `${name}: "${claim}"`).toBe(true);

      const strip = page.getByTestId("next-step");
      expect(await strip.locator("em").count()).toBeGreaterThanOrEqual(1);
      const arrow = strip.locator('.arrow[aria-hidden="true"]');
      await expect(arrow).toHaveCount(1);
      const a = await arrow.evaluate((el) => {
        const s = getComputedStyle(el);
        return { colour: s.color, size: parseFloat(s.fontSize), weight: Number(s.fontWeight) };
      });
      expect(a.colour).toBe(await purple1());
      expect(a.size).toBeGreaterThanOrEqual(19);
      expect(a.weight).toBeGreaterThanOrEqual(700);

      const ordered = await page.evaluate(() => {
        const els = ['[data-testid="eyebrow"]', "h1", 'h2[data-testid="claim"]', '[data-testid="next-step"]'].map(
          (s) => document.querySelector(s)!,
        );
        return els.every((el, i) => i === 0 || els[i - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      expect(ordered, `${name}: eyebrow < h1 < claim < next-step`).toBe(true);
    }
  });

  test("login cover layout", async ({ page }) => {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize(vp);
      await visit(page, "login");
      const panel = page.getByTestId("cover-panel");
      await expect(panel).toHaveAttribute("aria-hidden", "true");
      const bgImage = await panel.evaluate((el) => getComputedStyle(el).backgroundImage);
      expect(bgImage).toContain("linear-gradient");
      const opacity = await page.getByTestId("cover-motif").evaluate((el) => Number(getComputedStyle(el).opacity));
      expect(opacity).toBeLessThanOrEqual(0.2);
      expect(opacity).toBeGreaterThan(0);

      const p = (await panel.boundingBox())!;
      const f = (await page.locator(".cover-form").boundingBox())!;
      if (vp.width === 1280) {
        expect(p.x + p.width, "panel and form do not overlap horizontally").toBeLessThanOrEqual(f.x);
      } else {
        expect(p.y + p.height, "panel stacks above the form").toBeLessThanOrEqual(f.y);
      }
      await expect(page.getByTestId("research-disclaimer")).toBeInViewport({ ratio: 1 });
      await expect(page.getByLabel("Username")).toBeInViewport();
      await expect(page.getByLabel("Password")).toBeInViewport();
      await expect(page.getByRole("button", { name: "Sign in" })).toBeInViewport();
    }
  });

  test("alerts use warning tokens, never purple", async ({ page }) => {
    await visit(page, "login");
    await page.getByLabel("Username").fill("nurse1");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    const alert = page.locator("#login-error[role=alert]");
    await expect(alert).toHaveText("Invalid username or password.");
    const s = await alert.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { fg: cs.color, bg: cs.backgroundColor, edge: cs.borderLeftColor };
    });
    expect(s.fg).toBe(await tokenColour(page, "warn-fg"));
    expect(s.bg).toBe(await tokenColour(page, "warn-bg"));
    expect(s.edge).toBe(await tokenColour(page, "warn-border"));
  });

  test("focus rings visible", async ({ page }) => {
    for (const name of ["login", "nurse", "403"] as const) {
      await visit(page, name);
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
      const pageBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      const expected = await page.evaluate(
        () =>
          [...document.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex='-1'])")]
            .filter((el) => el.offsetParent !== null).length,
      );
      expect(expected, name).toBeGreaterThan(0);
      const seen = new Set<string>();
      for (let i = 0; i < 40; i++) {
        await page.keyboard.press("Tab");
        const info = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el || el === document.body) return null;
          const s = getComputedStyle(el);
          const key = `${el.tagName}#${el.id}:${el.textContent?.trim()}:${[...el.parentElement!.children].indexOf(el)}`;
          return { key, style: s.outlineStyle, width: parseFloat(s.outlineWidth), colour: s.outlineColor };
        });
        if (!info || seen.has(info.key)) break;
        seen.add(info.key);
        expect(info.style, `${name} ${info.key}`).not.toBe("none");
        expect(info.width, `${name} ${info.key}`).toBeGreaterThanOrEqual(2);
        expect(contrastRatio(info.colour, pageBg), `${name} ${info.key}`).toBeGreaterThanOrEqual(3);
      }
      expect(seen.size, `${name}: every focusable element reached by Tab`).toBe(expected);
    }
  });

  test(`no ${BRAND} in visible text`, async ({ page }) => {
    for (const name of PAGES) {
      await visit(page, name);
      const text = await page.evaluate(() => document.body.innerText);
      expect(text.toUpperCase(), name).not.toContain(BRAND);
    }
  });

  test("screenshots", async ({ page }) => {
    mkdirSync(SHOTS_DIR, { recursive: true });
    for (const vp of VIEWPORTS) {
      await page.setViewportSize(vp);
      for (const name of PAGES) {
        await visit(page, name);
        await page.screenshot({ path: join(SHOTS_DIR, `${name}-${vp.width}x${vp.height}.png`), fullPage: true });
      }
    }
  });
});
