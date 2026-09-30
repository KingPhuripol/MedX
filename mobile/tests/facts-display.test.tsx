/** V2C-C6: missing is never negative. Table-driven over 6 fields × every state, on recording and review. */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Review } from "@/components/Review";
import { COPY } from "@/lib/copy";
import { rows, type Scribe } from "@/lib/voice";

import { ASK, fact, nextAction, session, statuses } from "./fixtures/scenario";
import { renderRecording } from "./helpers";

type Case = { name: string; build: (field: string) => Scribe };
const NEG = /ไม่แพ้|ไม่มีประวัติแพ้/;

function scribe(field: string, status: "MISSING" | "KNOWN" | "UNKNOWN" | "REFUSED" | null, facts: ReturnType<typeof fact>[] = [], sess = {}): Scribe {
  const st = statuses(status ? { [field]: status } : {});
  return { session: session(sess) as Scribe["session"], facts: facts as Scribe["facts"], field_statuses: status ? st : st.filter((s) => s.field !== field), next_action: nextAction(st) as Scribe["next_action"], turns: [] };
}

const valueFor = (field: string, v: unknown, text: string, state: "KNOWN" | "UNKNOWN" | "REFUSED" = "KNOWN") =>
  field === "allergy_status" ? [fact("allergy_status", v, text, "vt_1", state)] : [fact(field, v, text, "vt_1", state)];

const CASES: Case[] = [
  { name: "no fact, no status", build: (f) => scribe(f, null) },
  { name: "MISSING", build: (f) => scribe(f, "MISSING") },
  { name: "UNKNOWN", build: (f) => scribe(f, "UNKNOWN", valueFor(f, null, "", "UNKNOWN")) },
  { name: "REFUSED", build: (f) => scribe(f, "REFUSED", valueFor(f, null, "", "REFUSED")) },
  {
    name: "KNOWN present",
    build: (f) =>
      scribe(f, "KNOWN", f === "allergy_status" ? [fact("allergy_status", "present", "แพ้ยา", "vt_1"), fact("allergens", ["amoxicillin"], "แพ้อะม็อกซีซิลลิน", "vt_1")] : valueFor(f, "x", "ค่าที่ได้")),
  },
  { name: "allergy_conflict", build: (f) => scribe(f, "KNOWN", valueFor(f, "none", "ไม่มีประวัติแพ้ยา"), { allergy_conflict: true }) },
  { name: "extraction_error", build: (f) => scribe(f, "KNOWN", valueFor(f, "none", "ไม่มีประวัติแพ้ยา"), { extraction_error: true }) },
  { name: "unknown value", build: (f) => scribe(f, "KNOWN", valueFor(f, "maybe", "ไม่แพ้มั้ง")) },
  { name: "KNOWN none but status MISSING", build: (f) => scribe(f, "MISSING", valueFor(f, "none", "ไม่มีประวัติแพ้ยา")) },
];

async function recordingRow(s: Scribe, field: string) {
  const r = await renderRecording({ init: { scribe: s } });
  const row = document.querySelector(`.fact[data-field="${field}"]`) as HTMLElement;
  return { r, row };
}

function reviewRow(s: Scribe, field: string) {
  render(
    <Review
      patient={{ id: "SYN-2026-0023" }}
      scribe={s}
      durationMs={0}
      redFlag={null}
      ackAtMs={null}
      consentAtMs={Date.now()}
      onContinue={vi.fn()}
      onSubmitted={vi.fn()}
      onAuthLost={vi.fn()}
    />,
  );
  return document.querySelector(`.review-list > li[data-field="${field}"]`) as HTMLElement;
}

describe.each(ASK.map((f) => [f]))("%s", (field) => {
  it.each(CASES.map((c) => [c.name, c]))("%s: never a negative, never blank", async (_n, c) => {
    const s = c.build(field);
    const { row, r } = await recordingRow(s, field);
    const val = row.querySelector(".val, .val--asking") as HTMLElement;
    expect(val.textContent?.trim()).not.toBe("");
    expect(val.textContent?.trim()).not.toMatch(/^(-|ไม่มี)$/);
    if (field === "allergy_status") expect(row.textContent).not.toMatch(NEG);
    const st = s.field_statuses.find((x) => x.field === field)?.status ?? "MISSING";
    if (st === "MISSING") expect(val).toHaveTextContent(COPY.rec.valueMissing);
    r.view.unmount();

    const item = reviewRow(s, field);
    if (field === "allergy_status") expect(item.textContent).not.toMatch(NEG);
    expect(within(item).queryByRole("button", { name: COPY.review.confirmNoAllergy })).toBeNull();
    if (st === "MISSING") expect(within(item).getByText(COPY.review.tag.missing)).toBeInTheDocument();
  });
});

describe("the one negative case", () => {
  it("KNOWN allergy_status value none shows ไม่มีประวัติแพ้ยา and the dedicated confirm button", async () => {
    const s = scribe("allergy_status", "KNOWN", [fact("allergy_status", "none", "ไม่แพ้ยา", "vt_1")]);
    expect(rows(s).find((r) => r.field === "allergy_status")?.negativeAllergy).toBe(true);
    const { row, r } = await recordingRow(s, "allergy_status");
    expect(row).toHaveTextContent("ไม่มีประวัติแพ้ยา");
    r.view.unmount();
    const item = reviewRow(s, "allergy_status");
    expect(within(item).getByRole("button", { name: COPY.review.confirmNoAllergy })).toBeInTheDocument();
  });

  it("the latest fact wins: none superseded by present is not a negative", () => {
    const s = scribe("allergy_status", "KNOWN", [fact("allergy_status", "none", "", "vt_1"), fact("allergy_status", "present", "แพ้ยา", "vt_2")]);
    const row = rows(s).find((r) => r.field === "allergy_status")!;
    expect(row.negativeAllergy).toBe(false);
    expect(row.value).not.toMatch(NEG);
  });

  it("present with an allergen text that reads negative is never shown as negative", () => {
    const s = scribe("allergy_status", "KNOWN", [fact("allergy_status", "present", "", "vt_1"), fact("allergens", [], "ไม่แพ้อะไร", "vt_1")]);
    expect(rows(s).find((r) => r.field === "allergy_status")!.value).not.toMatch(NEG);
  });
});
