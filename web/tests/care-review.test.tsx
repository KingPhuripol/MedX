import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "./router-mock";

import CareReview from "@/components/CareReview";
import type { Assessment, Screening, ScreeningStatus, Vocabulary } from "@/lib/care";

const CLAIMS = /diagnos|prescrib|treat|dose|dosage|วินิจฉัย|สั่งยา|ให้ยา|รักษา/i;

const VOCAB: Vocabulary = {
  next_information: [
    { code: "NI-OBS-REPEAT-VITALS", display: "Repeat vital signs", display_th: "วัดสัญญาณชีพซ้ำ" },
    { code: "NI-LAB-LACTATE", display: "Serum lactate", display_th: "แลคเตต" },
  ],
  pathway_options: [{ code: "CP-SEPSIS-SCREEN", display: "Sepsis screening pathway", display_th: "แนวทางคัดกรอง" }],
};

const REF = { item_id: "SYNE-0011-VS2", data_type: "Vitals", available_at_time: "2030-05-27T09:54:32+07:00" };

const BANNERS: Record<ScreeningStatus, string | null> = {
  evaluated: null,
  partially_evaluated: "RED-FLAG SCREENING INCOMPLETE",
  not_evaluated: "RED-FLAG SCREENING NOT PERFORMED",
  unavailable: "RED-FLAG SCREENING NOT PERFORMED",
};

function screening(status: ScreeningStatus): Screening {
  const rules_evaluated = status === "evaluated" ? ["RF-HR", "RF-STROKE"] : ["RF-HR"];
  const rules_not_evaluated = status === "evaluated" ? [] : ["RF-STROKE"];
  return {
    status,
    performed: status === "evaluated",
    banner: BANNERS[status],
    rules_evaluated,
    rules_not_evaluated,
    missing_inputs: status === "evaluated" ? [] : ["symptom.sudden_facial_droop"],
    rule_set_version: "rf-1.1.0",
    label: "provisional research prototype; thresholds copied from the cited source, pending clinical expert review",
    scope: "rf-1.1.0: 16 declared rules; care screening uses the latest structured vitals and demographics only",
    n_declared: 16,
    n_evaluated: 16 - rules_not_evaluated.length,
    n_not_evaluated: rules_not_evaluated.length,
    n_fired: 0,
    readings: [],
    conflicts: [],
  };
}

const RED: Assessment = {
  alerts: [
    {
      rule_id: "RF-CONSC",
      ruleset_version: "rf-1.1.0",
      name_en: "New confusion or reduced consciousness",
      name_th: "ทดสอบ",
      severity: "escalate",
      evidence_refs: ["SYNE-0011-VS2:vital.new_confusion"],
      message_en: "Escalate to a clinician now.",
      message_th: "ส่งต่อแพทย์ทันที",
    },
    {
      rule_id: "RF-QSOFA",
      ruleset_version: "rf-1.1.0",
      name_en: "qSOFA 2 or more",
      name_th: "ทดสอบ",
      severity: "escalate",
      evidence_refs: ["SYNE-0011-VS2:vital.rr"],
      message_en: "Escalate to a clinician now.",
      message_th: "ส่งต่อแพทย์ทันที",
    },
  ],
  red_flag_screening: screening("partially_evaluated"),
  escalation_required: true,
  status: "suggested",
  case_summary: [{ text: "Age 70, sex male", evidence_refs: [REF] }],
  next_information: [
    {
      code: "NI-LAB-LACTATE",
      kind: "lab",
      display: "Serum lactate",
      display_th: "แลคเตต",
      evidence_refs: [REF],
      source_refs: ["EVANS-SSC-2021"],
    },
  ],
  pathway_options: [
    { code: "CP-SEPSIS-SCREEN", display: "Sepsis screening pathway", display_th: "x", evidence_refs: [REF], source_refs: ["EVANS-SSC-2021"] },
  ],
  missing_information: ["lab_results"],
  uncertainty: "MOCK baseline — not calibrated",
  reason: null,
  provider: "mock",
  model_version: "mock-0.1.0+care-rules-1.0.0",
  contract_version: "0.1.0",
  rules_version: "care-rules-1.0.0",
  as_of: "2030-05-27T10:32:32+07:00",
  decision_point: "T2",
  case_id: "SYNE-0011",
  output_label: "Suggestion for physician review — research prototype",
  assessment_id: "a1",
  created_at: "2026-09-27T00:00:00+00:00",
  review_status: "pending_review",
  review: null,
};

