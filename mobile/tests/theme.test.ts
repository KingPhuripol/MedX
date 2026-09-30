/** V2C-C3: only synced theme tokens. */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { read, rel, ROOT, walk } from "./files";

const sha = (p: string) => createHash("sha256").update(readFileSync(p)).digest("hex");
const NAMED =
  "white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|navy|teal|silver|maroon|olive|lime|aqua|fuchsia|brown|gold|indigo|violet|crimson|coral|salmon|tomato|beige|ivory|khaki|lavender|plum|tan|turquoise|cyan|magenta";

describe("theme tokens", () => {
  it("mobile/app/theme.css is byte-identical to web/app/theme.css", () => {
    expect(sha(resolve(ROOT, "app/theme.css"))).toBe(sha(resolve(ROOT, "../web/app/theme.css")));
  });

  it("no colour literals outside theme.css", () => {
    const hits: string[] = [];
    for (const f of walk(ROOT, [".ts", ".tsx", ".css", ".mjs"])) {
      if (rel(f) === "app/theme.css" || rel(f).endsWith(".d.ts")) continue;
      const src = readFileSync(f, "utf8");
      for (const re of [/#[0-9a-fA-F]{3,8}\b/g, /\brgba?\(/g, /\bhsla?\(/g]) for (const m of src.matchAll(re)) hits.push(`${rel(f)}: ${m[0]}`);
      const named = f.endsWith(".css")
        ? new RegExp(`(?:^|[;{\\s])(?:color|background(?:-color)?|border(?:-[a-z]+)?|fill|stroke|outline(?:-color)?|box-shadow)\\s*:[^;]*\\b(${NAMED})\\b`, "gm")
        : new RegExp(`\\b(?:color|background|backgroundColor|fill|stroke|borderColor)\\s*[:=]\\s*["'](${NAMED})["']`, "g");
      for (const m of src.matchAll(named)) hits.push(`${rel(f)}: ${m[1]}`);
    }
    expect(hits).toEqual([]);
  });

  it("manifest theme_color/background_color equal token values", () => {
    const manifest = JSON.parse(read("public/manifest.webmanifest"));
    const theme = read("app/theme.css");
    const tokens = new Set([...theme.matchAll(/--[\w-]+:\s*(#[0-9A-Fa-f]{3,8})/g)].map((m) => m[1].toUpperCase()));
    expect(tokens.has(String(manifest.theme_color).toUpperCase())).toBe(true);
    expect(tokens.has(String(manifest.background_color).toUpperCase())).toBe(true);
    expect(theme).toMatch(new RegExp(`--background:\\s*${manifest.background_color}`, "i"));
  });

  it("scripts/sync_theme.sh copies web → mobile", () => {
    const sh = readFileSync(resolve(ROOT, "../scripts/sync_theme.sh"), "utf8");
    expect(sh).toMatch(/cp "\$root\/web\/app\/theme\.css" "\$root\/mobile\/app\/theme\.css"/);
  });
});
