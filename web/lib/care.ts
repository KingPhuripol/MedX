/** Types and copy for the physician care pages (slice s6). Mirrors the /api/care responses. */

export const OUTPUT_LABEL = "Suggestion for physician review — research prototype";

export type EvidenceRef = { item_id: string; data_type: string; available_at_time: string };

export type Alert = {
  rule_id: string;
  ruleset_version: string;
  name_en: string;
  name_th: string;
  severity: "escalate";
  evidence_refs: string[];
  message_en: string;
  message_th: string;
};

export type ScreeningStatus = "evaluated" | "partially_evaluated" | "not_evaluated" | "unavailable";

export type Screening = {
  status: ScreeningStatus;
  performed: boolean;
  banner: string | null;
  rules_evaluated: string[];
  rules_not_evaluated: string[];
  missing_inputs: string[];
};

export type SummaryLine = { text: string; evidence_refs: EvidenceRef[] };
export type NextInfo = {
  code: string;
  kind: string;
  display: string;
  display_th: string;
  evidence_refs: EvidenceRef[];
  source_refs: string[];
};
export type PathwayOption = Omit<NextInfo, "kind">;
export type Codes = { next_information: string[]; pathway_options: string[] };

export type Review = {
  action: ReviewAction;
  final_codes: Codes | null;
  reviewer_id: number;
  reviewer_role: string;
  ts_utc: string;
  acknowledged_alert_ids: string[];
  screening_acknowledged: boolean;
  reason_sha256: string | null;
};

export type Assessment = {
  alerts: Alert[];
  red_flag_screening: Screening;
  escalation_required: boolean;
  status: "suggested" | "abstained" | "error";
  case_summary: SummaryLine[];
  next_information: NextInfo[];
  pathway_options: PathwayOption[];
  missing_information: string[];
  uncertainty: string;
  reason: string | null;
  provider: string | null;
  model_version: string | null;
  contract_version: string | null;
  rules_version: string;
  as_of: string;
  decision_point: "T1" | "T2";
  case_id: string;
  output_label: string;
  assessment_id: string;
  created_at: string;
  review_status: "pending_review" | "confirmed" | "edited" | "rejected";
  review: Review | null;
};

export type VocabEntry = { code: string; display: string; display_th: string };
export type Vocabulary = { next_information: VocabEntry[]; pathway_options: VocabEntry[] };
export type CaseItem = { case_id: string; decision_points: { decision_point: "T1" | "T2"; as_of: string }[] };
export type ReviewAction = "confirm" | "edit" | "reject";
export type ReviewBody = {
  acknowledged_alert_ids: string[];
  screening_acknowledged: boolean;
  reason?: string;
  next_information?: string[];
  pathway_options?: string[];
};

export const ERROR_TEXT: Record<string, string> = {
  alerts_not_acknowledged: "Acknowledge every red-flag alert before reviewing.",
  screening_not_acknowledged: "Acknowledge the red-flag screening banner before reviewing.",
  already_reviewed: "This assessment has already been reviewed.",
  reason_required: "A reason is required.",
  codes_required: "Choose at least one item.",
  code_outside_vocabulary: "Choose items from the list.",
  too_many_codes: "Choose at most 5 next-information items and 3 pathway options.",
  nothing_to_confirm: "There is no suggestion to confirm. Use Edit or Reject.",
};

export function refText(r: EvidenceRef): string {
  return `${r.item_id} (${r.data_type}, available ${r.available_at_time})`;
}

export async function postJson(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
}
