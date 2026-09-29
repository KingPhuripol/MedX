"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AlertOctagon,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  FileAudio,
  FlaskConical,
  History,
  Info,
  Pill,
  RefreshCw,
  Send,
  ShieldAlert,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { ActionBar } from "@/components/ui/ActionBar";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import VoiceIntake from "@/components/voice/VoiceIntake";
import {
  api,
  formatThaiTime,
  RUN_KEY,
  type CaseOverview,
  type MedicationData,
  type TimelineItem,
  type User,
} from "@/lib/demo";

import css from "./CaseWorkspace.module.css";

const tabs = [
  ["overview", "ภาพรวม"],
  ["intake", "ข้อมูลรับเข้า"],
  ["triage", "คัดกรอง"],
  ["care", "Care review"],
  ["medications", "ข้อมูลยา"],
  ["timeline", "Timeline"],
  ["activity", "กิจกรรม"],
] as const;
/** The tab each role works in (B3b). Only nurse/triage and physician/care carry a gating review. */
const OWN_TAB: Record<string, string> = { nurse: "triage", physician: "care", pharmacist: "medications" };
const stageLabel: Record<string, string> = {
  intake: "รับข้อมูล",
  triage_review: "ทบทวนการคัดกรอง",
  care_review: "ทบทวนโดยแพทย์",
  medication_review: "ทบทวนข้อมูลยา",
  complete: "เสร็จสิ้น",
};

