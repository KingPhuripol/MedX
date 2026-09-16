import React, { useEffect, useRef, useState } from "react";
import { createIdempotencyKey } from "../api";
import { Icon, type IconName } from "./Icon";
import {
  type Draft,
  type Fact,
  type Run,
  type SafetyScreen,
  displayFact,
  factKinds,
  factStates,
  humanizeClinicalText,
  redFlagLabels,
  redFlagStates,
  urgencyLabels,
} from "../types";

export function StatusBadge({ tone = "neutral", children }: {
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
  children: React.ReactNode;
}) {
  const icon: IconName = tone === "success" ? "check" : tone === "warning" || tone === "danger" ? "alert" : "spark";
  return <span className={`status-badge status-${tone}`}><Icon name={icon} size={14} />{children}</span>;
}

/** The deterministic screen, rendered above the model's summary.
 *
 * It is read-only on purpose: a physician reviews the draft, never the screen. Urgency
 * and each flag state are carried by text and a glyph, not by color alone, so the
 * finding survives greyscale and a screen reader. */
export function ScreenFindings({ screen }: { screen: SafetyScreen | null }) {
  if (!screen) {
    return (
      <div className="inline-message inline-message--warning" role="status">
        ร่างนี้สร้างก่อนระบบคัดกรองอัตโนมัติ ไม่มีผลคัดกรองกำกับ
      </div>
    );
  }
  const triggered = screen.red_flags.some((flag) => flag.state === "TRIGGERED");
  return (
    <section className="screen-findings" aria-label="ผลคัดกรองอัตโนมัติก่อนใช้แบบจำลอง">
      <div className="section-heading">
        <div>
          <span className="eyebrow">คัดกรองอัตโนมัติ ({screen.policy_version})</span>
          <h3>ระดับความเร่งด่วนอย่างน้อย: {urgencyLabels[screen.urgency_floor] || screen.urgency_floor}</h3>
        </div>
        <StatusBadge tone={triggered ? "danger" : "warning"}>
          {triggered ? "เข้าเงื่อนไขคัดกรอง" : "ยังตอบไม่ครบ"}
        </StatusBadge>
      </div>
      {screen.red_flags.length ? (
        <ul className="screen-findings__flags">
          {screen.red_flags.map((flag) => (
            <li key={flag.code}>
              <strong>{redFlagLabels[flag.code] || flag.code}</strong>
              {" — "}
              {redFlagStates[flag.state] || flag.state}
              {flag.evidence_ids.length ? ` (${flag.evidence_ids.length} รายการ)` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {screen.missing_required.length ? (
        <p className="supporting-text">
          ยังขาด: {screen.missing_required.map((kind) => factKinds[kind] || kind).join(", ")}
        </p>
      ) : null}
      <p className="supporting-text">
        การคัดกรองนี้ดูว่ามีข้อมูลชนิดใดบ้าง ไม่ได้อ่านเนื้อหาทางคลินิก แบบจำลองลดระดับผลนี้ไม่ได้
      </p>
    </section>
  );
}

export function FactView({ fact, onEdit }: { fact: Fact; onEdit?: (fact: Fact) => void }) {
  return (
    <div className="fact-card">
      <div className="fact-card__header">
        <span className="eyebrow">{factKinds[fact.kind] || "ข้อมูลเพิ่มเติม"}</span>
        <StatusBadge tone={fact.state === "KNOWN" ? "success" : "neutral"}>
          {factStates[fact.state] || "รอตรวจ"}
        </StatusBadge>
      </div>
      <p>{displayFact(fact)}</p>
      {fact.conflicts_with_event_ids?.length ? (
        <p className="inline-message inline-message--warning">มีข้อมูลที่ต้องตรวจความสอดคล้อง</p>
      ) : null}
      {onEdit ? <button className="button button--text" onClick={() => onEdit(fact)}>แก้ไขข้อมูลนี้</button> : null}
    </div>
  );
}

export function FactEditor({ fact, onChange }: { fact: Fact; onChange: (fact: Fact) => void }) {
  const [raw, setRaw] = useState(typeof fact.value === "object" ? JSON.stringify(fact.value) : String(fact.value ?? ""));
  const [invalid, setInvalid] = useState(false);
  const knownValue = useRef(fact.value);
  if (fact.state === "KNOWN") knownValue.current = fact.value;
  const isMeasurement = fact.state === "KNOWN" && typeof fact.value === "object" && fact.value !== null && "name" in fact.value && "unit" in fact.value;
  const measurement = isMeasurement ? fact.value as Record<string, unknown> : null;

  return (
    <fieldset className="fact-editor">
      <legend className="sr-only">รายละเอียดข้อมูลที่ต้องตรวจ</legend>
      <div className="form-grid">
        <label>ประเภทข้อมูล
          <select value={fact.kind} onChange={(event) => {
            const kind = event.target.value;
            const measurement = ["VITAL", "LAB"].includes(kind);
            onChange({ ...fact, kind, value: fact.state === "KNOWN" && measurement && typeof fact.value !== "object" ? { name: "", value: null, unit: "" } : fact.value });
          }}>
            {Object.entries(factKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>สถานะข้อมูล
          <select value={fact.state} onChange={(event) => onChange({
            ...fact,
            state: event.target.value,
            value: event.target.value === "KNOWN" ? knownValue.current ?? raw : null,
          })}>
            {Object.entries(factStates).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
      {isMeasurement ? (
        <div className="form-grid form-grid--measurement">
          <label>ชื่อรายการวัด<input required value={String(measurement?.name ?? "")} onChange={(event) => onChange({ ...fact, value: { ...measurement, name: event.target.value } })} /></label>
          <label>ค่าที่วัด<input required type="number" step="any" value={measurement?.value === null ? "" : Number(measurement?.value ?? 0)} onChange={(event) => onChange({ ...fact, value: { ...measurement, value: event.target.value === "" ? null : Number(event.target.value) } })} /></label>
          <label>หน่วย<input required value={String(measurement?.unit ?? "")} onChange={(event) => onChange({ ...fact, value: { ...measurement, unit: event.target.value } })} /></label>
        </div>
      ) : fact.state === "KNOWN" ? (
        <label>ข้อมูลที่ตรวจแล้ว
          <textarea required value={raw} aria-invalid={invalid} onChange={(event) => {
            setRaw(event.target.value);
            try {
              const value = typeof fact.value === "object" && fact.value !== null
                ? JSON.parse(event.target.value)
                : typeof fact.value === "number" ? Number(event.target.value) : event.target.value;
              if (typeof value === "number" && !Number.isFinite(value)) throw Error();
              setInvalid(false);
              event.target.setCustomValidity("");
              onChange({ ...fact, value });
            } catch {
              setInvalid(true);
              event.target.setCustomValidity("รูปแบบข้อมูลไม่ถูกต้อง");
            }
          }} />
          {invalid ? <span className="field-error" role="alert">รูปแบบข้อมูลไม่ถูกต้อง โปรดแก้ให้ครบก่อนบันทึก</span> : null}
        </label>
      ) : null}
    </fieldset>
  );
}

export function Review({ draft, revision, canReview, act, onDirty }: {
  draft: Draft;
  revision: number;
  canReview: boolean;
  act: (path: string, body: unknown) => Promise<void>;
  onDirty: (dirty: boolean) => void;
}) {
  const [summary, setSummary] = useState(humanizeClinicalText(draft.content.summary));
  const [reason, setReason] = useState("");
  const [outstanding, setOutstanding] = useState(draft.content.outstanding.join("\n"));
  const [editing, setEditing] = useState(false);
  const [evidence, setEvidence] = useState(false);
  const [baseline, setBaseline] = useState({ summary: humanizeClinicalText(draft.content.summary), outstanding: draft.content.outstanding.join("\n") });
  const [reviewConflict, setReviewConflict] = useState(false);
  const dirty = summary !== baseline.summary || outstanding !== baseline.outstanding;
  const stale = draft.case_revision !== revision || draft.status === "SUPERSEDED" || draft.status === "STALE";

  useEffect(() => {
    const incoming = { summary: humanizeClinicalText(draft.content.summary), outstanding: draft.content.outstanding.join("\n") };
    if (!dirty || (incoming.summary === summary && incoming.outstanding === outstanding)) {
      setSummary(incoming.summary);
      setOutstanding(incoming.outstanding);
      setBaseline(incoming);
      setReviewConflict(false);
    } else setReviewConflict(true);
  }, [draft.draft_revision, draft.review_sequence]);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);

  const review = async (action: "CONFIRM" | "MODIFY" | "REJECT" | "ESCALATE") => act(`/drafts/${draft.draft_id}/reviews`, {
    expected_revision: revision,
    idempotency_key: createIdempotencyKey(),
    draft_revision: draft.draft_revision,
    expected_review_sequence: draft.review_sequence,
    action,
    reason: action === "CONFIRM" ? null : reason,
    content: action === "MODIFY" ? { ...draft.content, summary, outstanding: outstanding.split("\n").map((item) => item.trim()).filter(Boolean) } : null,
  });

  const tone = stale ? "warning" : draft.effective ? "success" : draft.status === "REJECT" ? "danger" : "info";
  const status = stale ? "ต้องตรวจใหม่" : draft.effective ? "ยืนยันแล้ว" : draft.status === "REJECT" ? "ถูกปฏิเสธ" : "รอตรวจยืนยัน";

  return (
    <section className="panel draft-review" aria-labelledby={`draft-${draft.draft_id}`}>
      <div className="section-heading">
        <div><span className="eyebrow">ร่างส่งต่อ</span><h2 id={`draft-${draft.draft_id}`}>ตรวจร่างฉบับที่ {draft.draft_revision}</h2></div>
        <StatusBadge tone={tone}>{status}</StatusBadge>
      </div>
      <p className="supporting-text">อ้างอิงข้อมูลเคสรุ่น {draft.case_revision}</p>
      {stale ? <div role="status" className="inline-message inline-message--warning">ข้อมูลเคสเปลี่ยนแล้ว กรุณาตรวจหรือสร้างร่างฉบับล่าสุด</div> : null}
      <ScreenFindings screen={draft.screen} />
      {editing ? <div className="edit-surface">
        <label>ข้อความสรุป<textarea className="summary-editor" value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
        <label>งานค้าง หนึ่งรายการต่อบรรทัด<textarea value={outstanding} onChange={(event) => setOutstanding(event.target.value)} /></label>
        <label>เหตุผลที่แก้ไขหรือปฏิเสธ<textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      </div> : <p className="summary-text">{humanizeClinicalText(draft.content.summary)}</p>}
      {dirty ? <div className="inline-message inline-message--warning" role="status">มีการแก้ไขที่ยังไม่บันทึก บันทึกแล้วตรวจฉบับใหม่ก่อนยืนยัน</div> : null}
      {reviewConflict ? <div className="inline-message inline-message--danger" role="alert"><p>ร่างเปลี่ยนระหว่างที่คุณแก้ ข้อความที่พิมพ์ยังอยู่ กรุณาเทียบกับฉบับล่าสุด</p><p className="summary-text">{humanizeClinicalText(draft.content.summary)}</p><button className="button button--secondary" onClick={() => setReviewConflict(false)}>ตรวจฉบับล่าสุดแล้ว</button></div> : null}
      {draft.content.outstanding.length ? <div className="outstanding"><h3>ข้อมูลหรืองานที่ยังขาด</h3><ul>{draft.content.outstanding.map((item, index) => <li key={index}>{factKinds[item] || factStates[item] || item}</li>)}</ul></div> : null}
      <button className="button button--text" onClick={() => setEvidence(!evidence)} aria-expanded={evidence}>ดูหลักฐานที่ร่างนี้ใช้ ({draft.snapshot.evidence.length})</button>
      {evidence ? <div className="evidence-list">{draft.snapshot.evidence.map((fact) => <FactView key={fact.event_id} fact={fact} />)}</div> : null}
      <details><summary>เทียบฉบับก่อนและประวัติ</summary>{draft.versions.map((version) => <div className="version" key={version.draft_revision}><h3>ฉบับที่ {version.draft_revision}</h3><p className="summary-text">{humanizeClinicalText(version.content.summary)}</p></div>)}</details>
      {canReview ? <div className="button-group">
        <button className="button button--primary" disabled={stale || dirty || draft.effective || reviewConflict} onClick={() => review("CONFIRM")}>ยืนยันร่างฉบับนี้</button>
        <button className="button button--secondary" onClick={() => setEditing(!editing)}>{editing ? "ปิดช่องแก้ไข" : "แก้ไขหรือปฏิเสธ"}</button>
        {editing ? <>
          <button className="button button--secondary" disabled={stale || !dirty || !reason.trim() || reviewConflict} onClick={() => review("MODIFY")}>บันทึกเป็นฉบับใหม่</button>
          <button className="button button--danger" disabled={stale || !reason.trim() || dirty} onClick={() => review("REJECT")}>ปฏิเสธร่าง</button>
          <button className="button button--danger" disabled={stale || !reason.trim() || dirty} onClick={() => review("ESCALATE")}>ส่งต่อให้ทบทวน</button>
        </> : null}
      </div> : <p className="supporting-text">บัญชีแพทย์เป็นผู้ยืนยันร่างส่งต่อ</p>}
    </section>
  );
}

export function Proposals({ run, revision, act, onDirty = () => undefined }: {
  run: Run;
  revision: number;
  act: (path: string, body: unknown) => Promise<void>;
  onDirty?: (dirty: boolean) => void;
}) {
  const initial = run.proposals.filter((proposal) => proposal.proposal_id);
  const [items, setItems] = useState(initial);
  const [selected, setSelected] = useState(initial.map((proposal) => proposal.proposal_id));
  const changed = JSON.stringify(items) !== JSON.stringify(initial) || selected.length !== initial.length;
  const active = run.case_revision === revision && run.status === "COMPLETED";
  useEffect(() => { onDirty(active && changed); return () => onDirty(false); }, [active, changed, onDirty]);
  if (!items.length || !active) return null;

  return (
    <form className="proposal-review" onSubmit={(event) => {
      event.preventDefault();
      act(`/runs/${run.run_id}/proposals/accept-batch`, {
        expected_revision: revision,
        idempotency_key: createIdempotencyKey(),
        proposals: items.filter((proposal) => selected.includes(proposal.proposal_id)).map(({ proposal_id, fact }) => ({ proposal_id, fact })),
      });
    }}>
      <div className="section-heading"><div><span className="eyebrow">ข้อมูลรอตรวจ</span><h3>ตรวจข้อเสนอจากผู้ช่วย</h3></div><StatusBadge tone="warning">{selected.length} รายการที่เลือก</StatusBadge></div>
      <p className="supporting-text">ข้อความสนทนายังไม่เป็นข้อมูลยืนยัน เลือกและตรวจทุกค่าก่อนบันทึก</p>
      {items.map((proposal, index) => <div className="proposal-item" key={proposal.proposal_id}>
        <label className="check-control"><input type="checkbox" checked={selected.includes(proposal.proposal_id)} onChange={(event) => setSelected(event.target.checked ? [...selected, proposal.proposal_id] : selected.filter((id) => id !== proposal.proposal_id))} /><span>เลือกบันทึกรายการนี้</span></label>
        <FactEditor fact={proposal.fact} onChange={(fact) => setItems(items.map((item, itemIndex) => itemIndex === index ? { ...item, fact } : item))} />
      </div>)}
      <button className="button button--primary" disabled={!selected.length}>ยืนยันข้อมูลที่เลือก {selected.length} รายการ</button>
    </form>
  );
}
