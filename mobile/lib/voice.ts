/** Voice session contract types (v2a §3, consumed only) and the display rules of SPEC §10. */
import { COPY, FIELD_LABELS, PROPOSED_V2C } from "./copy";

export const ASK_ORDER = [
  "chief_complaint",
  "onset_duration",
  "severity",
  "allergy_status",
  "current_medications",
  "relevant_history",
] as const;
export type AskField = (typeof ASK_ORDER)[number];

export interface NextAction {
  kind: "prompt_nurse" | "complete" | "handoff";
  field: string | null;
  suggested_question_id: string | null;
  suggested_question_th: string | null;
  reason: string | null;
  missing_fields: string[];
}

export interface Fact {
  fact_id: string;
  field: string;
  state: "KNOWN" | "UNKNOWN" | "REFUSED";
  value: string | number | string[] | null;
  value_text?: string;
  span_turn_ids: string[];
  available_at_time?: string;
}

export interface FieldStatus {
  field: string;
  status: "MISSING" | "KNOWN" | "UNKNOWN" | "REFUSED";
  times_asked: number;
  not_elicited?: boolean;
}

export interface Session {
  session_id: string;
  patient_ref: string;
  mode?: string;
  status: string;
  nurse_attention: boolean;
  extraction_error: boolean;
  allergy_conflict?: boolean;
}

export interface Turn {
  turn_id: string;
  text: string;
  started_at: string;
  ended_at: string;
  speaker?: string;
}

/** What the screen shows; every turn response replaces the parts it carries (T4). */
export interface Scribe {
  session: Session;
  facts: Fact[];
  field_statuses: FieldStatus[];
  next_action: NextAction | null;
  turns: Turn[];
}

export interface StartResponse {
  session: Session;
  next_action: NextAction;
  field_statuses: FieldStatus[];
}

export interface TurnResponse {
  turn: Turn;
  new_facts: Fact[];
  field_statuses: FieldStatus[];
  next_action: NextAction;
  nurse_attention?: boolean;
  extraction_error?: boolean;
  session: Session;
}

export interface SessionGet {
  session: Session;
  turns: Turn[];
  facts: Fact[];
  field_statuses: FieldStatus[];
  next_action: NextAction;
}

export function fromStart(r: StartResponse): Scribe {
  return { session: r.session, facts: [], field_statuses: r.field_statuses, next_action: r.next_action, turns: [] };
}

export function applyTurn(prev: Scribe, r: TurnResponse): Scribe {
  const known = new Set(prev.facts.map((f) => f.fact_id));
  const turns = prev.turns.some((t) => t.turn_id === r.turn.turn_id) ? prev.turns : [...prev.turns, r.turn];
  return {
    session: { ...r.session, nurse_attention: prev.session.nurse_attention || !!r.session?.nurse_attention },
    facts: [...prev.facts, ...(r.new_facts ?? []).filter((f) => !known.has(f.fact_id))],
    field_statuses: r.field_statuses,
    next_action: r.next_action,
    turns,
  };
}

export function applyGet(prev: Scribe, r: SessionGet): Scribe {
  return {
    session: { ...r.session, nurse_attention: prev.session.nurse_attention || !!r.session?.nurse_attention },
    facts: r.facts,
    field_statuses: r.field_statuses,
    next_action: r.next_action,
    turns: r.turns,
  };
}

/** Red flag = nurse_attention on any response, or the nurse-attention handoff (SPEC §10). */
export function isRedFlag(r: { nurse_attention?: boolean; session?: Session; next_action?: NextAction | null }): boolean {
  return (
    r.nurse_attention === true ||
    r.session?.nurse_attention === true ||
    (r.next_action?.kind === "handoff" && r.next_action.reason === "nurse_attention_phrase")
  );
}

export function latestFact(facts: Fact[], field: string): Fact | undefined {
  for (let i = facts.length - 1; i >= 0; i--) if (facts[i].field === field) return facts[i];
  return undefined;
}

