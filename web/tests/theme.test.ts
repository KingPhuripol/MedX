// @vitest-environment node
/** Slice t1 — MedX theme checks (T1-A05..A09, A12, A13). Pure file/CSS analysis, no network. */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const WEB = fileURLToPath(new URL("../", import.meta.url));
const THEME = readFileSync(join(WEB, "app", "theme.css"), "utf8");
// Brand name assembled at runtime so this file passes its own brand-name scan (T1-A12).
const BRAND = "SC" + "BX";
const SKIP_DIRS = new Set(["node_modules", ".next", "test-results", "playwright-report"]);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}
const rel = (p: string) => relative(WEB, p).split(sep).join("/");
const ALL_FILES = walk(WEB);
const SOURCE_FILES = ALL_FILES.filter((p) => /\.(css|ts|tsx|mjs)$/.test(p));

// Expected hex values written without "#" so this file passes the no-hard-coded-colour scan.
const EXPECTED_TOKENS: Record<string, string> = {
  "grey-1": "E6E8E8",
  "grey-2": "D6DADB",
  "grey-3": "AEB3B4",
  "grey-4": "606769",
  "grey-5": "363F42",
  "grey-6": "212628",
  "grey-7": "15191A",
  "purple-1": "8F47BF",
  "purple-2": "6C2993",
  "purple-3": "3C1D5D",
  white: "FFFFFF",
  "warn-bg": "FFF4CE",
  "warn-border": "8A6D00",
};

function parseTokens(css: string): Record<string, string> {
  const root = css.match(/:root\s*{([^}]*)}/);
  if (!root) throw new Error("theme.css has no :root block");
  const tokens: Record<string, string> = {};
  for (const m of root[1].matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) tokens[m[1]] = m[2].trim();
  return tokens;
}
const TOKENS = parseTokens(THEME);

