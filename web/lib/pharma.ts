/** Pharma Agent (s5) client types and copy. The UI reads snapshots; it never edits orders. */

export const NLM_ATTRIBUTION =
  "This product uses publicly available data from the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product.";

export const PHRASING_LABEL = "Rules primary / model phrasing supplementary / mock";

export const REVIEW_NOTE =
  "Issues are suggestions for pharmacist review. The agent compares medication lists only and never changes an order.";

/** What the check compares and what it does not (C2). Shown before and after every run. */
export const SCOPE_COMPARED =
  "Compared across the lists: ingredient duplication, dose per administration (strength × quantity), frequency, omission from the new order, and recorded allergies.";
export const SCOPE_NOT_CHECKED = [
  "drug–drug interactions",
  "dose range",
  "renal or hepatic adjustment",
  "route",
];
export const SCOPE_READING =
  "The dose on each line is read by a fixed, listed grammar of strength and quantity forms. Any other dose form is shown as could not be verified, and a frequency the fixed patterns cannot read is shown as not stated or not recognised; neither is ever counted as a match. A phrase that fits the grammar can still be clinically wrong: for example, a dispensed count written as “2 tabs” is still read as 2 tablets per dose.";

export const TYPE_LABELS: Record<string, string> = {
  allergy_direct: "Allergy: direct match",
  allergy_class: "Allergy: drug class",
  allergy_cross_reactivity: "Allergy: possible cross-reactivity",
  duplication_ingredient: "Duplicate ingredient",
  duplication_class: "Same-class duplication",
  dose_mismatch: "Dose per administration differs between sources",
  frequency_mismatch: "Frequency differs between sources",
  missing_field: "Dose or frequency not stated",
  omission: "Home medicine not in new order",
};

export const NOTICE_LABELS: Record<string, string> = {
  unrecognised_drug: "Unrecognised medicine name",
  allergy_unmapped: "Allergy not mapped",
  source_unreadable: "Source could not be read",
  source_missing: "Order source missing",
};

export const NOT_STATED = "not stated";
export const NOT_RECOGNISED = "not recognised";

export const UNVERIFIABLE_REASONS: Record<string, string> = {
  variable_regimen: "variable regimen",
  liquid_volume: "liquid volume",
  multiple_strengths: "more than one strength",
  range: "a range or alternative between two amounts",
  ambiguous_quantity: "conflicting quantities",
  unparsed_token: "a dose form this checker does not read",
};

export function notVerifiable(reason: string | null | undefined): string {
  return `not verifiable (${(reason && UNVERIFIABLE_REASONS[reason]) || "unverifiable"})`;
}

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
  quantity?: number | null;
  dose_per_administration?: number | null;
  dose_basis?: "strength_x_quantity" | "stated_amount" | null;
  dose_status?: "resolved" | "not_stated" | "unverifiable" | null;
  dose_unverifiable_reason?: string | null;
  frequency_code?: string | null;
  frequency_status?: "recognised" | "not_stated" | "not_recognised" | null;
};

export type IssueDetail = {
  field?: string;
  field_status?: "not_stated" | "not_recognised" | "unverifiable";
  unverifiable_reason?: string | null;
  basis?: string;
  citation?: string;
  clinical_review_status?: string;
  class_name?: string;
  class_source?: string;
  formulary_version?: string;
  [key: string]: unknown;
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
  /** missing_field only: the field the first listed source does not state. */
  field?: "dose" | "frequency" | null;
  detail?: IssueDetail;
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
};

export type ExtractedEntry = {
  source_text: string;
  drug_name_raw: string;
  dose_value: number | null;
  dose_unit: string | null;
  quantity?: number | null;
  dose_status?: "resolved" | "not_stated" | "unverifiable";
  dose_unverifiable_reason?: string | null;
  route: string | null;
  frequency_code: string | null;
  frequency_status?: "recognised" | "not_stated" | "not_recognised";
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
  comparisons_made?: number;
  unchecked_comparisons?: number;
  unchecked_by_reason?: { unverifiable: number; not_recognised: number; not_stated: number };
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

type DoseFields = Pick<
  ConflictingSource,
  "presence" | "dose_value" | "dose_unit" | "quantity" | "dose_per_administration" | "dose_status" | "dose_unverifiable_reason"
>;

function num(value: number): string {
  return String(Number(value.toFixed(6)));
}

/** Dose per administration as compared: "3 mg × 2 = 6 mg", or the stated amount when no quantity is stated. */
export function formatDose(src: DoseFields): string {
  if (src.presence === "absent") return "—";
  if (src.dose_status === "unverifiable") return notVerifiable(src.dose_unverifiable_reason);
  if (src.dose_value === null || src.dose_value === undefined) return NOT_STATED;
  const unit = src.dose_unit ?? "";
  const strength = `${num(src.dose_value)} ${unit}`.trim();
  if (src.quantity === null || src.quantity === undefined) return `${strength} (quantity not stated; stated amount used)`;
  const per = src.dose_per_administration ?? src.dose_value * src.quantity;
  return `${strength} × ${num(src.quantity)} = ${num(per)} ${unit}`.trim();
}

export function formatFrequency(src: Pick<ConflictingSource, "frequency_code" | "frequency_status">): string {
  if (src.frequency_code) return src.frequency_code;
  return src.frequency_status === "not_recognised" ? NOT_RECOGNISED : NOT_STATED;
}

/** A field the source did not state is shown as "not stated", never as blank or as a match. */
export function orNotStated(value: string | null | undefined): string {
  return value === null || value === undefined || value === "" ? NOT_STATED : value;
}

const MISSING_FIELD_TITLES: Record<string, string> = {
  "dose:not_stated": "Dose not stated",
  "dose:unverifiable": "Dose could not be verified",
  "frequency:not_stated": "Frequency not stated",
  "frequency:not_recognised": "Frequency not recognised",
};

/** Issue label. Titles follow what actually happened: an unverifiable comparison never "differs". */
export function issueLabel(issue: Pick<Issue, "type" | "field" | "unverifiable" | "detail">): string {
  if (issue.type === "missing_field") {
    const key = `${issue.field ?? issue.detail?.field}:${issue.detail?.field_status ?? "not_stated"}`;
    return MISSING_FIELD_TITLES[key] ?? TYPE_LABELS.missing_field;
  }
  if (issue.type === "dose_mismatch" && issue.unverifiable) return "Dose not comparable (units)";
  return TYPE_LABELS[issue.type] ?? issue.type;
}

export const COMPARED_FIELDS = "dose per administration and frequency";

/**
 * Run summary (B1, C3). The every-comparison sentence appears only when nothing was left unchecked; otherwise
 * the counts made and not made are stated, with the reasons.
 */
export function runSummary(run: Pick<Run, "comparisons_made" | "unchecked_comparisons" | "unchecked_by_reason">): {
  complete: boolean;
  text: string;
} {
  const made = run.comparisons_made ?? 0;
  const n = run.unchecked_comparisons ?? 0;
  if (n === 0) {
    return {
      complete: true,
      text: `Every comparison between lists was made: ${COMPARED_FIELDS} were compared (${made} comparison(s)).`,
    };
  }
  const r = run.unchecked_by_reason ?? { unverifiable: 0, not_recognised: 0, not_stated: 0 };
  return {
    complete: false,
    text:
      `${made} comparison(s) made; ${n} comparison(s) could not be checked and are not counted as matches: ` +
      `${r.unverifiable} not verifiable, ${r.not_recognised} not recognised, ${r.not_stated} not stated.`,
  };
}