function statusOf(s: Scribe, field: string): FieldStatus | undefined {
  return s.field_statuses.find((f) => f.field === field);
}

const NEGATIVE = /ไม่แพ้|ไม่มีประวัติแพ้/;

/** True only for the one case where the allergy row may say "no allergy" (C6). */
export function allergyNegativeAllowed(s: Scribe): boolean {
  const f = latestFact(s.facts, "allergy_status");
  return (
    f?.state === "KNOWN" &&
    f.value === "none" &&
    statusOf(s, "allergy_status")?.status === "KNOWN" &&
    !s.session.allergy_conflict &&
    !s.session.extraction_error
  );
}

function factText(f: Fact | undefined): string {
  if (!f) return "";
  if (typeof f.value_text === "string" && f.value_text.trim()) return f.value_text.trim();
  if (Array.isArray(f.value)) return f.value.join(", ");
  return f.value == null ? "" : String(f.value);
}

export type RowStatus = "captured" | "asking" | "missing";

export interface Row {
  field: AskField;
  label: string;
  status: RowStatus;
  state: FieldStatus["status"];
  value: string;
  /** Latest fact(s) behind the value; empty when not KNOWN/UNKNOWN/REFUSED. */
  facts: Fact[];
  negativeAllergy: boolean;
}

function knownValue(s: Scribe, field: AskField): { value: string; facts: Fact[]; negative: boolean } {
  if (field !== "allergy_status") {
    const f = latestFact(s.facts, field);
    return { value: factText(f) || COPY.rec.valueMissing, facts: f ? [f] : [], negative: false };
  }
  const status = latestFact(s.facts, "allergy_status");
  const allergens = latestFact(s.facts, "allergens");
  if (allergyNegativeAllowed(s)) return { value: PROPOSED_V2C.allergyNone, facts: status ? [status] : [], negative: true };
  const facts = [status, allergens].filter((f): f is Fact => !!f);
  if (s.session.allergy_conflict || status?.value !== "present") {
    // conflict, extraction error on a "none", or a value we do not know: never a negative.
    return { value: PROPOSED_V2C.allergyUnclear, facts, negative: false };
  }
  const text = (allergens?.state === "KNOWN" ? factText(allergens) : "") || factText(status);
  return { value: !text || NEGATIVE.test(text) ? PROPOSED_V2C.allergyUnclear : text, facts, negative: false };
}

/** The six display rows in ASK_ORDER (SPEC §10). `live`: the navy slot is asking, so its field reads "กำลังถาม". */
export function rows(s: Scribe, live = false): Row[] {
  const asking = live && s.next_action?.kind === "prompt_nurse" ? s.next_action.field : null;
  return ASK_ORDER.map((field) => {
    const st = statusOf(s, field);
    const state = st?.status ?? "MISSING";
    const base = { field, label: FIELD_LABELS[field], state, negativeAllergy: false };
    if (state === "MISSING") {
      if (field === asking) return { ...base, status: "asking", value: COPY.rec.valueAsking, facts: [] };
      return {
        ...base,
        status: "missing",
        value: st?.not_elicited ? COPY.rec.valueNotElicited : COPY.rec.valueMissing,
        facts: [],
      };
    }
    const fact = latestFact(s.facts, field);
    if (state === "UNKNOWN") return { ...base, status: "captured", value: COPY.rec.valueUnknown, facts: fact ? [fact] : [] };
    if (state === "REFUSED") return { ...base, status: "captured", value: COPY.rec.valueRefused, facts: fact ? [fact] : [] };
    const k = knownValue(s, field);
    return { ...base, status: "captured", value: k.value, facts: k.facts, negativeAllergy: k.negative };
  });
}

export function capturedCount(s: Scribe): number {
  return ASK_ORDER.filter((f) => (statusOf(s, f)?.status ?? "MISSING") !== "MISSING").length;
}

export function allComplete(s: Scribe): boolean {
  return capturedCount(s) === ASK_ORDER.length;
}
