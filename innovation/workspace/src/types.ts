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
  attention?: AttentionSummary;
  events?: { fact: Fact }[];
};

export type DraftContent = {
  summary: string;
  evidence_ids: string[];
  outstanding: string[];
  differentials: unknown[];
};

export type Draft = {
  draft_id: string;
  draft_revision: number;
  case_revision: number;
  review_sequence: number;
  status: string;
  effective: boolean;
  content: DraftContent;
  snapshot: { evidence: Fact[] };
  versions: { draft_revision: number; content: DraftContent }[];
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
  role: "intake" | "physician" | "evaluator";
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

export const handoffLabels: Record<string, string> = {
  NO_DRAFT: "ยังไม่มีร่าง",
  PENDING: "รอตรวจ",
  CONFIRMED: "ยืนยันแล้ว",
  STALE: "ต้องตรวจใหม่",
  REJECTED: "ถูกปฏิเสธ",
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
