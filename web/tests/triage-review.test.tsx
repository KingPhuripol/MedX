import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "./router-mock";

import TriageReview from "@/components/TriageReview";
import type { Assessment, Department } from "@/lib/triage";

const DEPARTMENTS: Department[] = [
  { code: "CARD", label_th: "อายุรกรรมหัวใจ", label_en: "Cardiology" },
  { code: "MED", label_th: "อายุรกรรม", label_en: "Internal medicine" },
  { code: "ORTHO", label_th: "ศัลยกรรมกระดูกและข้อ", label_en: "Orthopedics" },
];

function alert(rule_id: string, name_en: string) {
  return {
    rule_id,
    ruleset_version: "rf-1.1.0",
    name_en,
    name_th: "ทดสอบ",
    severity: "escalate" as const,
    evidence_refs: ["C-F01"],
    message_en: `${name_en}. Escalate to a clinician now.`,
    message_th: "ส่งต่อแพทย์ทันที",
  };
}

const RED: Assessment = {
  assessment_id: "a1",
  case_ref: "SYN-S4-002",
  as_of: "2026-09-02T09:40:00+07:00",
  ruleset_version: "rf-1.1.0",
  alerts: [alert("RF-CHEST", "Acute chest pain"), alert("RF-HR", "Abnormal pulse")],
  not_evaluable: [{ rule_id: "RF-HYPOGLY", name_en: "Level 2 hypoglycaemia", name_th: "x", missing_inputs: ["vital.capillary_glucose_mg_dl"] }],
  escalation_required: true,
  department: {
    status: "suggested",
    top3: [
      { code: "CARD", label_th: "อายุรกรรมหัวใจ", label_en: "Cardiology", score: 0.8, evidence_refs: ["C-F03"] },
      { code: "MED", label_th: "อายุรกรรม", label_en: "Internal medicine", score: 0.2, evidence_refs: ["C-F03"] },
    ],
    uncertainty: "low",
    uncertainty_label: "MOCK baseline — not calibrated",
    missing_information: [],
    reason: null,
  },
  review_status: "pending_review",
  confirmed_department: null,
  output_label: "Suggestion for nurse review",
};

const ABSTAINED: Assessment = {
  ...RED,
  assessment_id: "a2",
  alerts: [],
  escalation_required: false,
  department: {
    status: "abstained",
    top3: [],
    uncertainty: null,
    uncertainty_label: "MOCK baseline — not calibrated",
    missing_information: ["vitals.spo2"],
    reason: "required_information_missing",
  },
};

describe("TriageReview", () => {
  it("places the alert section before the department section", () => {
    render(<TriageReview assessment={RED} departments={DEPARTMENTS} onReview={vi.fn()} />);
    const alerts = screen.getByTestId("alerts-section");
    const dept = screen.getByTestId("department-section");
    expect(alerts).toHaveAttribute("role", "alert");
    expect(alerts).toHaveAttribute("aria-labelledby", "alerts-title");
    expect(alerts.compareDocumentPosition(dept) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId("department-ranking").tagName).toBe("OL");
    expect(screen.getByTestId("not-evaluable")).toHaveTextContent("vital.capillary_glucose_mg_dl");
  });

  it("keeps confirm disabled until every alert is acknowledged", async () => {
    const onReview = vi.fn(async () => null);
    render(<TriageReview assessment={RED} departments={DEPARTMENTS} onReview={onReview} />);
    const confirm = screen.getByRole("button", { name: "Confirm department" });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I have seen alert RF-CHEST"));
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText("I have seen alert RF-HR"));
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(onReview).toHaveBeenCalledWith("confirm", {
        department_code: "CARD",
        acknowledged_alert_ids: ["RF-CHEST", "RF-HR"],
      }),
    );
  });

  it("shows the missing list and no ranking when abstained; only edit and reject remain", async () => {
    const onReview = vi.fn(async () => null);
    render(<TriageReview assessment={ABSTAINED} departments={DEPARTMENTS} onReview={onReview} />);
    expect(screen.queryByTestId("department-ranking")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm department" })).not.toBeInTheDocument();
    expect(screen.getByTestId("missing-information")).toHaveTextContent("vitals.spo2");
    await userEvent.selectOptions(screen.getByLabelText("Choose another department"), "ORTHO");
    await userEvent.type(screen.getByLabelText("Reason for the change"), "manual choice");
    await userEvent.click(screen.getByRole("button", { name: "Save edited department" }));
    await waitFor(() =>
      expect(onReview).toHaveBeenCalledWith("edit", {
        department_code: "ORTHO",
        reason: "manual choice",
        acknowledged_alert_ids: [],
      }),
    );
    expect(screen.getByRole("button", { name: "Reject suggestion" })).toBeEnabled();
  });

  it("uses no claim terms and labels the output as a suggestion for nurse review", () => {
    const { container } = render(<TriageReview assessment={RED} departments={DEPARTMENTS} onReview={vi.fn()} />);
    expect(container.textContent).toMatch(/Suggestion for nurse review/);
    expect(container.textContent ?? "").not.toMatch(/diagnos|prescrib|treat/i);
  });

  it("shows the confirmed state after review", () => {
    const done: Assessment = {
      ...RED,
      review_status: "confirmed",
      confirmed_department: "CARD",
      review: {
        action: "confirm",
        final_department: "CARD",
        reviewer_id: 1,
        reviewer_role: "nurse",
        ts_utc: "2026-09-02T02:45:00.000+00:00",
        acknowledged_alert_ids: ["RF-CHEST", "RF-HR"],
      },
    };
    render(<TriageReview assessment={done} departments={DEPARTMENTS} onReview={vi.fn()} />);
    expect(screen.getByTestId("review-result")).toHaveTextContent("Confirmed department: Cardiology");
    expect(screen.queryByRole("button", { name: "Confirm department" })).not.toBeInTheDocument();
  });
});
