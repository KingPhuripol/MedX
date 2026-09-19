// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Review, Proposals } from "./main";
afterEach(cleanup);
const fact = {
  event_id: "a",
  kind: "HISTORY",
  state: "KNOWN",
  value: "original",
  observed_at: "2026-09-12T00:00:00Z",
  available_at_time: "2026-09-12T00:00:00Z",
  supersedes_event_id: null,
  source: "STAFF_CONFIRMED",
};
const content = {
  summary: "Original summary",
  evidence_ids: ["a"],
  outstanding: [],
  differentials: [],
  urgency: { level: "INSUFFICIENT_INFORMATION", confidence: null, evidence_ids: ["a"] },
  care_pathways: [{ code: "CLINICIAN_ASSESSMENT", rank: 1, confidence: null, evidence_ids: ["a"] }],
  next_information: [{ information_type: "VITAL", rank: 1, reason_code: "DECLARED_INFORMATION_GAP", waiting_is_unsafe: false }],
  uncertainty: { confidence: null, calibrated: false, abstained: true, escalation_required: false, reasons: ["Mock only"] },
  limitations: ["Synthetic only"],
};
const screening = {
  policy_version: "safety-policy-v1",
  urgency_floor: "URGENT_REVIEW",
  red_flags: [
    { code: "REQUIRED_INFORMATION_INCOMPLETE", state: "TRIGGERED" as const, evidence_ids: [] },
  ],
  applied_rules: ["SCR-001-REQUIRED_INFORMATION_INCOMPLETE"],
  missing_required: ["CHIEF_COMPLAINT", "VITAL"],
  limitations: [],
};
const draft = {
  draft_id: "d",
  draft_revision: 1,
  case_revision: 1,
  review_sequence: 0,
  status: "PENDING_REVIEW",
  effective: false,
  content,
  screen: screening,
  snapshot: { evidence: [fact], decision_time: "2026-09-12T00:00:00Z", timepoint: "T0" as const },
  provenance: { provider: "mock-v2", model: "deterministic-extractive-v1" },
  versions: [{ draft_revision: 1, content }],
};
it("blocks approval while edits are unsaved, then sends actual modified content", () => {
  const act = vi.fn().mockResolvedValue(undefined);
  render(
    <Review
      draft={draft}
      revision={1}
      canReview
      act={act}
      onDirty={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "แก้ไขข้อความ" }));
  fireEvent.change(screen.getByLabelText("ข้อความสรุป"), {
    target: { value: "Corrected summary" },
  });
  const confirm = screen.getByRole("button", { name: "ยืนยันร่างฉบับนี้" }) as HTMLButtonElement;
  expect(confirm.disabled).toBe(true);
  fireEvent.click(confirm);
  expect(act).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText(/เหตุผล/), { target: { value: "Correction" } });
  fireEvent.click(screen.getByText("บันทึกเป็นฉบับใหม่"));
  expect(act.mock.calls[0][1].content.summary).toBe("Corrected summary");
  expect(act.mock.calls[0][1].action).toBe("MODIFY");
});
it("blocks stale review and keeps snapshot evidence visible", () => {
  render(
    <Review
      draft={draft}
      revision={2}
      canReview
      act={vi.fn()}
      onDirty={() => {}}
    />,
  );
  expect(
    (screen.getByRole("button", { name: "ยืนยันร่างฉบับนี้" }) as HTMLButtonElement).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByText("ดูหลักฐานที่ร่างนี้ใช้ (1)"));
  expect(screen.getByText("original")).toBeTruthy();
});
it("accepts two proposals together and preserves structured values", () => {
  const act = vi.fn().mockResolvedValue(undefined);
  const measurement = {
    ...fact,
    event_id: "b",
    value: { name: "temperature", value: 37, unit: "C" },
  };
  render(
    <Proposals
      run={{
        run_id: "r",
        case_revision: 1,
        status: "COMPLETED",
        response: "",
        user_text: "",
        proposals: [
          { proposal_id: "p1", fact, requires_confirmation: true } as any,
          { proposal_id: "p2", fact: measurement },
        ],
      }}
      revision={1}
      act={act}
    />,
  );
  fireEvent.click(screen.getByText("ยืนยันข้อมูลที่เลือก 2 รายการ"));
  expect(act.mock.calls[0][1].proposals).toHaveLength(2);
  expect(act.mock.calls[0][1].proposals[1].fact.value).toEqual(
    measurement.value,
  );
});

