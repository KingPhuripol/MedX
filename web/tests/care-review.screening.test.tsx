import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import "./router-mock";

import CareReview from "@/components/CareReview";
import { CARE_STALE_TEXT, type Assessment, type Screening, type Vocabulary } from "@/lib/care";
import { BANNER_INCOMPLETE, BANNER_NOT_PERFORMED } from "@/lib/triage";

// Slice int2, INT2-A09 / A14: the physician care page renders the I2 screening block and never overclaims.
// Synthetic fixtures only.
const OVERCLAIM = /no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)/i;
const RULES = Array.from({ length: 16 }, (_, i) => `RF-${String(i + 1).padStart(2, "0")}`);
const LABEL = "provisional research prototype; thresholds copied from the cited source, pending clinical expert review";
// Mirrors the backend care CARE_SCREENING_SCOPE constant.
const SCOPE =
  "rf-1.1.0: 16 declared rules; care screening uses the latest structured vitals and demographics only " +
  "(a stale normal vital is not counted as screened; an abnormal one still alerts). Symptom rules are not " +
  "evaluated in care, because care does not read the intake transcript for red-flag symptoms; an unmentioned " +
  "symptom is unknown, not absent";
const VOCAB: Vocabulary = { next_information: [], pathway_options: [] };
const REF = { item_id: "SYNE-0011-VS2", data_type: "Vitals", available_at_time: "2030-05-27T09:54:32+07:00" };

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
      { vital: "hr", value: 88, read_at: "2030-05-27T09:54:32+07:00", age_min: 38, window_min: 60, fresh: true, item_id: "SYNE-0011-VS2" },
      { vital: "spo2", value: 97, read_at: "2030-05-27T08:00:00+07:00", age_min: 152, window_min: 60, fresh: false, item_id: "SYNE-0011-VS1" },
    ],
    conflicts: [],
    ...over,
  };
}

const ALERT = {
  rule_id: "RF-01",
  ruleset_version: "rf-1.1.0",
  name_en: "Low oxygen saturation",
  name_th: "ทดสอบ",
  severity: "escalate" as const,
  evidence_refs: ["SYNE-0011-VS2:vital.spo2"],
  message_en: "Escalate to a clinician now.",
  message_th: "ส่งต่อแพทย์ทันที",
};

const BASE: Assessment = {
  alerts: [],
  red_flag_screening: screening({}),
  escalation_required: false,
  status: "suggested",
  case_summary: [{ text: "Age 70, sex male", evidence_refs: [REF] }],
  next_information: [],
  pathway_options: [],
  missing_information: [],
  uncertainty: "MOCK baseline — not calibrated",
  reason: null,
  provider: "mock",
  model_version: "mock-0.1.0+care-rules-1.1.0",
  contract_version: "0.1.0",
  rules_version: "care-rules-1.1.0",
  as_of: "2030-05-27T10:32:32+07:00",
  decision_point: "T2",
  case_id: "SYNE-0011",
  output_label: "Suggestion for physician review — research prototype",
  assessment_id: "a1",
  created_at: "2026-09-27T00:00:00+00:00",
  review_status: "pending_review",
  review: null,
};

const STATES: Record<string, Assessment> = {
  evaluated_zero: BASE,
  evaluated_alerts: {
    ...BASE,
    alerts: [ALERT],
    escalation_required: true,
    red_flag_screening: screening({ n_fired: 1 }),
  },
  partial: {
    ...BASE,
    red_flag_screening: screening({
      status: "partially_evaluated",
      performed: false,
      banner: BANNER_INCOMPLETE,
      rules_evaluated: RULES.slice(0, 12),
      rules_not_evaluated: RULES.slice(12),
      missing_inputs: ["symptom.sudden_facial_droop", "vital.spo2:stale(read_at=2030-05-27T08:00:00+07:00, age_min=152)"],
      n_evaluated: 12,
      n_not_evaluated: 4,
    }),
  },
  unavailable: {
    ...BASE,
    red_flag_screening: screening({
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
  return render(<CareReview assessment={a} vocabulary={VOCAB} onReview={vi.fn()} />);
}

describe("CareReview red-flag screening block (INT2-A09 / A14)", () => {
  it.each(Object.keys(STATES))("%s: rule set, label, care scope shown inside the red-flag region, above the suggestion; never an all-clear", (key) => {
    const { container } = renderState(STATES[key]);
    const red = screen.getByTestId("redflag-section");
    const block = screen.getByTestId("screening-section");
    expect(red).toContainElement(block);
    expect(screen.getByTestId("screening-scope")).toHaveTextContent("rf-1.1.0");
    expect(screen.getByTestId("screening-scope")).toHaveTextContent(LABEL);
    expect(screen.getByTestId("screening-scope")).toHaveTextContent("Symptom rules are not evaluated in care");
    expect(red.compareDocumentPosition(screen.getByTestId("suggestion-section")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.textContent ?? "").not.toMatch(OVERCLAIM);
  });

  it("evaluated with 0 alerts: '0 of 16 declared rules fired' with the scope, 'No alert raised', no banner", () => {
    renderState(STATES.evaluated_zero);
    expect(screen.getByTestId("screening-count")).toHaveTextContent("0 of 16 declared rules fired");
    expect(screen.getByTestId("screening-count")).toHaveTextContent("Scope: rf-1.1.0");
    expect(screen.getByTestId("no-alert")).toHaveTextContent("No alert raised");
    expect(screen.queryByTestId("screening-banner")).toBeNull();
  });

  it("evaluated with alerts: the alert list and the fired count", () => {
    renderState(STATES.evaluated_alerts);
    expect(screen.getByTestId("alerts")).toHaveTextContent("Low oxygen saturation");
    expect(screen.getByTestId("screening-count")).toHaveTextContent("1 of 16 declared rules fired");
    expect(screen.queryByTestId("no-alert")).toBeNull();
  });

  it("partial: INCOMPLETE banner (role=alert) and the not-evaluated rules with the stale input", () => {
    renderState(STATES.partial);
    const banner = screen.getByTestId("screening-banner");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(BANNER_INCOMPLETE);
    const ne = screen.getByTestId("screening-not-evaluated");
    expect(ne).toHaveTextContent("RF-16");
    expect(ne).toHaveTextContent("vital.spo2:stale(read_at=");
  });

  it("unavailable: NOT PERFORMED banner (role=alert), every rule listed as not evaluated", () => {
    renderState(STATES.unavailable);
    const banner = screen.getByTestId("screening-banner");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(BANNER_NOT_PERFORMED);
    expect(screen.getByTestId("screening-not-evaluated")).toHaveTextContent("RF-01");
    expect(screen.queryByTestId("screening-count")).toBeNull();
  });

  it("stale care readings are listed with read time and age, and never say 'not used'", () => {
    renderState(STATES.evaluated_zero);
    const list = screen.getByTestId("screening-readings");
    expect(list).toHaveTextContent("read at 2030-05-27T08:00:00+07:00, age 152 min of a 60 min window");
    expect(list).toHaveTextContent(CARE_STALE_TEXT);
    expect(list.textContent ?? "").not.toMatch(/not used/i);
  });

  it("CareReview.tsx source carries no overclaim string", () => {
    const src = readFileSync(resolve(__dirname, "../components/CareReview.tsx"), "utf8");
    expect(src).not.toMatch(OVERCLAIM);
    expect(src).not.toMatch(/evaluated every rule/i);
  });
});
