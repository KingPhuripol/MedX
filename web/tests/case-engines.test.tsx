import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseSummary, EngineSummary } from "@/components/clinical/CaseWorkspace";
import type { CaseOverview, PharmaEngine, RedFlagEngine } from "@/lib/demo";

const NOT_RUN = "ยังประเมินไม่ได้ — ข้อมูลอาการยังไม่ถูกดึง";
const redFlag = (over: Partial<RedFlagEngine> = {}): RedFlagEngine => ({
  engine: "triage.redflags",
  ruleset_version: "rf-1.1.0",
  rules_total: 16,
  alerts: [],
  not_evaluated: [{ rule_id: "RF-CHEST", name_th: "เจ็บหน้าอก", missing_inputs: ["symptom.acute_chest_pain"], reason_th: NOT_RUN }],
  not_evaluated_text: NOT_RUN,
  ...over,
});
const pharma: PharmaEngine = {
  engine: "pharma.reconcile",
  pipeline_version: "s5-pipeline-2.6.0",
  rules_version: "s5-rules-2.1.0",
  formulary_version: "f1",
  issue_count: 2,
  notice_count: 0,
  unchecked_comparisons: 0,
};

describe("U7 engine summary", () => {
  it("shows versions, lists unrun rules, and never calls a no-alert case safe", () => {
    render(<EngineSummary engines={{ red_flag: redFlag(), pharma }} />);
    expect(screen.getByTestId("engine-alert-count")).toHaveTextContent("ไม่มีการแจ้งเตือนจากข้อมูลที่มีอยู่");
    expect(screen.getByTestId("engine-not-evaluated")).toHaveTextContent(NOT_RUN);
    expect(screen.getByTestId("engine-not-evaluated")).toHaveTextContent("RF-CHEST");
    expect(screen.getByTestId("engine-versions")).toHaveTextContent("rf-1.1.0");
    expect(screen.getByTestId("engine-versions")).toHaveTextContent("s5-pipeline-2.6.0");
    expect(screen.getByTestId("engine-versions")).toHaveTextContent("พบความคลาดเคลื่อน 2 รายการ");
    expect(screen.getByTestId("engine-summary")).not.toHaveTextContent("ปลอดภัย");
  });

  it("lists raised alerts", () => {
    const alert = { rule_id: "RF-SPO2", name_th: "ออกซิเจนต่ำ", message_th: "ส่งต่อแพทย์", evidence_refs: [] };
    render(<EngineSummary engines={{ red_flag: redFlag({ alerts: [alert], not_evaluated: [] }), pharma }} />);
    expect(screen.getByTestId("engine-alerts")).toHaveTextContent("RF-SPO2");
    expect(screen.queryByTestId("engine-not-evaluated")).toBeNull();
  });
});

describe("U7 previous reading with a missing vital", () => {
  it("names the vital that was not recorded in the previous reading", () => {
    const at = (t: string, temp: number | null) => ({
      observed_at: t,
      available_at_time: t,
      hr: 80,
      rr: 16,
      sbp: 120,
      dbp: 80,
      spo2: 97,
      temp_c: temp,
      consciousness: "A",
      on_oxygen: false,
    });
    const data = {
      run_id: "r",
      case_id: "SYNE-0121",
      intake: { chief_complaint: "x", onset: "y" },
      vitals: [at("2030-01-01T10:00:00+07:00", null), at("2030-01-01T11:00:00+07:00", 36.8)],
      allergies: null,
      labs: [],
    } as unknown as CaseOverview;
    render(<CaseSummary data={data} meds={null} runId="r" />);
    expect(screen.getByTestId("vitals-prev-missing")).toHaveTextContent("อุณหภูมิ");
    expect(screen.getByTestId("vital-temp_c-dir")).toHaveTextContent("ไม่มีค่าเทียบ");
    expect(screen.getByTestId("allergy-unknown")).toBeInTheDocument();
  });
});
