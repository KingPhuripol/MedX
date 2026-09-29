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
export type CaseOverview = {
  run_id: string;
  case_id: string;
  display_name: string;
  data_class: "synthetic";
  stage: string;
  owner: { role: Role; display: string };
  safety: { level: string; label: string; detail: string; acknowledged: boolean };
  next_action: string;
  demographics: { age: number; sex: string; hn: string };
  summary: string;
  intake: Record<string, string>;
  triage: { suggestion: string; department: string; confidence: string; evidence_ids: string[] };
  care: { status: string; suggestion: string; evidence_ids: string[] };
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
export const CASE_ID = "SYN-2026-0017";
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
