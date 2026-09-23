export type FactValue = string | number | Record<string, unknown> | null;

export type Fact = {
  event_id: string;
  kind: string;
  state: string;
  value: FactValue;
  observed_at: string;
  available_at_time: string;
  supersedes_event_id: string | null;
  source: string;
  conflicts_with_event_ids?: string[];
};

export type AttentionSummary = {
  pending_proposal_count: number;
  active_job_status: string | null;
  stale_draft: boolean;
  needs_attention: boolean;
};

export type Case = {
  encounter_id: string;
  age: number;
  case_revision: number;
  handoff_status?: string;
  journey_stage?: string;
  escalation?: string[];
  attention?: AttentionSummary;
  events?: { fact: Fact }[];
};

export type DraftContent = {
  summary: string;
  evidence_ids: string[];
  outstanding: string[];
  differentials: unknown[];
  urgency?: {
    level: string;
    confidence: number | null;
    evidence_ids: string[];
  };
  care_pathways?: {
    code: string;
    rank: number;
    confidence: number | null;
    evidence_ids: string[];
    rationale?: string | null;
  }[];
  next_information?: {
    information_type: string;
    rank: number;
    reason_code: string;
    waiting_is_unsafe: boolean;
  }[];
  uncertainty?: {
    confidence: number | null;
    calibrated: boolean;
    abstained: boolean;
    escalation_required: boolean;
    reasons: string[];
  };
  limitations?: string[];
};

export type RedFlag = {
  code: string;
  state: "TRIGGERED" | "NOT_TRIGGERED" | "UNKNOWN";
  evidence_ids: string[];
};

/** Deterministic pre-inference screen. The service computes it; no client may set it. */
export type SafetyScreen = {
  policy_version: string;
  urgency_floor: string;
  red_flags: RedFlag[];
  applied_rules: string[];
  missing_required: string[];
  limitations: string[];
};

export type Draft = {
  draft_id: string;
  draft_revision: number;
  case_revision: number;
  review_sequence: number;
  status: string;
  effective: boolean;
  content: DraftContent;
  screen: SafetyScreen | null;
  snapshot: { evidence: Fact[]; decision_time?: string; timepoint?: "T0" | "T1" };
  provenance?: Record<string, unknown>;
  versions: { draft_revision: number; content: DraftContent }[];
};

export type AuditEvent = {
  event: string;
  encounter_id: string;
  actor: string;
  role: string;
  recorded_at: string;
  [key: string]: unknown;
};

export type Run = {
  run_id: string;
  encounter_id?: string;
  case_revision: number;
  status: string;
  response: string;
  user_text: string;
  proposals: { proposal_id?: string; fact: Fact }[];
  error_code?: string;
  trace?: { sequence: number; tool: string; status: "COMPLETED" | "FAILED" | "BLOCKED"; elapsed_ms: number; evidence_ids: string[] }[];
  provenance?: { model?: string; design?: { design_id?: string } };
};

export type Job = {
  job_id: string;
  encounter_id: string;
  status: string;
  result: Run | null;
  error_code: string | null;
};

export type Session = {
  subject: string;
  role: "intake" | "physician" | "pharmacist" | "evaluator";
  workspace: string;
  csrf: string;
};

export type Capability = {
  profile: string;
  role: Session["role"];
  provider: string;
  model: string;
  differential: boolean;
  speech: boolean;
  synthesis: boolean;
  conversation: boolean;
  validation: string;
};

export type ReadinessCapability = {
  configured: boolean;
  connectivity: "PASSED" | "NOT_VERIFIED";
  smoke: "PASSED" | "NOT_VERIFIED";
  evaluation: "PASSED" | "NOT_VERIFIED";
  checked_at?: string | null;
};

export type ReadinessReport = {
  reasoning: ReadinessCapability;
  transcription: ReadinessCapability;
  synthesis: ReadinessCapability;
  clinical_validation: string;
};

