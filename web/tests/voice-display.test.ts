import { describe, expect, it } from "vitest";

import { displayValue, type Fact } from "@/lib/voice";

function fact(field: string, value: Fact["value"], state: Fact["state"] = "KNOWN"): Fact {
  return { fact_id: "f", field, state, value, span_turn_ids: ["t1"], available_at_time: "2026-01-01T00:00:00Z" };
}

describe("displayValue: negatives are attributed to their real source", () => {
  it("labels a patient's answer as a denial", () => {
    expect(displayValue(fact("allergy_status", "none"), ["patient"])).toBe("none (patient denies drug allergy)");
  });

  it("never labels a nurse statement as 'patient denies'", () => {
    for (const speakers of [["nurse"], ["nurse", "patient"], []] as const) {
      const text = displayValue(fact("allergy_status", "none"), [...speakers]);
      expect(text).not.toContain("patient denies");
      expect(text).toContain("confirm with patient");
    }
    expect(displayValue(fact("current_medications", []), ["nurse"])).toContain("confirm with patient");
  });

  it("attributes a relative's answer to the relative", () => {
    expect(displayValue(fact("allergy_status", "none"), ["relative"])).toBe("none (relative reports no drug allergy)");
    expect(displayValue(fact("relevant_history", []), ["relative"])).toBe("none reported (by relative)");
  });

  it("shows UNKNOWN / REFUSED as no value, never as none", () => {
    expect(displayValue(fact("allergy_status", null, "UNKNOWN"), ["patient"])).toBe("—");
    expect(displayValue(fact("current_medications", null, "REFUSED"), ["patient"])).toBe("—");
  });
});