const ABSTAINED: Assessment = {
  ...RED,
  alerts: [],
  escalation_required: false,
  status: "abstained",
  case_summary: [],
  next_information: [],
  pathway_options: [],
  missing_information: ["duration", "allergy_status"],
  reason: "required_information_missing",
  provider: null,
  model_version: null,
};

function position(a: HTMLElement, b: HTMLElement) {
  return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe("CareReview", () => {
  it("renders the red-flag region first, then summary, next information (ol), pathways, missing", () => {
    render(<CareReview assessment={RED} vocabulary={VOCAB} onReview={vi.fn()} />);
    const red = screen.getByTestId("redflag-section");
    expect(screen.getByTestId("alerts")).toHaveAttribute("role", "alert");
    const order = ["case-summary", "next-information", "pathway-options", "missing-information"].map((id) =>
      screen.getByTestId(id),
    );
    let prev: HTMLElement = red;
    for (const el of order) {
      expect(position(prev, el)).toBe(true);
      prev = el;
    }
    expect(screen.getByTestId("next-information").tagName).toBe("OL");
    expect(screen.getByTestId("next-information")).toHaveTextContent("available 2030-05-27T09:54:32+07:00");
    expect(screen.getByText(/Escalate to a clinician now\./, { selector: "strong" })).toBeInTheDocument();
  });

  it.each(Object.keys(BANNERS) as ScreeningStatus[])("shows the banner text for screening %s", (status) => {
    render(<CareReview assessment={{ ...RED, red_flag_screening: screening(status) }} vocabulary={VOCAB} onReview={vi.fn()} />);
    const text = BANNERS[status];
    if (text) {
      expect(screen.getByTestId("screening-banner")).toHaveTextContent(text);
      expect(screen.getByTestId("screening-not-evaluated")).toHaveTextContent("RF-STROKE");
    } else {
      expect(screen.queryByTestId("screening-banner")).not.toBeInTheDocument();
      expect(screen.getByTestId("screening-count")).toHaveTextContent("0 of 16 declared rules fired");
    }
  });

  it("keeps confirm disabled until every alert and the screening banner are acknowledged", async () => {
    const onReview = vi.fn(async () => null);
    render(<CareReview assessment={RED} vocabulary={VOCAB} onReview={onReview} />);
    const confirm = screen.getByRole("button", { name: "Confirm suggestion" });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I have seen alert RF-CONSC"));
    await userEvent.click(screen.getByLabelText("I have seen alert RF-QSOFA"));
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/I have seen that red-flag screening incomplete/));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(onReview).toHaveBeenCalledWith("confirm", {
        acknowledged_alert_ids: ["RF-CONSC", "RF-QSOFA"],
        screening_acknowledged: true,
      }),
    );
  });

  it("abstained view shows the exact missing list, no suggestions, and only edit/reject", async () => {
    const onReview = vi.fn(async () => null);
    render(<CareReview assessment={ABSTAINED} vocabulary={VOCAB} onReview={onReview} />);
    expect(screen.getByTestId("abstained")).toBeInTheDocument();
    for (const id of ["case-summary", "next-information", "pathway-options"]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument();
    }
    const items = screen.getByTestId("missing-information").querySelectorAll("li");
    expect(Array.from(items).map((li) => li.textContent)).toEqual(["duration", "allergy_status"]);
    expect(screen.queryByRole("button", { name: "Confirm suggestion" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/I have seen that red-flag screening incomplete/));
    await userEvent.click(screen.getByLabelText(/Repeat vital signs/));
    await userEvent.type(screen.getByLabelText("Reason for the edit"), "manual plan");
    await userEvent.click(screen.getByRole("button", { name: "Save edited suggestion" }));
    await waitFor(() =>
      expect(onReview).toHaveBeenCalledWith("edit", {
        next_information: ["NI-OBS-REPEAT-VITALS"],
        pathway_options: [],
        reason: "manual plan",
        acknowledged_alert_ids: [],
        screening_acknowledged: true,
      }),
    );
    expect(screen.getByRole("button", { name: "Reject suggestion" })).toBeEnabled();
  });

  it("uses no claim terms and shows the research-prototype review label", () => {
    const { container } = render(<CareReview assessment={RED} vocabulary={VOCAB} onReview={vi.fn()} />);
    expect(container.textContent).toMatch(/Suggestion for physician review — research prototype/);
    expect(container.textContent ?? "").not.toMatch(CLAIMS);
  });

  it("filters the edit picker: matches show, non-matching unselected rows hide, selected rows stay", async () => {
    const vocab: Vocabulary = {
      ...VOCAB,
      next_information: [
        ...VOCAB.next_information,
        { code: "NI-LAB-CULTURE", display: "Blood culture", display_th: "เพาะเชื้อ" },
      ],
    };
    render(<CareReview assessment={ABSTAINED} vocabulary={vocab} onReview={vi.fn()} />);
    const row = (re: RegExp) => screen.getByLabelText(re).closest("label") as HTMLElement;
    await userEvent.click(screen.getByLabelText(/Repeat vital signs/)); // selected, does not match the query
    await userEvent.type(document.getElementById("edit-ni-filter") as HTMLElement, "lactate");
    expect(row(/Serum lactate/)).toBeVisible();
    expect(row(/Blood culture/)).not.toBeVisible();
    expect(row(/Repeat vital signs/)).toBeVisible();
    // Every checkbox stays in the DOM and the count reflects the selection.
    expect(screen.getByLabelText(/Blood culture/)).toBeInTheDocument();
    expect(screen.getByText("เลือก 1/5")).toBeInTheDocument();
  });

  it("keeps Reject outside any details, and puts acknowledgements between red flags and the suggestion", () => {
    render(<CareReview assessment={RED} vocabulary={VOCAB} onReview={vi.fn()} />);
    const reject = screen.getByRole("button", { name: "Reject suggestion" });
    expect(reject.closest("details")).toBeNull();
    expect(screen.getByLabelText("Reason for rejecting").closest("details")).toBeNull();
    const red = screen.getByTestId("redflag-section");
    const ack = screen.getByTestId("acknowledgements");
    const sugg = screen.getByTestId("suggestion-section");
    expect(position(red, ack)).toBe(true);
    expect(position(ack, sugg)).toBe(true);
  });

  it("shows the confirmed state after review", () => {
    const done: Assessment = {
      ...RED,
      review_status: "confirmed",
      review: {
        action: "confirm",
        final_codes: { next_information: ["NI-LAB-LACTATE"], pathway_options: ["CP-SEPSIS-SCREEN"] },
        reviewer_id: 2,
        reviewer_role: "physician",
        ts_utc: "2026-09-27T02:45:00.000+00:00",
        acknowledged_alert_ids: ["RF-CONSC", "RF-QSOFA"],
        screening_acknowledged: true,
        reason_sha256: null,
      },
    };
    render(<CareReview assessment={done} vocabulary={VOCAB} onReview={vi.fn()} />);
    expect(screen.getByTestId("review-result")).toHaveTextContent("Confirmed: next information NI-LAB-LACTATE");
    expect(screen.queryByRole("button", { name: "Confirm suggestion" })).not.toBeInTheDocument();
    // Alerts stay visible after review.
    expect(screen.getByTestId("alerts")).toBeInTheDocument();
  });
});
