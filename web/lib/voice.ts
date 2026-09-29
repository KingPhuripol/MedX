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
  session: {
    session_id: string;
    patient_ref: string;
    status: string;
    extraction_error: boolean;
    nurse_attention: boolean;
    allergy_conflict?: boolean;
  };
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

type SourceKind = "patient" | "relative" | "other";

/** Who a negative came from. Only a patient or relative answer is a denial; a nurse statement is not. */
function negativeSource(speakers: Turn["speaker"][]): SourceKind {
  const set = new Set(speakers);
  if (set.size === 1 && set.has("patient")) return "patient";
  if (set.size === 1 && set.has("relative")) return "relative";
  return "other";
}

const NO_ALLERGY: Record<SourceKind, string> = {
  patient: "none (patient denies drug allergy)",
  relative: "none (relative reports no drug allergy)",
  other: "none (stated by nurse, not the patient; confirm with patient)",
};
const EMPTY_LIST: Record<SourceKind, string> = {
  patient: "none reported",
  relative: "none reported (by relative)",
  other: "none (stated by nurse, not the patient; confirm with patient)",
};

/**
 * Human-readable value. Only explicit KNOWN answers carry a value; MISSING never appears as a fact.
 * `speakers` are the speakers of the fact's source turns, taken from the transcript.
 */
export function displayValue(fact: Fact, speakers: Turn["speaker"][] = []): string {
  if (fact.state !== "KNOWN") return "—";
  const source = negativeSource(speakers);
  if (Array.isArray(fact.value)) return fact.value.length ? fact.value.join(", ") : EMPTY_LIST[source];
  if (fact.field === "allergy_status" && fact.value === "none") return NO_ALLERGY[source];
  return String(fact.value);
}
