export type Role = "nurse" | "physician" | "pharmacist";
export type User = { id: number; username: string; role: Role; home: string };
export type DemoRun = {
  run_id: string;
  journey_id: string;
  data_class: "synthetic";
  timestamp: string;
  version: number;
};
export type TaskSummary = {
  task_id: string;
  case_id: string;
  role: Role;
  kind: string;
  label: string;
  priority: "critical" | "warning";
  status: string;
  owner: null | { id: number; role: Role };
  stage: string;
  safety_state: string;
  next_action: string;
  version: number;
};
/** A null field is missing/not recorded. It is never 0 and never normal. */
export type VitalReading = {
  observed_at: string;
  available_at_time: string;
  evidence_id?: string;
  hr: number | null;
  rr: number | null;
  sbp: number | null;
  dbp: number | null;
  spo2: number | null;
  temp_c: number | null;
  consciousness: string | null;
  on_oxygen: boolean | null;
};
export type LabResult = {
  test: string;
  value: number | null;
  unit: string;
  ref_low: number | null;
  ref_high: number | null;
  resulted_at: string;
  available_at_time?: string;
};
export type RedFlagEngine = {
  engine: string;
  ruleset_version: string;
  rules_total: number;
  alerts: { rule_id: string; name_th: string; message_th: string; evidence_refs: string[] }[];
  /** Rules that could not be checked. Never a negative result. */
  not_evaluated: { rule_id: string; name_th: string; missing_inputs: string[]; reason_th: string }[];
  not_evaluated_text: string;
};
export type PharmaEngine = {
  engine: string;
  pipeline_version: string;
  rules_version: string;
  formulary_version: string;
  issue_count: number;
  notice_count: number;
  unchecked_comparisons: number;
};
/** A case row in the queue (all served cases, red flags first). */
export type QueueCase = {
  case_id: string;
  display_name: string;
  view_only: boolean;
  data_class?: string;
  safety_level: "critical" | "none";
  safety_label: string;
  alert_count: number;
  /** null when the case has no engine run (the seeded workflow case). */
  not_evaluated_count: number | null;
  age: number;
  sex: string;
  chief_complaint: string;
};
export type CaseOverview = {
  run_id: string;
  case_id: string;
  display_name: string;
  data_class: "synthetic";
  stage: string;
  owner: { role: Role; display: string };
  safety: { level: "critical" | "none" | string; label: string; detail: string; acknowledged: boolean };
  next_action: string;
  demographics: { age: number; sex: string; hn: string };
  summary: string;
  intake: Record<string, string>;
  triage?: { suggestion: string; department: string; confidence: string; evidence_ids: string[] };
  care?: { status: string; suggestion: string; evidence_ids: string[] };
  /** U7: fixture cases are read-only; workflow actions exist only for the seeded case. */
  view_only?: boolean;
  view_only_label?: string;
  engines?: { red_flag: RedFlagEngine; pharma: PharmaEngine };
  decision_time?: string;
  vitals?: VitalReading[];
  /** [] = no known allergy recorded; null/undefined = allergy status unknown. */
  allergies?: { substance: string; reaction: string }[] | null;
  labs?: LabResult[];
  timestamp: string;
  version: number;
};
export type TimelineItem = {
  event_id: string;
  kind: string;
  title: string;
  detail: string;
  actor: { role: string; display?: string };
  timestamp: string;
  version: number;
};
export type MedicationData = {
  view_only?: boolean;
  engine?: PharmaEngine;
  sources: { source_id: string; label: string; recorded_value: string; captured_at: string }[];
  discrepancies: {
    review_id: string;
    type: string;
    label: string;
    detail: string;
    status: string;
    provenance: string[];
    version: number;
  }[];
};
export const RUN_KEY = "medx.demo.run";
/** The one case with a full workflow (claim, review, handoff). Every other served case is view-only. */
export const WORKFLOW_CASE_ID = "SYN-2026-0017";
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || "โหลดข้อมูลไม่สำเร็จ") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function formatThaiTime(value: string) {
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Bangkok" }).format(
    new Date(value),
  );
}
