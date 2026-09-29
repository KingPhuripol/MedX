"use client";

import { Check, ChevronUp, CircleHelp } from "lucide-react";

import { StatusChip } from "@/components/ui/StatusChip";
import { FIELD_LABELS_TH, displayValue, type Fact, type FieldStatus, type SessionState, type Turn } from "@/lib/voice";

const FIELD_ORDER = Object.keys(FIELD_LABELS_TH);

function orderOf(field: string): number {
  const i = FIELD_ORDER.indexOf(field);
  return i === -1 ? FIELD_ORDER.length : i;
}

const STATE_NOTE_TH: Record<string, string> = { UNKNOWN: "ผู้ป่วยไม่ทราบ", REFUSED: "ผู้ป่วยไม่ตอบ" };

/** One captured fact with its evidence: value as said, normalised value, and the source utterance number. */
export function FactRow({ fact, turns }: { fact: Fact; turns: Turn[] }) {
  const bySeq = new Map(turns.map((t) => [t.turn_id, t]));
  const source = bySeq.get(fact.span_turn_ids[0] ?? "");
  const speakers = fact.span_turn_ids.flatMap((id) => bySeq.get(id)?.speaker ?? []);
  const known = fact.state === "KNOWN";
  return (
    <li className="live-fact" data-testid="live-fact-row" data-field={fact.field}>
      <span className={known ? "live-fact-icon" : "live-fact-icon live-fact-icon--open"} aria-hidden="true">
        {known ? <Check size={16} /> : <CircleHelp size={16} />}
      </span>
      <span className="live-fact-label">{FIELD_LABELS_TH[fact.field] ?? fact.field}</span>
      <span className="live-fact-value" lang="th">
        {fact.value_text ?? String(fact.value ?? "—")}
      </span>
      <span className="live-fact-ev">จากประโยค #{source?.seq ?? "?"}</span>
      <span className="live-fact-norm">{known ? displayValue(fact, speakers) : (STATE_NOTE_TH[fact.state] ?? fact.state)}</span>
    </li>
  );
}

export function MissingChips({ statuses }: { statuses: FieldStatus[] }) {
  const missing = statuses.filter((s) => s.status === "MISSING");
  if (!missing.length) return null;
  return (
    <ul className="live-missing" aria-label="หัวข้อที่ยังไม่มีข้อมูล">
      {missing.map((s) => (
        <li key={s.field} data-testid="live-missing-chip" data-field={s.field}>
          <StatusChip tone="neutral">
            {FIELD_LABELS_TH[s.field] ?? s.field}
            {s.not_elicited ? " (ถามครบ 2 ครั้งแล้ว)" : ""}
          </StatusChip>
        </li>
      ))}
    </ul>
  );
}

/** Bottom sheet "ข้อมูลที่กรอกแล้ว". Collapsed peek shows the two most recent facts; a right panel at >=1024px. */
export function FactSheet({
  data,
  expanded,
  desktop,
  onToggle,
}: {
  data: SessionState | null;
  expanded: boolean;
  desktop: boolean;
  onToggle: () => void;
}) {
  const facts = data?.facts ?? [];
  const statuses = data?.field_statuses ?? [];
  const turns = data?.turns ?? [];
  const known = statuses.filter((s) => s.status === "KNOWN").length;
  const open = expanded || desktop;
  const recent = [...facts]
    .sort((a, b) => b.available_at_time.localeCompare(a.available_at_time) || orderOf(b.field) - orderOf(a.field))
    .slice(0, 2);
  const shown = open ? [...facts].sort((a, b) => orderOf(a.field) - orderOf(b.field)) : recent;
  const title = `ข้อมูลที่กรอกแล้ว ${known}/${statuses.length}`;

  return (
    <section className="live-sheet" data-testid="live-sheet" data-expanded={open} aria-labelledby="live-sheet-title">
      <h2 id="live-sheet-title" className="live-sheet-head">
        {desktop ? (
          <span>{title}</span>
        ) : (
          <button type="button" data-testid="live-sheet-toggle" aria-expanded={expanded} aria-controls="live-sheet-body" onClick={onToggle}>
            <span>{title}</span>
            <ChevronUp size={20} aria-hidden="true" className="live-sheet-chevron" />
          </button>
        )}
      </h2>
      <div id="live-sheet-body" className="live-sheet-body">
        {shown.length ? (
          <ul className="live-facts">
            {shown.map((f) => (
              <FactRow key={f.fact_id} fact={f} turns={turns} />
            ))}
          </ul>
        ) : (
          <p className="live-sheet-empty">ยังไม่มีข้อมูล — ระบบจะกรอกให้เมื่อผู้ป่วยตอบ</p>
        )}
        {open && <MissingChips statuses={statuses} />}
      </div>
    </section>
  );
}
