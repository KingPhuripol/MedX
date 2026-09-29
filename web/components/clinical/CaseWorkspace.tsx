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
  type LabResult,
  type MedicationData,
  type VitalReading,
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
  view_only: "ดูข้อมูลอย่างเดียว",
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
      } else if (section === "overview") {
        // U6: the shared summary shows medications on first open; a failure leaves them "not loaded", never empty.
        setMeds(await api<MedicationData>(`/api/demo/v1/runs/${run}/cases/${caseId}/medications`).catch(() => null));
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
  const viewOnly = data.view_only === true;
  const critical = data.safety.level === "critical";
  const gatesAck =
    !viewOnly && ((section === "triage" && user?.role === "nurse") || (section === "care" && user?.role === "physician"));
  const pendingMedReview =
    !viewOnly && section === "medications" && user?.role === "pharmacist" && meds?.discrepancies[0]?.status === "pending";
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
      <section
        className={critical ? "safety-banner" : css.calmBanner}
        role={critical ? "alert" : undefined}
        aria-label={critical ? undefined : "ผลตรวจสัญญาณเตือน"}
        data-testid="safety-banner"
        data-level={data.safety.level}
      >
        {critical ? <AlertOctagon size={28} className="critical" /> : <Info size={28} aria-hidden="true" />}
        <div className={css.bannerBody}>
          <h2 className={critical ? "critical" : css.flush}>{data.safety.label}</h2>
          <p>{data.safety.detail}</p>
          {viewOnly ? null : gatesAck ? (
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
      {viewOnly ? (
        <Notice tone="info" icon={<Info size={24} aria-hidden="true" />} data-testid="view-only-notice">
          <p>
            <strong>{data.view_only_label}</strong>
          </p>
        </Notice>
      ) : null}
      <nav className="case-tabs" aria-label="ส่วนของเคส">
        {tabs.map(([slug, label]) => (
          <Link
            key={slug}
            className={`case-tab ${section === slug ? "active" : ""} ${css.tab}`}
            aria-current={section === slug ? "page" : undefined}
            href={`/app/cases/${caseId}/${slug}?run=${runId}`}
          >
            {label}
            {slug === ownTab && !viewOnly ? <StatusChip tone="info">งานของคุณ</StatusChip> : null}
          </Link>
        ))}
      </nav>
      {error ? (
        <Notice tone="critical" role="alert" title="บันทึกข้อมูลไม่สำเร็จ">
          <p>{error} — โหลดข้อมูลล่าสุดก่อนลองอีกครั้ง</p>
        </Notice>
      ) : null}
      {section === "overview" ? <Overview data={data} ownTab={viewOnly ? undefined : ownTab} runId={runId} meds={meds} /> : null}
      {section === "intake" ? (
        <>
          <Intake data={data} />
          {viewOnly ? null : (
            <Section className="desktop-task" title="บันทึก intake ผ่าน domain API เดิม" titleId="intake-domain-title">
              <VoiceIntake embedded />
            </Section>
          )}
        </>
      ) : null}
      {/* Real triage/care assessments live at /nurse/triage/[id] and /physician/care/[id], never under this
          seeded demo case header (a different synthetic patient). */}
      {viewOnly && (section === "triage" || section === "care") ? (
        <EmptyState
          title="ส่วนนี้ยังไม่เปิดให้ดำเนินการสำหรับเคสตัวอย่าง"
          description="เคสตัวอย่างแสดงข้อมูลที่บันทึกไว้และผลจากกฎที่ตรวจได้เท่านั้น ไม่มีข้อเสนอแนะหรือการยืนยัน"
        />
      ) : null}
      {!viewOnly && section === "triage" && data.triage ? (
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
      {!viewOnly && section === "care" && data.care ? (
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
      {section === "medications" ? <MedicationSurface data={meds} note={note} setNote={setNote} viewOnly={viewOnly} /> : null}
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

function Overview({
  data,
  ownTab,
  runId,
  meds,
}: {
  data: CaseOverview;
  ownTab?: string;
  runId: string;
  meds: MedicationData | null;
}) {
  return (
    <div className="page-stack">
      <CaseSummary data={data} meds={meds} runId={runId} />
      <div className="content-grid">
      <section className="card stack">
        <h2>สรุปเคส</h2>
        <p className={css.summary}>{data.summary}</p>
        <dl className="detail-list">
          <dt>สถานะ intake</dt>
          {data.view_only ? (
            <dd>บันทึกไว้ ยังไม่ได้ตรวจทาน</dd>
          ) : (
            <dd className={`success ${css.inlineIcon}`}>
              <CheckCircle2 size={16} aria-hidden="true" /> ตรวจทานแล้ว
            </dd>
          )}
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
        {data.engines ? (
          <EngineSummary engines={data.engines} />
        ) : (
          <>
            <div className="cluster critical">
              <ShieldAlert size={20} />
              <strong>ต้องประเมินเร่งด่วน</strong>
            </div>
            <p>Red flag แสดงก่อนข้อเสนออื่นทุกครั้ง และไม่มีการดำเนินการอัตโนมัติ</p>
          </>
        )}
        <Link className={css.inlineIcon} href={`/app/cases/${data.case_id}/timeline?run=${data.run_id}`}>
          ดู timeline ทั้งหมด <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </aside>
    </div>
    </div>
  );
}

/** U7: what the deterministic engines returned for this case, with versions. A rule not run is never a negative. */
export function EngineSummary({ engines }: { engines: NonNullable<CaseOverview["engines"]> }) {
  const rf = engines.red_flag,
    ph = engines.pharma;
  return (
    <div className="stack" data-testid="engine-summary">
      <p className={css.tight}>
        <strong>Red flag:</strong>{" "}
        <span data-testid="engine-alert-count">
          {rf.alerts.length === 0 ? "ไม่มีการแจ้งเตือนจากข้อมูลที่มีอยู่" : `แจ้งเตือน ${rf.alerts.length} ข้อ`}
        </span>
      </p>
      {rf.alerts.length ? (
        <ul className={css.plainList} data-testid="engine-alerts">
          {rf.alerts.map((a) => (
            <li key={a.rule_id}>
              <strong>{a.rule_id}</strong> {a.name_th} — {a.message_th}
            </li>
          ))}
        </ul>
      ) : null}
      {rf.not_evaluated.length ? (
        <div data-testid="engine-not-evaluated">
          <p className={css.tight}>
            <strong>{rf.not_evaluated_text}</strong> ({rf.not_evaluated.length} จาก {rf.rules_total} กฎ)
          </p>
          <ul className={css.plainList}>
            {rf.not_evaluated.map((n) => (
              <li key={n.rule_id}>
                {n.rule_id} {n.name_th} <span className="muted">— {n.reason_th}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className={`muted ${css.tight}`} data-testid="engine-versions">
        ชุดกฎ red flag {rf.ruleset_version} · กระทบยอดยา {ph.pipeline_version} (กฎ {ph.rules_version}, formulary{" "}
        {ph.formulary_version}) · พบความคลาดเคลื่อน {ph.issue_count} รายการ
      </p>
      <p className={`muted ${css.tight}`}>ผลจากกฎที่กำหนดไว้ล่วงหน้า ไม่ใช้โมเดล ไม่ใช่ข้อสรุปว่าไม่มีความเสี่ยง</p>
    </div>
  );
}

type VitalKey = "hr" | "rr" | "sbp" | "dbp" | "spo2" | "temp_c";
const VITAL_FIELDS: [VitalKey, string, string][] = [
  ["hr", "ชีพจร", "ครั้ง/นาที"],
  ["rr", "หายใจ", "ครั้ง/นาที"],
  ["sbp", "ความดันตัวบน", "mmHg"],
  ["dbp", "ความดันตัวล่าง", "mmHg"],
  ["spo2", "SpO₂", "%"],
  ["temp_c", "อุณหภูมิ", "°C"],
];
/** Change between two recorded values. Describes the recorded numbers only, never a clinical judgement. */
export function vitalDirection(now: number | null, before: number | null | undefined) {
  if (now == null || before == null) return null;
  if (now > before) return { arrow: "↑", word: "เพิ่มขึ้น" };
  if (now < before) return { arrow: "↓", word: "ลดลง" };
  return { arrow: "→", word: "เท่าเดิม" };
}
/** "high" / "low" outside the reference range, "unclassified" when a bound or value is missing, else null. */
export function labFlag(lab: LabResult): "high" | "low" | "unclassified" | null {
  if (lab.value == null) return "unclassified";
  if (lab.ref_low == null && lab.ref_high == null) return "unclassified";
  if (lab.ref_high != null && lab.value > lab.ref_high) return "high";
  if (lab.ref_low != null && lab.value < lab.ref_low) return "low";
  return null;
}

/** U6: the shared case summary (UI-SPEC "Overview"). Shows recorded facts only; missing is shown as missing. */
export function CaseSummary({ data, meds, runId }: { data: CaseOverview; meds: MedicationData | null; runId: string }) {
  const vitals = [...(data.vitals ?? [])].sort((a, b) => a.observed_at.localeCompare(b.observed_at));
  const latest: VitalReading | undefined = vitals[vitals.length - 1];
  const previous: VitalReading | undefined = vitals.length > 1 ? vitals[vitals.length - 2] : undefined;
  const previousMissing = previous
    ? VITAL_FIELDS.filter(([key]) => previous[key] == null).map(([, label]) => label)
    : [];
  const allergies = data.allergies ?? null;
  const labs = data.labs ?? [];
  const flagged = labs.map((lab) => [lab, labFlag(lab)] as const).filter(([, f]) => f !== null);
  const openDiscrepancies = meds ? meds.discrepancies.filter((d) => d.status === "pending").length : null;
  return (
    <div className={css.summaryGrid} data-testid="case-summary">
      <section className={`${css.tile} ${css.vitals}`} aria-labelledby="sum-vitals" data-testid="summary-vitals">
        <h2 id="sum-vitals" className={css.flush}>
          สัญญาณชีพล่าสุด
        </h2>
        {latest ? (
          <>
            <p className={`muted ${css.tight}`}>
              บันทึกเมื่อ {formatThaiTime(latest.observed_at)}
              {previous ? ` · เทียบกับค่าที่บันทึกเมื่อ ${formatThaiTime(previous.observed_at)}` : " · ยังไม่มีค่าก่อนหน้าให้เทียบ"}
            </p>
            <ul className={css.vitalList}>
              {VITAL_FIELDS.map(([key, label, unit]) => {
                const value = latest[key];
                const dir = vitalDirection(value, previous?.[key]);
                return (
                  <li key={key} className={css.vital} data-testid={`vital-${key}`}>
                    <span className="muted">{label}</span>
                    <span className={css.vitalRow}>
                      {value == null ? (
                        <strong className={css.missing}>ไม่มีบันทึก</strong>
                      ) : (
                        <strong>
                          {value} <span className={css.unit}>{unit}</span>
                        </strong>
                      )}
                      <span className={css.dir} data-testid={`vital-${key}-dir`}>
                        {dir ? `${dir.arrow} ${dir.word}` : value == null ? "" : "ไม่มีค่าเทียบ"}
                      </span>
                    </span>
                  </li>
                );
              })}
              <li className={css.vital} data-testid="vital-consciousness">
                <span className="muted">รู้สึกตัว (ACVPU)</span>
                <strong className={latest.consciousness == null ? css.missing : undefined}>
                  {latest.consciousness ?? "ไม่มีบันทึก"}
                </strong>
              </li>
              <li className={css.vital} data-testid="vital-on_oxygen">
                <span className="muted">ออกซิเจนเสริม</span>
                <strong className={latest.on_oxygen == null ? css.missing : undefined}>
                  {latest.on_oxygen == null ? "ไม่มีบันทึก" : latest.on_oxygen ? "ใช้ออกซิเจน" : "ไม่ใช้ออกซิเจน"}
                </strong>
              </li>
            </ul>
            {previousMissing.length ? (
              <p className={css.missing} data-testid="vitals-prev-missing">
                ค่าก่อนหน้าที่ไม่มีบันทึก: {previousMissing.join(", ")}
              </p>
            ) : null}
            <p className={`muted ${css.tight}`}>ลูกศรแสดงการเปลี่ยนของค่าที่บันทึกเท่านั้น ไม่ใช่การประเมินทางคลินิก</p>
          </>
        ) : (
          <p className={css.missing} data-testid="vitals-missing">
            ยังไม่มีบันทึกสัญญาณชีพ
          </p>
        )}
      </section>
      <section className={css.tile} aria-labelledby="sum-complaint" data-testid="summary-complaint">
        <h2 id="sum-complaint" className={css.flush}>
          อาการสำคัญ
        </h2>
        <dl className={css.facts}>
          <dt className="muted">อาการ</dt>
          <dd>{data.intake.chief_complaint}</dd>
          <dt className="muted">เริ่มมีอาการ</dt>
          <dd>{data.intake.onset}</dd>
        </dl>
      </section>
      <section className={css.tile} aria-labelledby="sum-allergy" data-testid="summary-allergy">
        <h2 id="sum-allergy" className={css.flush}>
          ประวัติแพ้
        </h2>
        {allergies === null ? (
          <p className={css.missing} data-testid="allergy-unknown">
            ไม่ทราบสถานะการแพ้ — ต้องถาม
          </p>
        ) : allergies.length === 0 ? (
          <p className={css.tight} data-testid="allergy-none">
            ไม่มีประวัติแพ้ที่บันทึกไว้
          </p>
        ) : (
          <ul className={css.plainList}>
            {allergies.map((a) => (
              <li key={a.substance} data-testid="allergy-item">
                <strong>{a.substance}</strong> — {a.reaction}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className={css.tile} aria-labelledby="sum-meds" data-testid="summary-meds">
        <h2 id="sum-meds" className={css.flush}>
          ยาที่ใช้อยู่
        </h2>
        {meds === null ? (
          <p className={css.missing} data-testid="meds-missing">
            ยังไม่ได้โหลดข้อมูลยา
          </p>
        ) : (
          <>
            {meds.sources.length === 0 ? (
              <p className={css.missing}>ยังไม่มีรายการยาที่บันทึก</p>
            ) : (
              <ul className={css.plainList}>
                {meds.sources.map((m) => (
                  <li key={m.source_id} data-testid="med-item">
                    {m.recorded_value} <span className="muted">({m.label})</span>
                  </li>
                ))}
              </ul>
            )}
            <p className={css.tight} data-testid="med-discrepancy-count">
              ความคลาดเคลื่อนที่ยังไม่ตรวจทาน: <strong>{openDiscrepancies} รายการ</strong>
            </p>
          </>
        )}
        <Link className={css.inlineIcon} href={`/app/cases/${data.case_id}/medications?run=${runId}`}>
          ดูรายละเอียดยา <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </section>
      <section className={css.tile} aria-labelledby="sum-labs" data-testid="summary-labs">
        <h2 id="sum-labs" className={css.flush}>
          ผลแล็บผิดปกติล่าสุด
        </h2>
        {labs.length === 0 ? (
          <p className={css.missing} data-testid="labs-none-yet">
            ยังไม่มีผลแล็บ
          </p>
        ) : flagged.length === 0 ? (
          <p className={css.tight} data-testid="labs-normal">
            ไม่มีผลแล็บผิดปกติ
          </p>
        ) : (
          <ul className={css.plainList}>
            {flagged.map(([lab, flag]) => (
              <li key={lab.test} data-testid="lab-item">
                <strong>{lab.test}</strong>{" "}
                {lab.value == null ? (
                  <span className={css.missing}>ไม่มีค่า</span>
                ) : (
                  <>
                    {lab.value} {lab.unit}
                  </>
                )}{" "}
                <span className={css.dir}>
                  {flag === "high" ? "↑ สูงกว่าช่วงอ้างอิง" : flag === "low" ? "↓ ต่ำกว่าช่วงอ้างอิง" : "ไม่มีช่วงอ้างอิงให้เทียบ"}
                </span>
                {lab.ref_low != null || lab.ref_high != null ? (
                  <span className="muted">
                    {" "}
                    (ช่วงอ้างอิง {lab.ref_low ?? "–"}–{lab.ref_high ?? "–"})
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
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
  viewOnly,
}: {
  data: MedicationData | null;
  note: string;
  setNote: (v: string) => void;
  viewOnly: boolean;
}) {
  if (!data)
    return (
      <EmptyState
        title="ข้อมูลบางส่วนยังไม่พร้อม"
        description="ตรวจรายการที่ทำเครื่องหมายไว้ก่อนดำเนินการต่อ"
      />
    );
  return (
    <div className="content-grid">
      <section className="card stack">
        <div className="cluster">
          <Pill size={24} />
          <h2 className={css.flush}>Medication reconciliation</h2>
        </div>
        {data.sources.length === 0 ? <p className={css.missing}>ยังไม่มีรายการยาที่บันทึก</p> : null}
        {data.sources.map((s) => (
          <article key={s.source_id} className={css.source}>
            <strong>{s.label}</strong>
            <p>{s.recorded_value}</p>
            <span className="muted">
              {s.source_id} · {formatThaiTime(s.captured_at)}
            </span>
          </article>
        ))}
        {viewOnly ? null : (
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
        )}
      </section>
      <aside className="card stack">
        {data.discrepancies.length === 0 ? (
          <p data-testid="med-no-issue">กฎที่ตรวจได้ไม่พบความคลาดเคลื่อนจากแหล่งข้อมูลที่มี ไม่ใช่ข้อสรุปว่ารายการยาถูกต้อง</p>
        ) : null}
        {data.discrepancies.map((d) => (
          <div key={d.review_id} className="stack" data-testid="med-discrepancy">
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
          </div>
        ))}
        {data.engine ? (
          <p className="muted" data-testid="med-engine">
            กระทบยอดยา {data.engine.pipeline_version} · กฎ {data.engine.rules_version} · formulary {data.engine.formulary_version}
          </p>
        ) : null}
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
