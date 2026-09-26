/** Pharma Agent (s5) client types and copy. The UI reads snapshots; it never edits orders. */

export const NLM_ATTRIBUTION =
  "This product uses publicly available data from the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product.";

export const PHRASING_LABEL = "Rules primary / model phrasing supplementary / mock";

export const REVIEW_NOTE =
  "Issues are suggestions for pharmacist review. The agent compares medication lists only and never changes an order.";

export const TYPE_LABELS: Record<string, string> = {
  allergy_direct: "Allergy: direct match",
  allergy_class: "Allergy: drug class",
  allergy_cross_reactivity: "Allergy: possible cross-reactivity",
  duplication_ingredient: "Duplicate ingredient",
  duplication_class: "Same-class duplication",
  dose_mismatch: "Dose differs between sources",
  frequency_mismatch: "Frequency differs between sources",
  omission: "Home medicine not in new order",
};

export const NOTICE_LABELS: Record<string, string> = {
  unrecognised_drug: "Unrecognised medicine name",
  allergy_unmapped: "Allergy not mapped",
  source_unreadable: "Source could not be read",
  source_missing: "Order source missing",
  missing_field: "Not stated, so not compared",
};

export const NOT_STATED = "not stated";

export const SOURCE_LABELS: Record<string, string> = {
  home_list: "Home list",
  patient_reported: "Patient-reported list",
  new_order: "New order",
  allergy_record: "Allergy record",
};

export type Fixture = { fixture_ref: string; patient_ref: string; split: string; label: string };

export type ConflictingSource = {
  source_type: string;
  evidence_ref: string;
  available_at_time: string;
  raw_span: string;
  presence?: "present" | "absent";
  dose_value?: number | null;
  dose_unit?: string | null;
  frequency_code?: string | null;
};

export type Issue = {
  issue_id: string;
  run_id: string;
  type: string;
  severity: string;
  severity_rank: number;
  rule_id: string;
  ingredients: string[];
  conflicting_sources: ConflictingSource[];
  unverifiable?: boolean;
  possible_substitution?: boolean;
  phrasing: { text: string; source: string; provider: string; model_version: string; fallback_reason?: string | null };
  status: "open" | "confirmed" | "dismissed";
  decision?: { decision: string; reason: string | null; reviewer_role: string; ts_utc: string } | null;
};

export type Notice = {
  notice_id: string;
  type: string;
  source_type?: string | null;
  evidence_ref?: string | null;
  raw_span?: string | null;
  detail: string;
  field?: "dose" | "frequency_code" | null;
  ingredients?: string[] | null;
};

export type ExtractedEntry = {
  source_text: string;
  drug_name_raw: string;
  dose_value: number | null;
  dose_unit: string | null;
  route: string | null;
  frequency_code: string | null;
  ingredients: string[];
  recognised: boolean;
  discontinue_intent: boolean;
};

export type ExtractionRecord = {
  source_index: number;
  source_type: string;
  evidence_ref: string;
  available_at_time: string;
  status: "ok" | "extraction_failed";
  failure_reason: string | null;
  entries: ExtractedEntry[] | null;
};

export type Run = {
  run_id: string;
  patient_ref: string;
  as_of: string;
  mode: string;
  status: "complete" | "incomplete";
  formulary_version: string;
  rules_version: string;
  excluded_future_items: number;
  unchecked_comparisons?: number;
  extraction?: ExtractionRecord[];
  issues: Issue[];
  notices: Notice[];
};

export function isAllergy(issue: Issue): boolean {
  return issue.type.startsWith("allergy_");
}

/** Severity order is fixed by rule; allergy issues always come first and are never filtered out. */
export function sortIssues(issues: Issue[]): Issue[] {
  return [...issues].sort((a, b) => a.severity_rank - b.severity_rank);
}

export function formatDose(src: Pick<ConflictingSource, "presence" | "dose_value" | "dose_unit">): string {
  if (src.presence === "absent") return "—";
  if (src.dose_value === null || src.dose_value === undefined) return NOT_STATED;
  return `${src.dose_value} ${src.dose_unit ?? ""}`.trim();
}

/** A field the source did not state is shown as "not stated", never as blank or as a match. */
export function orNotStated(value: string | null | undefined): string {
  return value === null || value === undefined || value === "" ? NOT_STATED : value;
}

export function uncheckedSummary(run: Pick<Run, "unchecked_comparisons">): string {
  const n = run.unchecked_comparisons ?? 0;
  if (n === 0) return "Every dose and frequency present in two or more lists could be compared.";
  return `${n} comparison(s) could not be checked because a dose or frequency was not stated in one list. These are not counted as matches; see the notices and the lists below.`;
}