export const factKinds: Record<string, string> = {
  CHIEF_COMPLAINT: "อาการสำคัญ",
  HISTORY: "ประวัติ",
  MEDICATION: "ยาที่ใช้",
  ALLERGY: "การแพ้ยา",
  VITAL: "สัญญาณชีพ",
  LAB: "ผลตรวจ",
  REPORT: "รายงาน",
};

export const factStates: Record<string, string> = {
  KNOWN: "มีข้อมูล",
  UNKNOWN: "ผู้ป่วยไม่ทราบ",
  REFUSED: "ผู้ป่วยไม่สะดวกตอบ",
  NOT_AVAILABLE: "ยังไม่มีข้อมูล",
};

export const urgencyLabels: Record<string, string> = {
  IMMEDIATE_REVIEW: "ต้องให้แพทย์ดูทันที",
  URGENT_REVIEW: "ต้องให้แพทย์ดูโดยเร็ว",
  ROUTINE_REVIEW: "ให้แพทย์ดูตามคิวปกติ",
  INSUFFICIENT_INFORMATION: "ข้อมูลยังไม่พอสรุป",
};

export const redFlagLabels: Record<string, string> = {
  REQUIRED_INFORMATION_INCOMPLETE: "ข้อมูลที่จำเป็นยังไม่ครบ",
  COMPLAINT_NOT_EVALUATED_BY_RULE: "ยังไม่มีกฎอ่านอาการสำคัญนี้",
  OUT_OF_SCOPE_PRESENTATION: "เคสอยู่นอกขอบเขตที่ประเมินไว้",
};

export const pathwayLabels: Record<string, string> = {
  CLINICIAN_ASSESSMENT: "ประเมินโดยแพทย์",
  EMERGENCY_ASSESSMENT: "ประเมินฉุกเฉิน",
  SAME_DAY_URGENT_SERVICE: "บริการเร่งด่วนภายในวัน",
  SCHEDULED_OUTPATIENT_REVIEW: "นัดตรวจผู้ป่วยนอก",
  REQUEST_MORE_INFORMATION: "ขอข้อมูลเพิ่มเติม",
};

export const redFlagStates: Record<string, string> = {
  TRIGGERED: "เข้าเงื่อนไข",
  UNKNOWN: "ยังตอบไม่ได้",
  NOT_TRIGGERED: "ไม่เข้าเงื่อนไข",
};

export const handoffLabels: Record<string, string> = {
  NO_DRAFT: "ยังไม่มีร่าง",
  PENDING: "รอตรวจ",
  CONFIRMED: "ยืนยันแล้ว",
  STALE: "ต้องตรวจใหม่",
  REJECTED: "ถูกปฏิเสธ",
};

export const journeyLabels: Record<string, string> = {
  INTAKE: "รับข้อมูล",
  DOCTOR_REVIEW: "รอแพทย์",
  PHARMACY: "ห้องยา",
  PHARMACY_HOLD: "ห้องยา-พัก",
  AWAITING_DISPOSITION: "รอแพทย์ตัดสินใจ",
  DISPOSITION_HOME: "แพทย์ให้กลับบ้าน",
  DISPOSITION_REFER: "แพทย์ส่งต่อ",
  DISPOSITION_OBSERVE: "แพทย์ให้สังเกตอาการ",
};

export function humanizeClinicalText(value: string): string {
  return Object.entries({ ...factKinds, ...factStates, ...handoffLabels })
    .sort(([left], [right]) => right.length - left.length)
    .reduce((text, [code, label]) => text.replace(new RegExp(`\\b${code}\\b`, "g"), label), value);
}

export function displayFact(fact: Fact): string {
  if (fact.state !== "KNOWN") return factStates[fact.state] || "ยังไม่มีข้อมูล";
  if (typeof fact.value !== "object") return String(fact.value ?? "");
  if (fact.value && "name" in fact.value && "unit" in fact.value) {
    return `${String(fact.value.name)}: ${String(fact.value.value ?? "")} ${String(fact.value.unit)}`.trim();
  }
  return "ข้อมูลแบบมีโครงสร้าง";
}