function resolveHex(name: string): string {
  let value = TOKENS[name];
  for (let i = 0; i < 5 && value?.startsWith("var("); i++) value = TOKENS[value.slice(6, -1)];
  if (!value || !/^#[0-9a-fA-F]{6}$/.test(value)) throw new Error(`token --${name} does not resolve to a hex colour`);
  return value;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function contrast(fg: string, bg: string): number {
  const [a, b] = [luminance(resolveHex(fg)), luminance(resolveHex(bg))].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

// [use, foreground token, background token, required ratio] — from slices/t1/SPEC.md.
const PAIRS: [string, string, string, number][] = [
  ["body/h1/claim/em/wordmark Med", "grey-7", "grey-1", 4.5],
  ["secondary text, next-step body", "grey-5", "grey-1", 4.5],
  ["muted meta text", "grey-4", "grey-1", 4.5],
  ["eyebrow label, links", "purple-2", "grey-1", 4.5],
  ["wordmark X (large text)", "purple-1", "grey-1", 3],
  ["next-step arrow (large, decorative)", "purple-1", "grey-1", 3],
  ["primary button label", "white", "purple-2", 4.5],
  ["primary button hover", "white", "purple-3", 4.5],
  ["secondary button label", "grey-7", "white", 4.5],
  ["disabled button label", "white", "grey-4", 4.5],
  ["input text", "grey-7", "white", 4.5],
  ["input border (non-text)", "grey-4", "white", 3],
  ["focus ring on grey-1 (non-text)", "purple-2", "grey-1", 3],
  ["focus ring on white (non-text)", "purple-2", "white", 3],
  ["disclaimer and alert text", "warn-fg", "warn-bg", 4.5],
  ["disclaimer border (non-text)", "warn-border", "warn-bg", 3],
  ["cover text on lightest stop", "white", "purple-2", 4.5],
  ["cover sub text on lightest stop", "grey-1", "purple-2", 4.5],
  ["cover text on darkest stop", "white", "grey-7", 4.5],
];
const FORBIDDEN_NORMAL_TEXT: [string, string][] = [
  ["purple-1", "grey-1"],
  ["purple-1", "grey-2"],
  ["grey-4", "grey-2"],
  ["purple-1", "grey-7"],
];

const NAMED_COLOURS =
  "black|white|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|maroon|navy|teal|olive|lime|aqua|fuchsia|brown|gold|indigo|violet|cyan|magenta|beige|crimson|coral|salmon|tomato|khaki|ivory|lavender|tan|turquoise";
const COLOUR_PROPS =
  "color|background|background-color|background-image|border|border-(?:top|right|bottom|left)(?:-color)?|border-color|outline|outline-color|fill|stroke|box-shadow|text-shadow|caret-color|accent-color|text-decoration-color|scrollbar-color|backgroundColor|borderColor|outlineColor";
const NAMED_IN_PROP = new RegExp(`(?:^|[\\s{;,"'])(?:${COLOUR_PROPS})\\s*:\\s*["']?[^;}\\n]*?\\b(?:${NAMED_COLOURS})\\b`, "i");

function colourViolations(path: string, text: string): string[] {
  const out: string[] = [];
  const noVars = text.replace(/var\(--[a-z0-9-]+\)/gi, "var()");
  for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/]) {
    const m = text.match(re);
    if (m) out.push(`${rel(path)}: ${m[0]}`);
  }
  const named = noVars.match(NAMED_IN_PROP);
  if (named) out.push(`${rel(path)}: named colour in "${named[0].trim()}"`);
  return out;
}

describe("MedX theme", () => {
  it("tokens exact", () => {
    for (const [name, hex] of Object.entries(EXPECTED_TOKENS)) {
      expect(TOKENS[name]?.toUpperCase(), `--${name}`).toBe(`#${hex}`);
    }
    expect(TOKENS["warn-fg"]).toBe("var(--grey-7)");
    expect(TOKENS.type).toBe('"SCBXBeta2", system-ui, sans-serif');
    const layout = readFileSync(join(WEB, "app", "layout.tsx"), "utf8");
    const themeAt = layout.indexOf('import "./theme.css"');
    const globalsAt = layout.indexOf('import "./globals.css"');
    expect(themeAt).toBeGreaterThan(-1);
    expect(globalsAt).toBeGreaterThan(themeAt);
  });

  it("contrast pairs meet AA", () => {
    const failures = PAIRS.map(([use, fg, bg, min]) => ({ use, ratio: contrast(fg, bg), min })).filter(
      (p) => p.ratio < p.min,
    );
    expect(failures).toEqual([]);
    // Spec reference values (rounded) guard against silent token drift.
    expect(contrast("grey-7", "grey-1")).toBeCloseTo(14.4, 1);
    expect(contrast("purple-1", "grey-1")).toBeCloseTo(4.47, 1);
    expect(contrast("warn-fg", "warn-bg")).toBeCloseTo(16.09, 1);
    // The forbidden pairs really are below 4.5 (so they must stay large-text/non-text only).
    for (const [fg, bg] of FORBIDDEN_NORMAL_TEXT) expect(contrast(fg, bg)).toBeLessThan(4.5);
  });

  it("no hard-coded colours outside theme.css", () => {
    const scanned = SOURCE_FILES.filter((p) => {
      const r = rel(p);
      return r !== "app/theme.css" && !r.startsWith("public/fonts/") && r !== "package-lock.json";
    });
    expect(scanned.length).toBeGreaterThan(10);
    const violations = scanned.flatMap((p) => colourViolations(p, readFileSync(p, "utf8")));
    expect(violations).toEqual([]);
    // The scanner itself catches each forbidden form.
    const hash = "#";
    expect(colourViolations("x.css", `a { color: ${hash}fff; }`)).toHaveLength(1);
    expect(colourViolations("x.css", `a { color: ${"rgb"}(0, 0, 0); }`)).toHaveLength(1);
    const [named1, named2] = [["r", "e", "d"], ["wh", "ite"]].map((parts) => parts.join(""));
    expect(colourViolations("x.css", `a { border: 1px solid ${named1}; }`)).toHaveLength(1);
    expect(colourViolations("x.tsx", `style={{ color: "${named2}" }}`)).toHaveLength(1);
    expect(colourViolations("x.css", "a { color: var(--grey-7); }")).toEqual([]);
  });

  it("purple share 8-25%", () => {
    const cssFiles = SOURCE_FILES.filter((p) => rel(p).startsWith("app/") && p.endsWith(".css"));
    const inlineStyles = SOURCE_FILES.filter((p) => /\.tsx$/.test(p))
      .flatMap((p) => readFileSync(p, "utf8").match(/style=\{\{[^}]*\}\}/g) ?? [])
      .join("\n");
    const text = cssFiles.map((p) => readFileSync(p, "utf8")).join("\n") + inlineStyles;
    const purple = (text.match(/var\(--purple-\d\)/g) ?? []).length;
    const grey = (text.match(/var\(--grey-\d\)/g) ?? []).length;
    const share = purple / (purple + grey);
    expect(purple).toBeGreaterThan(0);
    expect(share).toBeGreaterThanOrEqual(0.08);
    expect(share).toBeLessThanOrEqual(0.25);
  });

  it("fonts self-hosted, sha256 match, 3 font-faces", () => {
    const expected: Record<string, string> = {
      "SCBXBeta2-Light.otf": "8c9cf6dea0d2fe25d0e661911202a680a496eb4fe812529e717c77ad379c5527",
      "SCBXBeta2-Regular.otf": "1ee2d72857c69bd276a30b14f594396cea00c1680fcd2c9a3a3de1b1b61ff76b",
      "SCBXBeta2-Bold.otf": "6a4d02311aa39d5e7ff8a873b3352e2cc2b293229dfe4b5eeea14d9bc2d5bc12",
    };
    const fontDir = join(WEB, "public", "fonts");
    expect(readdirSync(fontDir).sort()).toEqual(Object.keys(expected).sort());
    for (const [name, sha] of Object.entries(expected)) {
      expect(createHash("sha256").update(readFileSync(join(fontDir, name))).digest("hex"), name).toBe(sha);
    }
    const faces = [...THEME.matchAll(/@font-face\s*{([^}]*)}/g)].map((m) => m[1]);
    expect(faces).toHaveLength(3);
    const weights = faces.map((f) => f.match(/font-weight:\s*(\d+)/)?.[1]).sort();
    expect(weights).toEqual(["300", "400", "700"]);
    for (const face of faces) {
      expect(face).toMatch(/font-family:\s*"SCBXBeta2"/);
      expect(face).toMatch(/font-display:\s*swap/);
      expect(face).toMatch(/src:\s*url\("\/fonts\/SCBXBeta2-(Light|Regular|Bold)\.otf"\)/);
    }
    expect(TOKENS.type.startsWith('"SCBXBeta2"')).toBe(true);
  });

  it("no remote font URLs", () => {
    const hits: string[] = [];
    for (const p of SOURCE_FILES) {
      const text = readFileSync(p, "utf8");
      if (/next\/font\/google|fonts\.googleapis|fonts\.gstatic/.test(text)) hits.push(rel(p));
      if (p.endsWith(".css") && /url\(\s*["']?(https?:)?\/\//.test(text)) hits.push(`${rel(p)}: remote url()`);
      if (p.endsWith(".css") && /@import/.test(text)) hits.push(`${rel(p)}: @import`);
    }
    expect(hits).toEqual([]);
  });

  it(`no ${BRAND} logo files or references`, () => {
    const logoHashes = new Set([
      "a1312461aa1a28923dc1efea7060b2c16d81d17d8c80e46f7b15b0b1fb5803cb", // logo-black.png
      "dfee5ad8885947df01587ff56bb5da1bfa091e1939655dc595ce46c22919b1d0", // logo-white.png
    ]);
    const files = ALL_FILES.filter((p) => rel(p) !== "package-lock.json");
    expect(files.filter((p) => /logo/i.test(rel(p)))).toEqual([]);
    const byHash = files.filter((p) => logoHashes.has(createHash("sha256").update(readFileSync(p)).digest("hex")));
    expect(byHash).toEqual([]);
    // The brand name may appear only inside the font family/filename SCBXBeta2 (needle built so this file stays clean).
    const needle = new RegExp("sc" + "bx(?!beta2)", "i");
    const refs = files
      .filter((p) => !rel(p).startsWith("public/fonts/"))
      .filter((p) => needle.test(readFileSync(p, "utf8")) || needle.test(rel(p)))
      .map(rel);
    expect(refs).toEqual([]);
  });

  it("titles use MedX template", () => {
    const layout = readFileSync(join(WEB, "app", "layout.tsx"), "utf8");
    expect(layout).toContain('const SITE_TITLE = "MedX — AI Clinical Front Door (research prototype)"');
    expect(layout).toContain("template: `%s · ${SITE_TITLE}`");
    expect(layout).toContain("default: SITE_TITLE");
    const stale = SOURCE_FILES.filter((p) => rel(p).startsWith("app/"))
      .flatMap((p) => readFileSync(p, "utf8").split("\n").map((line) => [rel(p), line] as const))
      .filter(([, line]) => line.includes("Clinical Front Door (research prototype)") && !line.includes("MedX"));
    expect(stale).toEqual([]);
  });
});
