/** V2C-C11 static parts: manifest, icon files and sizes, a service worker with no caching or /api handling. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { read, ROOT } from "./files";

const manifest = JSON.parse(read("public/manifest.webmanifest"));

function pngSize(path: string): [number, number] {
  const b = readFileSync(resolve(ROOT, "public", path.replace(/^\//, "")));
  expect(b.subarray(1, 4).toString("latin1")).toBe("PNG");
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}

describe("manifest", () => {
  it("has the required installable fields", () => {
    expect(manifest).toMatchObject({ lang: "th", start_url: "/", scope: "/", display: "standalone", orientation: "portrait" });
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
  });

  it("icons 192, 512 and 512 maskable exist with matching pixel sizes", () => {
    const want = [
      ["192x192", undefined],
      ["512x512", undefined],
      ["512x512", "maskable"],
    ];
    for (const [sizes, purpose] of want) {
      const icon = manifest.icons.find((i: { sizes: string; purpose?: string }) => i.sizes === sizes && i.purpose === purpose);
      expect(icon, `${sizes} ${purpose ?? ""}`).toBeTruthy();
      const [w, h] = pngSize(icon.src);
      expect(`${w}x${h}`).toBe(sizes);
    }
  });

  it("is linked from the layout and the service worker is registered", () => {
    expect(read("app/layout.tsx")).toContain('manifest: "/manifest.webmanifest"');
    expect(read("components/SwRegister.tsx")).toContain('register("/sw.js")');
  });
});

describe("service worker (T11)", () => {
  const sw = read("public/sw.js");
  it("never touches Cache Storage or handles fetch/api", () => {
    expect(sw).not.toMatch(/caches|cache\.put|\/api|addEventListener\(\s*["']fetch/);
  });
});
