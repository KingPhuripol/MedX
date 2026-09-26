/** Voice intake API types and display labels (contract: /api/voice, slice s3). */
export type Speaker = "patient" | "relative" | "nurse";

export interface NextAction {
  action: "ask" | "handoff";
  field: string | null;
  utterance_id: string;
  utterance_th: string;
  reason: string | null;
  missing_fields: string[];
}

export interface Turn {
  turn_id: string;
  seq: number;
  speaker: "agent" | Speaker;
  text: string;
  started_at: string;
  ended_at: string;
}

export interface Fact {
  fact_id: string;
  field: string;
  state: "KNOWN" | "UNKNOWN" | "REFUSED";
  value: string | number | string[] | null;
  span_turn_ids: string[];
  available_at_time: string;
}

export interface FieldStatus {
  field: string;
  status: "MISSING" | "KNOWN" | "UNKNOWN" | "REFUSED";
  times_asked: number;
  not_elicited: boolean;
}

export interface SessionState {
  session: { session_id: string; patient_ref: string; status: string; extraction_error: boolean; nurse_attention: boolean };
  turns: Turn[];
  facts: Fact[];
  field_statuses: FieldStatus[];
  next_action: NextAction;
}

export interface FinishResult {
  handoff_reason: string;
  missing_fields: string[];
  evidence: unknown[];
}

export const SPEAKER_LABELS: Record<Turn["speaker"], string> = {
  agent: "Agent",
  patient: "Patient",
  relative: "Relative",
  nurse: "Nurse",
};

export const FIELD_LABELS: Record<string, string> = {
  chief_complaint: "Chief complaint (symptom category)",
  onset_duration: "Onset / duration",
  severity: "Severity",
  allergy_status: "Drug allergy status",
  allergens: "Allergens (as said)",
  current_medications: "Current medications (as said)",
  relevant_history: "Relevant history (as said)",
};

export const REASON_LABELS: Record<string, string> = {
  complete: "All intake fields answered",
  attempts_exhausted: "Some fields were not elicited after two attempts",
  nurse_attention_phrase: "Attention phrase heard — nurse to review now",
  extraction_unavailable: "Extraction unavailable — nurse to continue manually",
  finished_by_nurse: "Finished by nurse",
};

/** Human-readable value. Only explicit KNOWN answers carry a value; MISSING never appears as a fact. */
export function displayValue(fact: Fact): string {
  if (fact.state !== "KNOWN") return "—";
  if (Array.isArray(fact.value)) return fact.value.length ? fact.value.join(", ") : "none reported";
  if (fact.field === "allergy_status" && fact.value === "none") return "none (patient denies drug allergy)";
  return String(fact.value);
}