export default function CaseWorkspace({ caseId, section }: { caseId: string; section: string }) {
  const router = useRouter(),
    params = useSearchParams();
  const [runId, setRunId] = useState(""),
    [data, setData] = useState<CaseOverview | null>(null),
    [user, setUser] = useState<User | null>(null),
    [timeline, setTimeline] = useState<TimelineItem[]>([]),
    [meds, setMeds] = useState<MedicationData | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [note, setNote] = useState(""),
    [acknowledged, setAcknowledged] = useState(false),
    [reviewed, setReviewed] = useState(false);
  async function load() {
    const run = params.get("run") || localStorage.getItem(RUN_KEY) || "";
    setRunId(run);
    if (!run) {
      router.replace("/app/queue");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [me, c] = await Promise.all([
        api<{ user: User }>("/api/me"),
        api<CaseOverview>(`/api/demo/v1/runs/${run}/cases/${caseId}`),
      ]);
      setUser(me.user);
      setData(c);
      if (section === "timeline" || section === "activity") {
        const t = await api<{ items: TimelineItem[] }>(`/api/demo/v1/runs/${run}/cases/${caseId}/timeline`);
        setTimeline(t.items);
      }
      if (section === "medications") {
        setMeds(await api<MedicationData>(`/api/demo/v1/runs/${run}/cases/${caseId}/medications`));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [caseId, section]);
  async function handoff() {
    if (!data || !user) return;
    const to = user.role === "nurse" ? "physician" : "pharmacist";
    const task = user.role === "nurse" ? "task-triage-017" : "task-care-017";
    setBusy(true);
    try {
      await api(`/api/demo/v1/tasks/${task}/handoffs`, {
        method: "POST",
        body: JSON.stringify({
          run_id: runId,
          to_role: to,
          note,
          version: data.version,
          acknowledged_alerts: acknowledged ? ["red-flag-017"] : [],
        }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "ส่งต่อไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }
  async function taskReview(action: "confirm" | "edit" | "reject") {
    if (!data || !user) return;
    const task = user.role === "nurse" ? "task-triage-017" : "task-care-017";
    setBusy(true);
    setError("");
    try {
      await api(`/api/demo/v1/tasks/${task}/reviews/${action}`, {
        method: "POST",
        body: JSON.stringify({
          run_id: runId,
          version: data.version,
          reason: note,
          acknowledged_alerts: acknowledged ? ["red-flag-017"] : [],
        }),
      });
      setReviewed(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "บันทึกการตรวจทานไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }
  async function medicationReview(action: "confirm" | "edit" | "reject") {
    const review = meds?.discrepancies[0];
    if (!review) return;
    setBusy(true);
    try {
      await api(`/api/demo/v1/medication-reviews/${review.review_id}/${action}`, {
        method: "POST",
        body: JSON.stringify({
          run_id: runId,
          version: review.version,
          reason: action === "confirm" ? "" : note,
          final_value: action === "edit" ? note : null,
        }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "บันทึกการตรวจทานไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }
  if (loading)
    return (
      <div className="page-stack">
        <LoadingState label="กำลังโหลดข้อมูลเคส…" rows={3} />
      </div>
    );
  if (error && !data)
    return (
      <Notice
        tone="critical"
        role="alert"
        title="โหลดข้อมูลไม่สำเร็จ"
        actions={
          <div>
            <Button variant="secondary" onClick={load}>
              <RefreshCw size={18} />
              ลองโหลดอีกครั้ง
            </Button>
          </div>
        }
      >
        <p>{error}</p>
      </Notice>
    );
  if (!data) return null;
  const ownTab = user ? OWN_TAB[user.role] : undefined;
  // B3a: the acknowledgement only renders where a review it gates is present.
  const gatesAck = (section === "triage" && user?.role === "nurse") || (section === "care" && user?.role === "physician");
  const pendingMedReview =
    section === "medications" && user?.role === "pharmacist" && meds?.discrepancies[0]?.status === "pending";
  return (
    <div className="page-stack">
      <header className="card case-header" aria-label="ข้อมูลประจำเคส">
        <div>
          <div className="cluster">
            <span className="badge">
              <FlaskConical size={14} />
              Synthetic
            </span>
            <span className="muted">{data.case_id}</span>
          </div>
          <h1>{data.display_name}</h1>
          <p className="muted">
            {data.demographics.sex} · {data.demographics.age} ปี · {data.demographics.hn}
          </p>
        </div>
        <div className="case-fact">
          <span>ขั้นตอน</span>
          <strong>{stageLabel[data.stage] || data.stage}</strong>
        </div>
        <div className="case-fact">
          <span>ผู้รับผิดชอบ</span>
          <strong>{data.owner.display}</strong>
        </div>
        <div className="case-fact">
          <span>งานถัดไป</span>
          <strong>{data.next_action}</strong>
        </div>
      </header>
      <section className="safety-banner" role="alert">
        <AlertOctagon size={28} className="critical" />
        <div className={css.bannerBody}>
          <h2 className="critical">{data.safety.label}</h2>
          <p>{data.safety.detail}</p>
          {gatesAck ? (
            <label className={css.ackRow}>
              <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
              <span>รับทราบ red flag และจะให้บุคลากรประเมินโดยตรง</span>
            </label>
          ) : (
            <div>
              <StatusChip tone="critical">ต้องให้บุคลากรประเมินโดยตรง</StatusChip>
            </div>
          )}
        </div>
      </section>
      <nav className="case-tabs" aria-label="ส่วนของเคส">
        {tabs.map(([slug, label]) => (
          <Link
            key={slug}
            className={`case-tab ${section === slug ? "active" : ""} ${css.tab}`}
            aria-current={section === slug ? "page" : undefined}
            href={`/app/cases/${caseId}/${slug}?run=${runId}`}
          >
            {label}
            {slug === ownTab ? <StatusChip tone="info">งานของคุณ</StatusChip> : null}
          </Link>
        ))}
      </nav>
      {error ? (
        <Notice tone="critical" role="alert" title="บันทึกข้อมูลไม่สำเร็จ">
          <p>{error} — โหลดข้อมูลล่าสุดก่อนลองอีกครั้ง</p>
        </Notice>
      ) : null}
      {section === "overview" ? <Overview data={data} ownTab={ownTab} runId={runId} /> : null}
      {section === "intake" ? (
        <>
          <Intake data={data} />
          <Section className="desktop-task" title="บันทึก intake ผ่าน domain API เดิม" titleId="intake-domain-title">
            <VoiceIntake embedded />
          </Section>
        </>
      ) : null}
      {/* Real triage/care assessments live at /nurse/triage/[id] and /physician/care/[id], never under this
          seeded demo case header (a different synthetic patient). */}
      {section === "triage" ? (
        <ReviewSurface
          icon={<ShieldAlert size={24} />}
          title="ทบทวนข้อเสนอการคัดกรอง"
          suggestion={data.triage.suggestion}
          meta={`หน่วยงานที่เสนอ: ${data.triage.department}`}
          evidence={data.triage.evidence_ids}
          note={note}
          setNote={setNote}
        />
      ) : null}
      {section === "care" ? (
        <ReviewSurface
          icon={<Stethoscope size={24} />}
          title="ทบทวน Care suggestion"
          suggestion={data.care.suggestion}
          meta="ไม่ใช่การวินิจฉัยหรือคำแนะนำการรักษา"
          evidence={data.care.evidence_ids}
          note={note}
          setNote={setNote}
        />
      ) : null}
      {section === "medications" ? <MedicationSurface data={meds} note={note} setNote={setNote} /> : null}
      {section === "timeline" || section === "activity" ? (
        <Timeline items={timeline} audit={section === "activity"} />
      ) : null}
      {gatesAck ? (
        <ActionBar
          summary={
            <>
              <strong>{reviewed ? "ตรวจทานโดยบุคลากรแล้ว" : "ต้องให้บุคลากรยืนยัน"}</strong>
              <div className="muted">
                {reviewed || acknowledged
                  ? "บันทึกตัวตน เวลา และเวอร์ชันแบบ append-only"
                  : "รับทราบ red flag ก่อนจึงจะยืนยันได้"}
              </div>
            </>
          }
        >
          {!reviewed ? (
            <>
              <Button variant="secondary" disabled={busy || !acknowledged || !note} onClick={() => taskReview("edit")}>
                แก้ไขก่อนยืนยัน
              </Button>
              <Button variant="danger" disabled={busy || !acknowledged || !note} onClick={() => taskReview("reject")}>
                ปฏิเสธข้อเสนอแนะ
              </Button>
              <Button disabled={busy || !acknowledged} onClick={() => taskReview("confirm")}>
                ยืนยันข้อเสนอแนะ <CheckCircle2 size={18} />
              </Button>
            </>
          ) : (
            <Button disabled={busy || !acknowledged} onClick={handoff}>
              {user?.role === "nurse" ? "ส่งต่อให้แพทย์" : "ส่งต่อให้เภสัชกร"}
              <Send size={18} />
            </Button>
          )}
        </ActionBar>
      ) : null}
      {pendingMedReview ? (
        <ActionBar
          summary={
            <>
              <strong>Medication review</strong>
              <div className="muted">ตรวจแหล่งข้อมูลและ provenance ก่อนบันทึก</div>
            </>
          }
        >
          <Button variant="secondary" disabled={busy || !note} onClick={() => medicationReview("edit")}>
            แก้ไขก่อนยืนยัน
          </Button>
          <Button variant="danger" disabled={busy || !note} onClick={() => medicationReview("reject")}>
            ปฏิเสธข้อเสนอแนะ
          </Button>
          <Button disabled={busy} onClick={() => medicationReview("confirm")}>
            ยืนยันข้อเสนอแนะ <CheckCircle2 size={18} />
          </Button>
        </ActionBar>
      ) : null}
    </div>
  );
}

function Overview({ data, ownTab, runId }: { data: CaseOverview; ownTab?: string; runId: string }) {
  return (
    <div className="content-grid">
      <section className="card stack">
        <h2>สรุปเคส</h2>
        <p className={css.summary}>{data.summary}</p>
        <dl className="detail-list">
          <dt>อาการสำคัญ</dt>
          <dd>{data.intake.chief_complaint}</dd>
          <dt>เริ่มมีอาการ</dt>
          <dd>{data.intake.onset}</dd>
          <dt>สถานะ intake</dt>
          <dd className={`success ${css.inlineIcon}`}>
            <CheckCircle2 size={16} aria-hidden="true" /> ตรวจทานแล้ว
          </dd>
        </dl>
        {ownTab ? (
          <div>
            <Link className="ui-button ui-button--primary" href={`/app/cases/${data.case_id}/${ownTab}?run=${runId}`}>
              ไปที่งานของคุณ <ArrowRight size={18} aria-hidden="true" />
            </Link>
          </div>
        ) : null}
      </section>
      <aside className="card stack">
        <h2>ภาพรวมความปลอดภัย</h2>
        <div className="cluster critical">
          <ShieldAlert size={20} />
          <strong>ต้องประเมินเร่งด่วน</strong>
        </div>
        <p>Red flag แสดงก่อนข้อเสนออื่นทุกครั้ง และไม่มีการดำเนินการอัตโนมัติ</p>
        <Link className={css.inlineIcon} href={`/app/cases/${data.case_id}/timeline?run=${data.run_id}`}>
          ดู timeline ทั้งหมด <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </aside>
    </div>
  );
}
function Intake({ data }: { data: CaseOverview }) {
  return (
    <div className="content-grid">
      <section className="card stack">
        <div className="cluster">
          <FileAudio size={24} />
          <h2 className={css.flush}>ข้อมูลรับเข้า</h2>
        </div>
        <dl className="detail-list">
          <dt>อาการสำคัญ</dt>
          <dd>{data.intake.chief_complaint}</dd>
          <dt>เวลาเริ่ม</dt>
          <dd>{data.intake.onset}</dd>
          <dt>แหล่งข้อมูล</dt>
          <dd>{data.intake.source}</dd>
        </dl>
        <Notice tone="info" icon={<Info size={24} aria-hidden="true" />} title="การแก้ transcript ใช้หน้าจอขนาดใหญ่">
          <p>ทำงานนี้ต่อบนแท็บเล็ตหรือเดสก์ท็อป สถานะรอบเดโมและเคสจะยังคงอยู่</p>
        </Notice>
      </section>
      <aside className="card">
        <h2>หลักฐานและที่มา</h2>
        <p>บทสนทนาจำลองภาษาไทย</p>
        <p className="muted">data_class: synthetic · status: {data.intake.status}</p>
      </aside>
    </div>
  );
}
function ReviewSurface({
  icon,
  title,
  suggestion,
  meta,
  evidence,
  note,
  setNote,
}: {
  icon: React.ReactNode;
  title: string;
  suggestion: string;
  meta: string;
  evidence: string[];
  note: string;
  setNote: (v: string) => void;
}) {
  return (
    <div className="content-grid">
      <section className="card stack">
        <div className="cluster">
          {icon}
          <h2 className={css.flush}>{title}</h2>
        </div>
        <div className={css.suggestion}>
          <p className="muted">ข้อเสนอจากระบบ — ต้องให้บุคลากรยืนยัน</p>
          <p className={css.suggestionText}>{suggestion}</p>
          <p>{meta}</p>
        </div>
        <div className="form-field">
          <label htmlFor="review-note">บันทึกประกอบการตรวจทาน</label>
          <textarea
            id="review-note"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="ระบุเหตุผลเมื่อแก้ไข ปฏิเสธ หรือส่งต่อพร้อมข้อสังเกต"
          />
        </div>
      </section>
      <aside className="card stack">
        <div className="cluster">
          <BookOpen size={20} />
          <h2 className={css.flush}>หลักฐานและที่มา</h2>
        </div>
        <ul className={css.evidenceList}>
          {evidence.map((id) => (
            <li key={id}>{id}</li>
          ))}
        </ul>
        <p className="muted">แสดง evidence ID และ metadata เพื่อการตรวจสอบ ไม่ใช่เหตุผลทางคลินิกที่ระบบสร้างใหม่</p>
      </aside>
    </div>
  );
}
function MedicationSurface({
  data,
  note,
  setNote,
}: {
  data: MedicationData | null;
  note: string;
  setNote: (v: string) => void;
}) {
  if (!data)
    return (
      <EmptyState
        title="ข้อมูลบางส่วนยังไม่พร้อม"
        description="ตรวจรายการที่ทำเครื่องหมายไว้ก่อนดำเนินการต่อ"
      />
    );
  const d = data.discrepancies[0];
  return (
    <div className="content-grid">
      <section className="card stack">
        <div className="cluster">
          <Pill size={24} />
          <h2 className={css.flush}>Medication reconciliation</h2>
        </div>
        {data.sources.map((s) => (
          <article key={s.source_id} className={css.source}>
            <strong>{s.label}</strong>
            <p>{s.recorded_value}</p>
            <span className="muted">
              {s.source_id} · {formatThaiTime(s.captured_at)}
            </span>
          </article>
        ))}
        <div className="form-field">
          <label htmlFor="med-note">เหตุผลหรือค่าที่แก้ไข</label>
          <textarea
            id="med-note"
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="จำเป็นเมื่อแก้ไขหรือปฏิเสธ"
          />
        </div>
      </section>
      <aside className="card stack">
        <div className="cluster warning">
          <AlertOctagon size={20} />
          <h2 className={css.flush}>{d.label}</h2>
        </div>
        <p>{d.detail}</p>
        <div className="cluster">
          <StatusChip tone={d.status === "pending" ? "warning" : "success"}>
            {d.status === "pending" ? "รอตรวจทาน" : "ตรวจทานแล้ว"}
          </StatusChip>
          <StatusChip tone="neutral">version {d.version}</StatusChip>
        </div>
        <p className="muted">Provenance: {d.provenance.join(" · ")}</p>
      </aside>
    </div>
  );
}
function Timeline({ items, audit }: { items: TimelineItem[]; audit: boolean }) {
  return (
    <section className="card">
      <div className="cluster">
        <History size={24} />
        <h2 className={css.flush}>{audit ? "ประวัติกิจกรรมแบบ append-only" : "Timeline ของเคส"}</h2>
      </div>
      {items.length === 0 ? (
        <EmptyState
          title="ยังไม่มีรายการใน timeline"
          description="กิจกรรมจะปรากฏหลังมีการรับเคส ตรวจทาน หรือส่งต่อ"
        />
      ) : (
        <ol className={`timeline ${css.timeline}`}>
          {items.map((i) => (
            <li key={i.event_id}>
              <span className="timeline-dot" />
              <div>
                <strong>{i.title}</strong>
                <p className={css.tight}>{i.detail}</p>
                <span className={`muted ${css.inlineIcon}`}>
                  <Clock3 size={14} aria-hidden="true" /> {formatThaiTime(i.timestamp)} · {i.actor.display || i.actor.role}{" "}
                  · v{i.version}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