it("shows the deterministic screen above the model summary and can escalate", () => {
  const act = vi.fn().mockResolvedValue(undefined);
  render(<Review draft={draft} revision={1} canReview act={act} onDirty={() => {}} />);
  // The finding must be readable without color: text carries urgency and flag state.
  expect(screen.getByText(/ต้องให้แพทย์ดูโดยเร็ว/)).toBeTruthy();
  expect(screen.getByText("ข้อมูลที่จำเป็นยังไม่ครบ")).toBeTruthy();
  expect(screen.getByText("งดสรุปผลอัตโนมัติ")).toBeTruthy();
  expect(screen.getByText(/ประเมินโดยแพทย์/)).toBeTruthy();
  expect(screen.getAllByText(/สัญญาณชีพ/).length).toBeGreaterThan(0);

  fireEvent.change(screen.getByLabelText(/เหตุผล/), { target: { value: "ต้องให้แพทย์อีกท่านดู" } });
  fireEvent.click(screen.getByText("ส่งต่อให้ทบทวน"));
  expect(act.mock.calls[0][1].action).toBe("ESCALATE");
});

it("records a structured reason when requesting more information", () => {
  const act = vi.fn().mockResolvedValue(undefined);
  render(<Review draft={draft} revision={1} canReview act={act} onDirty={() => {}} />);
  fireEvent.change(screen.getByLabelText("หมวดการตัดสินใจ"), { target: { value: "MISSING_INFORMATION" } });
  fireEvent.change(screen.getByLabelText(/รายละเอียดเหตุผล/), { target: { value: "ต้องวัดสัญญาณชีพ" } });
  fireEvent.click(screen.getByText("ขอข้อมูลเพิ่มเติม"));
  expect(act.mock.calls[0][1].action).toBe("REQUEST_INFORMATION");
  expect(act.mock.calls[0][1].reason_code).toBe("MISSING_INFORMATION");
});

it("says so when a draft predates the screen instead of implying it passed", () => {
  render(<Review draft={{ ...draft, screen: null }} revision={1} canReview act={vi.fn()} onDirty={() => {}} />);
  expect(screen.getByText(/ไม่มีผลคัดกรองกำกับ/)).toBeTruthy();
});

it("does not rewrite stored clinical text that the reviewer never edited", () => {
  // The edit surface renders Thai labels over machine values. Sending the humanized
  // string back would silently replace HISTORY with ประวัติ in stored content on every
  // MODIFY. Only the field the reviewer actually changed may be sent.
  const coded = {
    ...content,
    summary: "HISTORY: ไอสองวัน",
    outstanding: ["HISTORY", "MEDICATION"],
  };
  const act = vi.fn().mockResolvedValue(undefined);
  render(
    <Review draft={{ ...draft, content: coded, versions: [{ draft_revision: 1, content: coded }] }}
      revision={1} canReview act={act} onDirty={() => {}} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "แก้ไขข้อความ" }));

  // The outstanding editor must not show raw enum codes to a clinician.
  const outstandingBox = screen.getByLabelText(/งานค้าง/) as HTMLTextAreaElement;
  expect(outstandingBox.value).toBe("ประวัติ\nยาที่ใช้");

  // Edit the summary only; outstanding is untouched and must go back as stored codes.
  fireEvent.change(screen.getByLabelText("ข้อความสรุป"), { target: { value: "แก้แล้ว" } });
  fireEvent.change(screen.getByLabelText(/เหตุผล/), { target: { value: "ตรวจแก้ร่าง" } });
  fireEvent.click(screen.getByText("บันทึกเป็นฉบับใหม่"));

  const sent = act.mock.calls[0][1].content;
  expect(sent.summary).toBe("แก้แล้ว");
  expect(sent.outstanding).toEqual(["HISTORY", "MEDICATION"]);
});

it("says why confirming is unavailable instead of only disabling the button", () => {
  render(<Review draft={draft} revision={2} canReview act={vi.fn()} onDirty={() => {}} />);
  expect(screen.getByText(/ต้องสร้างหรือตรวจร่างฉบับล่าสุดก่อน/)).toBeTruthy();
});
