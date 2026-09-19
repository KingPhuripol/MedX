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
  pathwayLabels,
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
export function ScreenFindings({ screen, onAddMissing }: {
  screen: SafetyScreen | null;
  onAddMissing?: (kind: string) => void;
}) {
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
        <div className="screen-findings__missing">
          <p className="supporting-text">ยังขาด: {screen.missing_required.map((kind) => factKinds[kind] || kind).join(", ")}</p>
          {onAddMissing ? (
            <div className="missing-tags">
              {screen.missing_required.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className="badge-action-pill"
                  title={`คลิกเพื่อเพิ่มข้อมูล ${factKinds[kind] || kind}`}
                  onClick={() => onAddMissing(kind)}
                >
                  <Icon name="plus" size={12} />
                  <span>เพิ่ม{factKinds[kind] || kind}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
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

const outstandingLabel = (item: string) => factKinds[item] || factStates[item] || item;

export function Review({ draft, revision, canReview, act, onDirty, onAddMissing }: {
  draft: Draft;
  revision: number;
  canReview: boolean;
  act: (path: string, body: unknown) => Promise<void>;
  onDirty: (dirty: boolean) => void;
  onAddMissing?: (kind: string) => void;
}) {
  // The edit surface shows Thai, but `draft.content` stores the machine values. Keeping
  // the two apart matters: sending the humanized string back would silently rewrite
  // stored clinical text that the reviewer never authored. `review()` below sends the
  // ORIGINAL value whenever a field was not edited, so the codes survive untouched.
  const incomingOf = (source: Draft) => ({
    summary: humanizeClinicalText(source.content.summary),
    outstanding: source.content.outstanding.map(outstandingLabel).join("\n"),
  });
  const [summary, setSummary] = useState(() => incomingOf(draft).summary);
  const [reason, setReason] = useState("");
  const [reasonCode, setReasonCode] = useState("MISSING_INFORMATION");
  const [outstanding, setOutstanding] = useState(() => incomingOf(draft).outstanding);
  const [editing, setEditing] = useState(false);
  const [evidence, setEvidence] = useState(false);
  const [baseline, setBaseline] = useState(() => incomingOf(draft));
  const [reviewConflict, setReviewConflict] = useState(false);
  const summaryEdited = summary !== baseline.summary;
  const outstandingEdited = outstanding !== baseline.outstanding;
  const dirty = summaryEdited || outstandingEdited;
  const stale = draft.case_revision !== revision || draft.status === "SUPERSEDED" || draft.status === "STALE";

  useEffect(() => {
    const incoming = incomingOf(draft);
    if (!dirty || (incoming.summary === summary && incoming.outstanding === outstanding)) {
      setSummary(incoming.summary);
      setOutstanding(incoming.outstanding);
      setBaseline(incoming);
      setReviewConflict(false);
    } else setReviewConflict(true);
  }, [draft.draft_revision, draft.review_sequence]);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);

  const review = async (action: "CONFIRM" | "MODIFY" | "REJECT" | "REQUEST_INFORMATION" | "ESCALATE") => act(`/drafts/${draft.draft_id}/reviews`, {
    expected_revision: revision,
    idempotency_key: createIdempotencyKey(),
    draft_revision: draft.draft_revision,
    expected_review_sequence: draft.review_sequence,
    action,
    reason_code: action === "CONFIRM" ? null : reasonCode,
    reason: action === "CONFIRM" ? null : reason,
    content: action === "MODIFY" ? {
      ...draft.content,
      summary: summaryEdited ? summary : draft.content.summary,
      outstanding: outstandingEdited
        ? outstanding.split("\n").map((item) => item.trim()).filter(Boolean)
        : draft.content.outstanding,
    } : null,
  });

  const tone = stale ? "warning" : draft.effective ? "success" : draft.status === "REJECT" ? "danger" : "info";
  const status = stale ? "ต้องตรวจใหม่" : draft.effective ? "ยืนยันแล้ว" : draft.status === "REJECT" ? "ถูกปฏิเสธ" : "รอตรวจยืนยัน";

  // Why the primary action is unavailable. A disabled control must say so in words.
  const blocked = stale ? "ข้อมูลเคสเปลี่ยนแล้ว ต้องสร้างหรือตรวจร่างฉบับล่าสุดก่อนจึงจะยืนยันได้"
    : reviewConflict ? "ร่างเปลี่ยนระหว่างที่คุณแก้ กรุณาเทียบกับฉบับล่าสุดก่อน"
    : dirty ? "มีการแก้ไขที่ยังไม่บันทึก บันทึกเป็นฉบับใหม่แล้วตรวจอีกครั้งก่อนยืนยัน"
    : draft.effective ? "ร่างฉบับนี้ยืนยันแล้ว การเพิ่มข้อมูลเคสจะทำให้ต้องตรวจใหม่"
    : "";
  const consequence = draft.effective
    ? "ร่างฉบับนี้เป็นการส่งต่อปัจจุบันของเคส บันทึกไว้พร้อมชื่อผู้ตรวจและเวลาแล้ว"
    : draft.status === "REJECT"
    ? "ร่างนี้ถูกปฏิเสธและไม่ถูกใช้เป็นการส่งต่อ เหตุผลที่ระบุอยู่ในประวัติการตรวจ สร้างร่างใหม่ได้เมื่อพร้อม"
    : "การยืนยันทำให้ร่างนี้เป็นการส่งต่อปัจจุบันของเคส และบันทึกชื่อคุณกับเวลาไว้กับมัน หากมีการเพิ่มข้อมูลเคสหลังจากนี้ ร่างจะกลายเป็นฉบับที่ต้องตรวจใหม่โดยอัตโนมัติ";

  return (
    <section className="panel draft-review" aria-labelledby={`draft-${draft.draft_id}`}>
      <div className="section-heading">
        <div><span className="eyebrow">ร่างส่งต่อ</span><h2 id={`draft-${draft.draft_id}`}>ตรวจร่างฉบับที่ {draft.draft_revision}</h2></div>
        <StatusBadge tone={tone}>{status}</StatusBadge>
      </div>
      <p className="supporting-text">อ้างอิงข้อมูลเคสรุ่น {draft.case_revision}</p>
      <div className="decision-snapshot" aria-label="ช่วงเวลาที่ประเมิน">
        <StatusBadge tone="info">{draft.snapshot.timepoint || "T0"}</StatusBadge>
        <span>ประเมินจากข้อมูลที่พร้อมใช้ ณ {draft.snapshot.decision_time ? new Date(draft.snapshot.decision_time).toLocaleString("th-TH") : "เวลาที่สร้างร่าง"}</span>
      </div>
      {stale ? <div role="status" className="inline-message inline-message--warning">ข้อมูลเคสเปลี่ยนแล้ว กรุณาตรวจหรือสร้างร่างฉบับล่าสุด</div> : null}
      <div className="draft-review__body">
        <div className="draft-review__content">
          <ScreenFindings screen={draft.screen} onAddMissing={onAddMissing} />
          <section className="clinical-output-grid" aria-label="ผลช่วยตัดสินใจ">
            <article>
              <span className="eyebrow">ข้อเสนอระดับเร่งด่วน</span>
              <h3>{urgencyLabels[draft.content.urgency?.level || "INSUFFICIENT_INFORMATION"] || draft.content.urgency?.level}</h3>
              <p>{draft.content.urgency?.confidence == null ? "ยังไม่มีค่าความมั่นใจที่ผ่านการสอบเทียบ" : `ความมั่นใจ ${(draft.content.urgency.confidence * 100).toFixed(0)}%`}</p>
            </article>
            <article>
              <span className="eyebrow">ความไม่แน่นอน</span>
              <h3>{draft.content.uncertainty?.abstained ? "งดสรุปผลอัตโนมัติ" : "มีข้อเสนอให้แพทย์ตรวจ"}</h3>
              <p>{draft.content.uncertainty?.calibrated ? "ผ่านการสอบเทียบ" : "ยังไม่ผ่านการสอบเทียบ"}</p>
            </article>
          </section>
          {draft.content.care_pathways?.length ? <section className="decision-list"><h3>แนวทางส่งต่อที่เสนอ</h3><ol>{draft.content.care_pathways.map((item) => <li key={`${item.rank}-${item.code}`}><strong>{item.rank}. {pathwayLabels[item.code] || item.code}</strong>{item.rationale ? <span>{item.rationale}</span> : null}</li>)}</ol></section> : null}
          {draft.content.next_information?.length ? <section className="decision-list"><h3>ข้อมูลถัดไปที่ควรเก็บ</h3><ol>{draft.content.next_information.map((item) => <li key={`${item.rank}-${item.information_type}`}><strong>{item.rank}. {factKinds[item.information_type] || item.information_type}</strong><span>{item.waiting_is_unsafe ? "ห้ามรอหากทำให้การทบทวนล่าช้า" : "เก็บเพิ่มเมื่อทำได้อย่างปลอดภัย"}</span></li>)}</ol></section> : null}
          {[...(draft.screen?.limitations || []), ...(draft.content.limitations || []), ...(draft.content.uncertainty?.reasons || [])].length ? <section className="limitations"><h3>ข้อจำกัดที่ต้องรับทราบ</h3><ul>{[...(draft.screen?.limitations || []), ...(draft.content.limitations || []), ...(draft.content.uncertainty?.reasons || [])].map((item, index) => <li key={index}>{item}</li>)}</ul></section> : null}
          {editing ? <div className="edit-surface">
            <label>ข้อความสรุป<textarea className="summary-editor" value={summary} onChange={(event) => setSummary(event.target.value)} /></label>
            <label>งานค้าง หนึ่งรายการต่อบรรทัด<textarea value={outstanding} onChange={(event) => setOutstanding(event.target.value)} /></label>
          </div> : <p className="summary-text">{humanizeClinicalText(draft.content.summary)}</p>}
          {dirty ? <div className="inline-message inline-message--warning" role="status">มีการแก้ไขที่ยังไม่บันทึก บันทึกแล้วตรวจฉบับใหม่ก่อนยืนยัน</div> : null}
          {reviewConflict ? <div className="inline-message inline-message--danger" role="alert"><p>ร่างเปลี่ยนระหว่างที่คุณแก้ ข้อความที่พิมพ์ยังอยู่ กรุณาเทียบกับฉบับล่าสุด</p><p className="summary-text">{humanizeClinicalText(draft.content.summary)}</p><button className="button button--secondary" onClick={() => setReviewConflict(false)}>ตรวจฉบับล่าสุดแล้ว</button></div> : null}
          {draft.content.outstanding.length ? <div className="outstanding"><h3>ข้อมูลหรืองานที่ยังขาด</h3><ul>{draft.content.outstanding.map((item, index) => <li key={index}>{outstandingLabel(item)}</li>)}</ul></div> : null}
          <button className="button button--text" onClick={() => setEvidence(!evidence)} aria-expanded={evidence}>ดูหลักฐานที่ร่างนี้ใช้ ({draft.snapshot.evidence.length})</button>
          {evidence ? <div className="evidence-list">{draft.snapshot.evidence.map((fact) => <FactView key={fact.event_id} fact={fact} />)}</div> : null}
          <details><summary>เทียบฉบับก่อนและประวัติ</summary>{draft.versions.map((version) => <div className="version" key={version.draft_revision}><h3>ฉบับที่ {version.draft_revision}</h3><p className="summary-text">{humanizeClinicalText(version.content.summary)}</p></div>)}</details>
          {draft.provenance ? <details><summary>ข้อมูลเทคนิคสำหรับผู้ประเมิน</summary><dl className="technical-provenance"><div><dt>Provider</dt><dd>{String(draft.provenance.provider || "ไม่ระบุ")}</dd></div><div><dt>Model</dt><dd>{String(draft.provenance.model || "ไม่ระบุ")}</dd></div><div><dt>Policy</dt><dd>{draft.screen?.policy_version || "ไม่ระบุ"}</dd></div></dl></details> : null}
        </div>
        <aside className="decision-rail" aria-label="การตัดสินใจของแพทย์">
          <span className="eyebrow">การตัดสินใจ</span>
          <p className="decision-rail__consequence">{consequence}</p>
          {canReview ? <>
            <label className="decision-rail__reason">หมวดการตัดสินใจ<select value={reasonCode} onChange={(event) => setReasonCode(event.target.value)}><option value="MISSING_INFORMATION">ข้อมูลยังไม่ครบ</option><option value="CLINICAL_CORRECTION">แก้ไขเนื้อหาทางคลินิก</option><option value="UNSAFE_TO_CONFIRM">ยังไม่ปลอดภัยที่จะยืนยัน</option><option value="OUT_OF_SCOPE">อยู่นอกขอบเขตระบบ</option><option value="OTHER">เหตุผลอื่น</option></select></label>
            <label className="decision-rail__reason">รายละเอียดเหตุผล<span className="field-hint">ต้องระบุเมื่อแก้ไข ปฏิเสธ ขอข้อมูลเพิ่ม หรือส่งต่อ และจะถูกบันทึกในประวัติ</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
            {blocked ? <div className="inline-message inline-message--warning" role="status">{blocked}</div> : null}
            <div className="button-group button-group--stacked">
              <button className="button button--primary button--full" disabled={stale || dirty || draft.effective || reviewConflict} onClick={() => review("CONFIRM")}>ยืนยันร่างฉบับนี้</button>
              <button className="button button--secondary button--full" onClick={() => setEditing(!editing)}>{editing ? "ปิดช่องแก้ไข" : "แก้ไขข้อความ"}</button>
              <button className="button button--secondary button--full" disabled={stale || !dirty || !reason.trim() || reviewConflict} onClick={() => review("MODIFY")}>บันทึกเป็นฉบับใหม่</button>
              <button className="button button--secondary button--full" disabled={stale || !reason.trim() || dirty} onClick={() => review("REQUEST_INFORMATION")}>ขอข้อมูลเพิ่มเติม</button>
              <button className="button button--danger button--full" disabled={stale || !reason.trim() || dirty} onClick={() => review("REJECT")}>ปฏิเสธร่าง</button>
              <button className="button button--danger button--full" disabled={stale || !reason.trim() || dirty} onClick={() => review("ESCALATE")}>ส่งต่อให้ทบทวน</button>
            </div>
          </> : <p className="supporting-text">บัญชีแพทย์เป็นผู้ยืนยันร่างส่งต่อ</p>}
          <p className="decision-rail__note"><Icon name="lock" size={15} />ผลคัดกรองไม่ได้มาจากแบบจำลอง แก้หรือลบไม่ได้ และการตัดสินของคุณถูกบันทึกพร้อมชื่อผู้ตรวจ</p>
        </aside>
      </div>
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

  const allSelected = selected.length === items.length;
  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected([]);
    } else {
      setSelected(items.map((p) => p.proposal_id));
    }
  };

  return (
    <form className="proposal-review" onSubmit={(event) => {
      event.preventDefault();
      act(`/runs/${run.run_id}/proposals/accept-batch`, {
        expected_revision: revision,
        idempotency_key: createIdempotencyKey(),
        proposals: items.filter((proposal) => selected.includes(proposal.proposal_id)).map(({ proposal_id, fact }) => ({ proposal_id, fact })),
      });
    }}>
      <div className="section-heading">
        <div><span className="eyebrow">ข้อมูลรอตรวจ</span><h3>ตรวจข้อเสนอจากผู้ช่วย</h3></div>
        <div className="proposal-header-actions">
          <button type="button" className="button button--text button--sm" onClick={toggleSelectAll}>
            {allSelected ? "ยกเลิกการเลือกทั้งหมด" : "เลือกทั้งหมด"}
          </button>
          <StatusBadge tone="warning">{selected.length} / {items.length} รายการที่เลือก</StatusBadge>
        </div>
      </div>
      <p className="supporting-text">ข้อความสนทนายังไม่เป็นข้อมูลยืนยัน เลือกและตรวจทุกค่าก่อนบันทึก</p>
      {items.map((proposal, index) => <div className="proposal-item" key={proposal.proposal_id}>
        <label className="check-control"><input type="checkbox" checked={selected.includes(proposal.proposal_id)} onChange={(event) => setSelected(event.target.checked ? [...selected, proposal.proposal_id] : selected.filter((id) => id !== proposal.proposal_id))} /><span>เลือกบันทึกรายการนี้</span></label>
        <FactEditor fact={proposal.fact} onChange={(fact) => setItems(items.map((item, itemIndex) => itemIndex === index ? { ...item, fact } : item))} />
      </div>)}
      <div className="sticky-action-bar">
        <div className="sticky-action-bar__info">
          <strong>เลือกแล้ว {selected.length} จาก {items.length} รายการ</strong>
          <small>ข้อมูลที่เลือกจะถูกบันทึกเป็นข้อเท็จจริงทางการแพทย์</small>
        </div>
        <button className="button button--primary" disabled={!selected.length}>ยืนยันข้อมูลที่เลือก {selected.length} รายการ</button>
      </div>
    </form>
  );
}

const agentToolLabels: Record<string, string> = {
  read_snapshot: "อ่านข้อมูลเคสล่าสุด",
  conversation: "ตอบข้อความ",
  propose_information: "เสนอข้อมูลที่พบ",
  check_information: "ตรวจข้อมูลที่ยังขาด",
  retrieve_reference: "ดึงแนวทางอ้างอิง",
  create_draft: "เขียนร่างส่งต่อ",
  verify_draft: "ตรวจร่างกับหลักฐาน",
};

// The executed tool steps only (name, status, timing, cited evidence) — never model reasoning.
export function AgentTrace({ run }: { run: Run }) {
  if (!run.trace?.length) return null;
  const seconds = (run.trace.reduce((sum, step) => sum + step.elapsed_ms, 0) / 1000).toFixed(1);
  const design = run.provenance?.design?.design_id;
  return <details className="agent-trace">
    <summary>ขั้นตอนของ agent · {run.trace.length} ขั้น · {seconds} วินาที</summary>
    <ol>{run.trace.map((step) => <li key={step.sequence} className={`agent-trace__step agent-trace__step--${step.status.toLowerCase()}`}>
      <Icon name={step.status === "COMPLETED" ? "check" : "alert"} size={16} />
      <span>{agentToolLabels[step.tool] || step.tool}</span>
      <small>{step.status === "BLOCKED" ? "ถูกระงับ · " : step.status === "FAILED" ? "ไม่สำเร็จ · " : ""}{step.evidence_ids.length ? `อ้างหลักฐาน ${step.evidence_ids.length} · ` : ""}{step.elapsed_ms < 1000 ? `${Math.round(step.elapsed_ms)} ms` : `${(step.elapsed_ms / 1000).toFixed(1)} s`}</small>
    </li>)}</ol>
    {design || run.provenance?.model ? <p className="agent-trace__meta">{design ? `design: ${design}` : ""}{design && run.provenance?.model ? " · " : ""}{run.provenance?.model ? `model: ${run.provenance.model}` : ""}</p> : null}
  </details>;
}
