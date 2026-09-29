import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import "./router-mock";

import TriageReview from "@/components/TriageReview";
import { BANNER_INCOMPLETE, BANNER_NOT_PERFORMED, type Assessment, type Screening } from "@/lib/triage";

// Slice i2, I2-A10 / condition C2: the red-flag screening block never overclaims. Synthetic fixtures only.
const OVERCLAIM = /no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)/i;
const RULES = Array.from({ length: 16 }, (_, i) => `RF-${String(i + 1).padStart(2, "0")}`);
const LABEL = "provisional research prototype; thresholds copied from the cited source, pending clinical expert review";
const SCOPE =
  "rf-1.1.0: 16 declared rules over vitals within their freshness windows and symptoms mentioned in the intake " +
  "transcript; an unmentioned symptom is unknown, not absent";

function screening(over: Partial<Screening>): Screening {
  return {
    status: "evaluated",
    performed: true,
    banner: null,
    rules_evaluated: RULES,
    rules_not_evaluated: [],
    missing_inputs: [],
    rule_set_version: "rf-1.1.0",
    label: LABEL,
    scope: SCOPE,
    n_declared: 16,
    n_evaluated: 16,
    n_not_evaluated: 0,
    n_fired: 0,
    readings: [
      { vital: "spo2", value: 97, read_at: "2026-09-02T09:35:00+07:00", age_min: 5, window_min: 60, fresh: true, item_id: "C-F02" },
    ],
    ...over,
  };
}

const BASE: Assessment = {
  assessment_id: "a1",
  case_ref: "SYN-S4-011",
  as_of: "2026-09-02T09:40:00+07:00",
  ruleset_version: "rf-1.1.0",
  alerts: [],
  not_evaluable: [],
  escalation_required: false,
  department: {
    status: "suggested",
    top3: [{ code: "MED", label_th: "อายุรกรรม", label_en: "Internal medicine", score: 0.7, evidence_refs: ["C-F03"] }],
    uncertainty: "low",
    uncertainty_label: "MOCK baseline — not calibrated",
    missing_information: [],
    reason: null,
  },
  review_status: "pending_review",
  confirmed_department: null,
  output_label: "Suggestion for nurse review",
  graph_id: "g-1",
};

const FIRED_ALERT = {
  rule_id: "RF-01",
  ruleset_version: "rf-1.1.0",
  name_en: "Low oxygen saturation",
  name_th: "ออกซิเจนต่ำ",
  severity: "escalate" as const,
  evidence_refs: ["C-F02"],
  message_en: "Low oxygen saturation. Escalate to a clinician now.",
  message_th: "ส่งต่อแพทย์ทันที",
};

const STATES: Record<string, Assessment> = {
  evaluated_zero: { ...BASE, screening: screening({}) },
  evaluated_alerts: {
    ...BASE,
    alerts: [FIRED_ALERT],
    escalation_required: true,
    screening: screening({ n_fired: 1 }),
  },
  partial: {
    ...BASE,
    screening: screening({
      status: "partially_evaluated",
      performed: false,
      banner: BANNER_INCOMPLETE,
      rules_evaluated: RULES.slice(0, 13),
      rules_not_evaluated: RULES.slice(13),
      missing_inputs: ["vital.capillary_glucose_mg_dl (missing)", "vital.temp_c (stale)"],
      n_evaluated: 13,
      n_not_evaluated: 3,
    }),
  },
  unavailable: {
    ...BASE,
    escalation_required: true,
    screening: screening({
      status: "unavailable",
      performed: false,
      banner: BANNER_NOT_PERFORMED,
      rules_evaluated: [],
      rules_not_evaluated: RULES,
      n_evaluated: 0,
      n_not_evaluated: 16,
      readings: [],
    }),
  },
};

function renderState(a: Assessment) {
  return render(<TriageReview assessment={a} departments={[]} onReview={vi.fn()} />);
}

describe("TriageReview red-flag screening block (I2-A10)", () => {
  it.each(Object.keys(STATES))("%s: rule set, label, scope and counts shown; never an all-clear", (key) => {
    const { container } = renderState(STATES[key]);
    const block = screen.getByTestId("screening-section");
    expect(block).toHaveTextContent("rf-1.1.0");
    expect(block).toHaveTextContent(LABEL);
    expect(block).toHaveTextContent("16 declared rules");
    expect(container.textContent ?? "").not.toMatch(OVERCLAIM);
  });

  it("evaluated with 0 alerts renders '0 of 16 declared rules fired' with scope, and no warning banner", () => {
    renderState(STATES.evaluated_zero);
    expect(screen.getByTestId("screening-count")).toHaveTextContent("0 of 16 declared rules fired");
    expect(screen.getByTestId("screening-count")).toHaveTextContent("Scope: rf-1.1.0");
    expect(screen.queryByTestId("screening-banner")).toBeNull();
    expect(screen.getByTestId("screening-readings")).toHaveTextContent("read at 2026-09-02T09:35:00+07:00");
  });

  it("action bar summary never reads as all-clear when screening was not fully evaluated (C2)", () => {
    for (const key of ["partial", "unavailable"]) {
      const { container, unmount } = renderState(STATES[key]);
      const bar = container.querySelector(".ui-action-bar")!;
      expect(bar).toHaveTextContent("การคัดกรอง red flag ไม่ครบหรือไม่ได้ทำ — ต้องประเมินผู้ป่วยโดยตรง");
      expect(bar).not.toHaveTextContent("ไม่มีรายการที่ต้องรับทราบ");
      unmount();
    }
    const ok = renderState(STATES.evaluated_zero);
    expect(ok.container.querySelector(".ui-action-bar")).toHaveTextContent("ไม่มีรายการที่ต้องรับทราบ");
  });

  it("evaluated with alerts renders the fired count and the alert list", () => {
    renderState(STATES.evaluated_alerts);
    expect(screen.getByTestId("screening-count")).toHaveTextContent("1 of 16 declared rules fired");
    expect(screen.getByTestId("alerts-section")).toHaveTextContent("Low oxygen saturation");
  });

  it("partial renders the INCOMPLETE text banner (role=alert) and lists what was not evaluated", () => {
    renderState(STATES.partial);
    const banner = screen.getByTestId("screening-banner");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(BANNER_INCOMPLETE);
    expect(banner).toHaveTextContent("13 of 16 declared rules were evaluated");
    expect(screen.getByTestId("screening-not-evaluated")).toHaveTextContent("vital.temp_c (stale)");
    expect(screen.queryByTestId("screening-count")).toBeNull();
  });

  it("unavailable renders the NOT PERFORMED text banner (role=alert)", () => {
    renderState(STATES.unavailable);
    const banner = screen.getByTestId("screening-banner");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(BANNER_NOT_PERFORMED);
    expect(screen.queryByTestId("screening-count")).toBeNull();
  });

  it("a missing screening block (legacy assessment) renders NOT PERFORMED, not an all-clear", () => {
    const { container } = renderState({ ...BASE, screening: null });
    expect(screen.getByTestId("screening-banner")).toHaveTextContent(BANNER_NOT_PERFORMED);
    expect(container.textContent ?? "").not.toMatch(OVERCLAIM);
  });

  it("state is carried by text, not colour: no inline styles or ad-hoc colours in the screening component", () => {
    const src = readFileSync(resolve(__dirname, "../components/ScreeningBlock.tsx"), "utf8");
    expect(src).not.toMatch(/style=|#[0-9a-f]{3,6}\b|rgb\(|className=/i);
  });
});
