import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CaseSummary, labFlag, vitalDirection } from "@/components/clinical/CaseWorkspace";
import type { CaseOverview, MedicationData, VitalReading } from "@/lib/demo";

const reading = (over: Partial<VitalReading> = {}): VitalReading => ({
  observed_at: "2026-09-28T02:15:00+00:00",
  available_at_time: "2026-09-28T02:16:00+00:00",
  hr: 100,
  rr: 20,
  sbp: 120,
  dbp: 80,
  spo2: 96,
  temp_c: 36.8,
  consciousness: "A",
  on_oxygen: false,
  ...over,
});

const base = (over: Partial<CaseOverview> = {}): CaseOverview =>
  ({
    run_id: "r",
    case_id: "SYN-2026-0017",
    intake: { chief_complaint: "แน่นหน้าอก", onset: "40 นาที" },
    vitals: [reading(), reading({ observed_at: "2026-09-28T02:25:00+00:00", hr: 110, spo2: 91, temp_c: null })],
    allergies: [],
    labs: [],
    ...over,
  }) as CaseOverview;

const meds: MedicationData = {
  sources: [{ source_id: "s1", label: "สัมภาษณ์", recorded_value: "Aspirin 81 mg", captured_at: "2026-09-28T02:10:00+00:00" }],
  discrepancies: [
    { review_id: "a", type: "t", label: "l", detail: "d", status: "pending", provenance: [], version: 1 },
    { review_id: "b", type: "t", label: "l", detail: "d", status: "confirm", provenance: [], version: 1 },
  ],
};

describe("U6 CaseSummary missing-value rendering", () => {
  it("shows a null vital as missing (never 0, never normal) with no direction", () => {
    render(<CaseSummary data={base()} meds={meds} runId="r" />);
    const temp = screen.getByTestId("vital-temp_c");
    expect(temp).toHaveTextContent("ไม่มีบันทึก");
    expect(temp).not.toHaveTextContent("0");
    expect(screen.getByTestId("vital-temp_c-dir")).toBeEmptyDOMElement();
    expect(screen.getByTestId("vital-hr-dir")).toHaveTextContent("↑ เพิ่มขึ้น");
    expect(screen.getByTestId("vital-spo2-dir")).toHaveTextContent("↓ ลดลง");
    expect(screen.getByTestId("vital-rr-dir")).toHaveTextContent("→ เท่าเดิม");
  });

  it("renders no vitals as missing, not as an empty normal panel", () => {
    render(<CaseSummary data={base({ vitals: [] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("vitals-missing")).toHaveTextContent("ยังไม่มีบันทึกสัญญาณชีพ");
  });

  it("renders allergy [] (none recorded) and null (unknown) differently", () => {
    const { unmount } = render(<CaseSummary data={base({ allergies: [] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("allergy-none")).toHaveTextContent("ไม่มีประวัติแพ้ที่บันทึกไว้");
    expect(screen.queryByTestId("allergy-unknown")).toBeNull();
    unmount();
    render(<CaseSummary data={base({ allergies: null })} meds={meds} runId="r" />);
    expect(screen.getByTestId("allergy-unknown")).toHaveTextContent("ไม่ทราบสถานะการแพ้ — ต้องถาม");
    expect(screen.queryByTestId("allergy-none")).toBeNull();
  });

  it("lists allergy substances with reactions", () => {
    render(<CaseSummary data={base({ allergies: [{ substance: "เพนิซิลลิน", reaction: "ผื่น" }] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("allergy-item")).toHaveTextContent("เพนิซิลลิน — ผื่น");
  });

  it("counts only pending medication discrepancies and links to the medications tab", () => {
    render(<CaseSummary data={base()} meds={meds} runId="r1" />);
    expect(screen.getByTestId("med-discrepancy-count")).toHaveTextContent("1 รายการ");
    const link = within(screen.getByTestId("summary-meds")).getByRole("link", { name: /ดูรายละเอียดยา/ });
    expect(link).toHaveAttribute("href", "/app/cases/SYN-2026-0017/medications?run=r1");
  });

  it("shows medications as not loaded when the fetch failed (null), never as an empty list", () => {
    render(<CaseSummary data={base()} meds={null} runId="r" />);
    expect(screen.getByTestId("meds-missing")).toHaveTextContent("ยังไม่ได้โหลดข้อมูลยา");
    expect(screen.queryByTestId("med-discrepancy-count")).toBeNull();
  });

  it("labs: none yet, none abnormal, and abnormal with reference range", () => {
    const { unmount } = render(<CaseSummary data={base({ labs: [] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("labs-none-yet")).toHaveTextContent("ยังไม่มีผลแล็บ");
    unmount();
    const ok = { test: "K", value: 4, unit: "mmol/L", ref_low: 3.5, ref_high: 5.1, resulted_at: "x" };
    const { unmount: u2 } = render(<CaseSummary data={base({ labs: [ok] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("labs-normal")).toHaveTextContent("ไม่มีผลแล็บผิดปกติ");
    u2();
    render(<CaseSummary data={base({ labs: [ok, { ...ok, test: "Trop", value: 0.09, ref_low: 0, ref_high: 0.04 }] })} meds={meds} runId="r" />);
    const items = screen.getAllByTestId("lab-item");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("Trop");
    expect(items[0]).toHaveTextContent("↑ สูงกว่าช่วงอ้างอิง");
  });

  it("a lab with a missing value is surfaced as missing, not treated as normal", () => {
    const missing = { test: "Trop", value: null, unit: "ng/mL", ref_low: 0, ref_high: 0.04, resulted_at: "x" };
    render(<CaseSummary data={base({ labs: [missing] })} meds={meds} runId="r" />);
    expect(screen.getByTestId("lab-item")).toHaveTextContent("ไม่มีค่า");
    expect(screen.queryByTestId("labs-normal")).toBeNull();
  });

  it("adds no new h1 or role=status and states the arrows are recorded-value changes only", () => {
    render(<CaseSummary data={base()} meds={meds} runId="r" />);
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText(/ไม่ใช่การประเมินทางคลินิก/)).toBeInTheDocument();
  });

  it("helpers: direction and lab flag handle nulls", () => {
    expect(vitalDirection(null, 5)).toBeNull();
    expect(vitalDirection(5, undefined)).toBeNull();
    expect(labFlag({ test: "t", value: 1, unit: "", ref_low: null, ref_high: null, resulted_at: "" })).toBe("unclassified");
    expect(labFlag({ test: "t", value: 1, unit: "", ref_low: 2, ref_high: null, resulted_at: "" })).toBe("low");
  });
});
