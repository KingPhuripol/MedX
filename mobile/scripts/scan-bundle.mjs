// V2C-C10: the client bundle carries no secret, sentinel, ephemeral key or key name. Run after `npm run build`.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("../.next/static", import.meta.url).pathname;
const BANNED = [/\bsk-[A-Za-z0-9_-]{10,}/, /SENTINEL/, /\bek_[A-Za-z0-9]{8,}/, /OPENAI_API_KEY/];

const files = [];
const walk = (d) => {
  for (const n of readdirSync(d)) {
    const p = join(d, n);
    statSync(p).isDirectory() ? walk(p) : files.push(p);
  }
};
try {
  walk(ROOT);
} catch {
  console.error(`scan-bundle: ${ROOT} not found; run npm run build first`);
  process.exit(2);
}

let hits = 0;
for (const f of files) {
  const text = readFileSync(f, "utf8");
  for (const re of BANNED) {
    if (re.test(text)) {
      hits += 1;
      console.error(`scan-bundle: ${re} matched in ${f.slice(ROOT.length + 1)}`);
    }
  }
}
console.log(`scan-bundle: ${files.length} files scanned, ${hits} matches`);
process.exit(hits ? 1 : 0);
