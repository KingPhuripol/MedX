/** Types and copy for the nurse triage pages (slice s4). Mirrors the /api/triage responses. */

export const OUTPUT_LABEL = "Suggestion for nurse review";

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

export type NotEvaluable = { rule_id: string; name_en: string; name_th: string; missing_inputs: string[] };

export type DepartmentEntry = {
  code: string;
  label_th: string;
  label_en: string;
  score: number;
  evidence_refs: string[];
};

export type DepartmentSuggestion = {
  status: "suggested" | "abstained" | "error";
  top3: DepartmentEntry[];
  uncertainty: "low" | "medium" | "high" | null;
  uncertainty_label: string;
  missing_information: string[];
  reason: string | null;
};

export type Review = {
  action: "confirm" | "edit" | "reject";
  final_department: string | null;
  reviewer_id: number;
  reviewer_role: string;
  ts_utc: string;
  acknowledged_alert_ids: string[];
};

export type Assessment = {
  assessment_id: string;
  case_ref: string;
  as_of: string;
  ruleset_version: string;
  alerts: Alert[];
  not_evaluable: NotEvaluable[];
  escalation_required: boolean;
  department: DepartmentSuggestion;
  review_status: "pending_review" | "confirmed" | "edited" | "rejected";
  confirmed_department: string | null;
  output_label: string;
  review?: Review | null;
};

export type Department = { code: string; label_th: string; label_en: string };
export type CaseItem = { case_ref: string; chief_complaint: string | null; suggested_as_of: string };
export type ReviewAction = "confirm" | "edit" | "reject";
export type ReviewBody = { department_code?: string; reason?: string; acknowledged_alert_ids: string[] };

export const ERROR_TEXT: Record<string, string> = {
  alerts_not_acknowledged: "Acknowledge every red-flag alert before reviewing.",
  already_reviewed: "This assessment has already been reviewed.",
  department_not_in_top3: "Choose one of the suggested departments, or use Edit.",
  unknown_department: "Choose a department from the list.",
  reason_required: "A reason is required.",
};

export async function postJson(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
}
