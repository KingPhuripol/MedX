"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { FIELD_LABELS_TH, REASON_LABELS_TH, type FinishResult, type SessionState } from "@/lib/voice";

import { FactRow } from "./FactSheet";

export function handoffHref(caseId: string | null, runId: string | null): string {
  return caseId && runId ? `/app/cases/${encodeURIComponent(caseId)}/triage?run=${encodeURIComponent(runId)}` : "/nurse/triage";
}

/** End-of-call summary: handoff reason, what is still missing, evidence count and the captured facts. */
export function Summary({ result, data }: { result: FinishResult; data: SessionState | null }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const facts = data?.facts ?? result.facts ?? [];
  const turns = data?.turns ?? [];
  const missing = result.missing_fields.map((f) => FIELD_LABELS_TH[f] ?? f);
  return (
    <section className="live-panel live-summary" data-testid="live-summary" aria-labelledby="live-summary-title">
      <h2 id="live-summary-title" ref={heading} tabIndex={-1}>
        สรุปการสนทนา
      </h2>
      <p>เหตุผลที่ส่งต่อ: {REASON_LABELS_TH[result.handoff_reason] ?? result.handoff_reason}</p>
      <p>หัวข้อที่ยังขาด: {missing.length ? missing.join(", ") : "ไม่มี"}</p>
      <p>หลักฐานที่บันทึก: {result.evidence.length} รายการ</p>
      {facts.length > 0 && (
        <ul className="live-facts live-facts--detail" aria-label="ข้อมูลที่กรอกแล้ว">
          {facts.map((f) => (
            <FactRow key={f.fact_id} fact={f} turns={turns} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function HandoffLink({ caseId, runId }: { caseId: string | null; runId: string | null }) {
  return (
    <Link className="ui-button ui-button--primary live-handoff" data-testid="live-handoff" href={handoffHref(caseId, runId)}>
      ส่งต่อให้พยาบาลตรวจ
    </Link>
  );
}
