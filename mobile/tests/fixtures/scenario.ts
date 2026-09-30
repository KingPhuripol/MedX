/**
 * Contract-shaped builders over the JSON fixtures (v2a §3 / v2t §3). Used by vitest and Playwright.
 * Synthetic data only; values mirror the approved comps.
 */
import start from "./voice-session-start.json";

export const ASK = [
  "chief_complaint",
  "onset_duration",
  "severity",
  "allergy_status",
  "current_medications",
  "relevant_history",
] as const;

export const QUESTIONS: Record<string, string> = {
  "ask.chief_complaint": "วันนี้มีอาการอะไรมาคะ",
  "ask.onset_duration": "มีอาการนี้มานานเท่าไรแล้วคะ",
  "ask.severity": "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ",
  "ask.allergy_status": "เคยแพ้ยาอะไรไหมคะ",
  "ask.current_medications": "ตอนนี้ใช้ยาอะไรอยู่บ้างไหมคะ",
  "ask.relevant_history": "มีโรคประจำตัวหรือเคยเจ็บป่วยอะไรมาก่อนไหมคะ",
};

type Status = "MISSING" | "KNOWN" | "UNKNOWN" | "REFUSED";

export function statuses(known: Partial<Record<string, Status>> = {}, notElicited: string[] = []) {
  return ASK.map((field) => ({
    field,
    status: known[field] ?? "MISSING",
    times_asked: 0,
    not_elicited: notElicited.includes(field),
  }));
}

export function nextAction(st: ReturnType<typeof statuses>, override?: { kind: "handoff"; reason: string }) {
  const missing = st.filter((s) => s.status === "MISSING").map((s) => s.field);
  if (override) {
    return { kind: override.kind, field: null, suggested_question_id: null, suggested_question_th: null, reason: override.reason, missing_fields: missing };
  }
  if (!missing.length) {
    return { kind: "complete", field: null, suggested_question_id: null, suggested_question_th: null, reason: "complete", missing_fields: [] };
  }
  const id = `ask.${missing[0]}`;
  return { kind: "prompt_nurse", field: missing[0], suggested_question_id: id, suggested_question_th: QUESTIONS[id], reason: null, missing_fields: missing };
}

export function session(p: Partial<typeof start.session> & { patient_ref?: string } = {}) {
  return { ...start.session, ...p };
}

let seq = 0;
export function fact(field: string, value: unknown, valueText: string, turnId: string, state: "KNOWN" | "UNKNOWN" | "REFUSED" = "KNOWN") {
  seq += 1;
  return {
    fact_id: `vf_${String(seq).padStart(4, "0")}`,
    session_id: start.session.session_id,
    field,
    state,
    value,
    value_text: valueText,
    span_turn_ids: [turnId],
    event_time: "2026-09-30T10:31:00+07:00",
    available_at_time: "2026-09-30T10:31:05+07:00",
    extractor: "mock_rules",
    provider: "mock",
    model_version: "mock-0",
    request_sha256: "0".repeat(64),
    supersedes_fact_id: null,
  };
}

export function turn(turnId: string, text: string, startedAt: string, endedAt = startedAt) {
  return { turn_id: turnId, session_id: start.session.session_id, seq: 0, speaker: "unknown", text, started_at: startedAt, ended_at: endedAt };
}

export interface TurnOpts {
  turnId: string;
  text: string;
  startedAt?: string;
  facts?: ReturnType<typeof fact>[];
  known: Partial<Record<string, Status>>;
  nurseAttention?: boolean;
  handoff?: string;
  sessionPatch?: Record<string, unknown>;
  notElicited?: string[];
}

export function turnResponse(o: TurnOpts) {
  const st = statuses(o.known, o.notElicited);
  const next = o.nurseAttention
    ? nextAction(st, { kind: "handoff", reason: "nurse_attention_phrase" })
    : o.handoff
      ? nextAction(st, { kind: "handoff", reason: o.handoff })
      : nextAction(st);
  const at = o.startedAt ?? "2026-09-30T10:31:00+07:00";
  return {
    turn: turn(o.turnId, o.text, at, at),
    new_facts: o.facts ?? [],
    field_statuses: st,
    next_action: next,
    nurse_attention: !!o.nurseAttention,
    extraction_error: o.handoff === "extraction_unavailable",
    chief_complaint_conflict: false,
    session: session({ nurse_attention: !!o.nurseAttention, extraction_error: o.handoff === "extraction_unavailable", ...o.sessionPatch }),
  };
}

export function startResponse(patientRef = "SYN-2026-0023") {
  const st = statuses();
  return { session: session({ patient_ref: patientRef }), next_action: nextAction(st), field_statuses: st };
}

/** GET session payload for the review comp (04-review): six captured fields with their source turns. */
export function reviewSession() {
  const turns = [
    turn("vt_1", "ปวดท้องใต้ลิ้นปี่ ปวดบิดค่ะ", "2026-09-30T10:30:40+07:00"),
    turn("vt_2", "เริ่มเมื่อคืนค่ะ ประมาณวันนึง", "2026-09-30T10:31:30+07:00"),
    turn("vt_3", "น่าจะเจ็ดค่ะ", "2026-09-30T10:32:10+07:00"),
    turn("vt_4", "เคยกินอะม็อกซี่แล้วผื่นขึ้นทั้งตัวค่ะ", "2026-09-30T10:34:05+07:00"),
    turn("vt_5", "ความดันสูงค่ะ กินยาทุกเช้า", "2026-09-30T10:35:12+07:00"),
    turn("vt_6", "กินยาลดกรดอยู่ค่ะ จำชื่อยาไม่ได้", "2026-09-30T10:36:02+07:00"),
  ];
  const facts = [
    fact("chief_complaint", "abdominal_pain", "ปวดท้องใต้ลิ้นปี่ ปวดบิด", "vt_1"),
    fact("onset_duration", "P1D", "ประมาณ 1 วัน (เริ่มเมื่อคืน)", "vt_2"),
    fact("severity", 7, "7 จาก 10", "vt_3"),
    fact("allergy_status", "present", "แพ้ยา", "vt_4"),
    fact("allergens", ["amoxicillin"], "แพ้อะม็อกซีซิลลิน (ผื่นขึ้นทั้งตัว)", "vt_4"),
    fact("current_medications", ["ยาลดกรด"], "ยาลดกรด", "vt_6"),
    fact("relevant_history", ["hypertension"], "ความดันโลหิตสูง", "vt_5"),
  ];
  const st = statuses(Object.fromEntries(ASK.map((f) => [f, "KNOWN"])));
  return { session: session(), turns, facts, field_statuses: st, next_action: nextAction(st), held_facts: [] };
}
