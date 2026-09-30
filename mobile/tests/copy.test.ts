/** V2C-C14: every §5 string used by the app is byte-exact; the limitation label is last on every screen. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { COPY, FIELD_LABELS, PROPOSED_V2C } from "@/lib/copy";

import { leaves } from "./files";

/** The fixture: the copy tables of SPEC §5 plus the §3.1 aria-label column and the §4 glyph labels, ↵ treated as a line break. */
const spec = readFileSync(resolve(__dirname, "../../slices/v2c/SPEC.md"), "utf8");
const section = (from: string, to: string) => spec.slice(spec.indexOf(from), spec.indexOf(to, spec.indexOf(from)));
const S5 = section("## 5. Thai copy (exact)", "## 6.").replace(/ ↵ /g, "\n");
const S31 = section("### 3.1", "### 3.2");
const S4 = section("## 4. Accessibility", "## 5.");
const S15 = section("## 15. Decisions", "## 16.").replace(/ ↵ /g, "\n");
const FIXTURE = `${S5}\n${S31}\n${S4}`;

const C = COPY;
/** Function copies rendered with the spec's own placeholders. */
const FN: [string, string][] = [
  ["start.account", C.start.account("nurse1")],
  ["start.sexAge", C.start.sexAge("หญิง", 46)],
  ["start.arrived", C.start.arrived("10:24")],
  ["start.noMatch.head", C.start.noMatch("<input>").head],
  ["start.noMatch.body", C.start.noMatch("<input>").body],
  ["rec.factsCount", C.rec.factsCount("n" as unknown as number)],
  ["rec.noteListening", C.rec.noteListening("<field label>")],
  ["rec.reconnecting.head", C.rec.reconnecting("n" as unknown as number).head],
  ["rec.reconnecting.body", C.rec.reconnecting(1).body],
  ["rec.error.head", C.rec.error(1).head],
  ["rec.error.body", C.rec.error("n" as unknown as number).body],
  ["rec.ackStrip", C.rec.ackStrip("HH:MM")],
  ["review.meta", C.review.meta("`SYN-…`", "m" as unknown as number, "s" as unknown as number)],
  ["review.source", C.review.source("HH:MM")],
  ["review.heard", C.review.heard("<original>")],
  ["review.progress", C.review.progress("n" as unknown as number)],
  ["review.editedCount", C.review.editedCount("n" as unknown as number)],
  ["review.submitted.head", C.review.submitted("x").head],
  ["review.submitted.body", C.review.submitted("`SYN-…`").body],
];

describe("§5 copy is byte-exact", () => {
  it.each(leaves(COPY).map(([k, v]) => [k, v]))("COPY.%s", (_k, v) => {
    expect(FIXTURE).toContain(v);
  });

  it.each(FN)("COPY.%s()", (_k, v) => {
    expect(FIXTURE).toContain(v);
  });

  it.each(Object.entries(FIELD_LABELS))("field label %s", (_k, v) => {
    expect(S5).toContain(v);
  });

  it("the D-V2C-2 proposed strings match §15 byte-exact", () => {
    const listed = ["accessCodeLabel", "accessCodeInvalid", "voiceUnavailable", "sessionEnded", "slotAfterAck", "notConnected"] as const;
    for (const k of listed) for (const [, v] of leaves(PROPOSED_V2C[k])) expect(S15).toContain(v);
    expect(S15).toContain(PROPOSED_V2C.failedSegments("n" as unknown as number));
  });

  it("the limitation label is exact", () => {
    expect(C.limit).toBe("ข้อมูลสังเคราะห์ · ต้นแบบเพื่อการวิจัย");
  });
});
