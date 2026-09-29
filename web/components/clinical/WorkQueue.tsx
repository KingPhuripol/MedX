"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  AlertOctagon,
  ArrowRight,
  BriefcaseMedical,
  CheckCircle2,
  AudioLines,
  Clock,
  Mic,
  Pill,
  RefreshCw,
  ShieldAlert,
  Stethoscope,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import { api, RUN_KEY, type QueueCase, type Role, type TaskSummary, type User } from "@/lib/demo";

// MedX Live entry (slice v1): shown only when the build enables voice; the /live route itself always works.
const voiceEnabled = () => process.env.NEXT_PUBLIC_VOICE_ENABLED === "1";
const liveTool = {
  href: "/live",
  title: "เปิด MedX Live",
  text: "สัมภาษณ์ด้วยเสียงภาษาไทยแบบเรียลไทม์ (บทสังเคราะห์เท่านั้น)",
  icon: <AudioLines size={18} />,
};

const roleTitle = { nurse: "คิวรับเข้าและคัดกรอง", physician: "เคสที่รอตรวจโดยแพทย์", pharmacist: "คิวทบทวนข้อมูลยา" };

// Link cards to the role's own work pages. Names avoid "เปิดเคส" (e2e counts those links) and the English nav names.
const roleTools: Record<Role, { href: string; title: string; text: string; icon: ReactNode }[]> = {
  nurse: [
    { href: "/nurse/triage", title: "คัดกรองเคส", text: "ตรวจข้อเสนอการคัดกรอง โดยเห็น red flag ก่อน", icon: <ShieldAlert size={18} /> },
    { href: "/nurse/intake", title: "รับข้อมูลด้วยเสียง", text: "สัมภาษณ์เบื้องต้นด้วยข้อความภาษาไทย", icon: <Mic size={18} /> },
  ],
  physician: [
    { href: "/physician/care", title: "ข้อเสนอการดูแล", text: "ตรวจทานข้อเสนอสำหรับแพทย์ ณ เวลาตัดสินใจ", icon: <Stethoscope size={18} /> },
  ],
  pharmacist: [
    { href: "/pharmacist/reconcile", title: "ทบทวนความสอดคล้องของยา", text: "ตรวจรายการยาจากหลายแหล่งข้อมูล", icon: <Pill size={18} /> },
  ],
};

export default function WorkQueue() {
  const [user, setUser] = useState<User | null>(null),
    [tasks, setTasks] = useState<TaskSummary[]>([]),
    [cases, setCases] = useState<QueueCase[]>([]),
    [runId, setRunId] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  async function load() {
    const run = localStorage.getItem(RUN_KEY) || "";
    setRunId(run);
    if (!run) {
      // No run: still resolve the role so its tool links show.
      try {
        setUser((await api<{ user: User }>("/api/me")).user);
      } catch {
        /* AppShell redirects to /login when unauthenticated */
      }
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [me, q] = await Promise.all([
        api<{ user: User }>("/api/me"),
        api<{ items: TaskSummary[]; cases?: QueueCase[] }>(`/api/demo/v1/runs/${run}/queue`),
      ]);
      setUser(me.user);
      setTasks(q.items);
      setCases(q.cases ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function claim(task: TaskSummary) {
    try {
      await api(`/api/demo/v1/tasks/${task.task_id}/claim`, {
        method: "POST",
        body: JSON.stringify({ run_id: runId, version: task.version }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "รับเคสไม่สำเร็จ");
    }
  }
  const href = (t: TaskSummary) => `/app/cases/${t.case_id}/${t.kind}?run=${runId}`;

  const columns: DataTableColumn<TaskSummary>[] = [
    {
      key: "priority",
      header: "ความสำคัญ",
      render: (t) =>
        t.priority === "critical" ? (
          <StatusChip tone="critical" icon={<AlertOctagon size={16} />}>
            เร่งด่วน
          </StatusChip>
        ) : (
          <StatusChip tone="warning" icon={<Clock size={16} />}>
            ต้องตรวจทาน
          </StatusChip>
        ),
    },
    {
      key: "case",
      hideLabel: true,
      header: "เคส",
      render: (t) => (
        <>
          <strong className="ui-nowrap">{t.case_id}</strong>
          <div className="muted">ข้อมูลสังเคราะห์</div>
        </>
      ),
    },
    {
      key: "task",
      hideLabel: true,
      header: "งานที่ต้องทำ",
      render: (t) => (
        <>
          <strong>{t.label}</strong>
          {t.next_action && t.next_action !== t.label ? <div className="muted">{t.next_action}</div> : null}
        </>
      ),
    },
    {
      key: "owner",
      header: "ผู้รับผิดชอบ",
      render: (t) => (t.owner ? "รับเคสแล้ว" : <span className="muted">ยังไม่มีผู้รับผิดชอบ</span>),
    },
    {
      key: "actions",
      header: "การทำงาน",
      className: "ui-cell-actions",
      hideLabel: true,
      render: (t) => (
        <div className="ui-table__actions">
          {!t.owner ? (
            <Button variant="secondary" onClick={() => claim(t)}>
              รับเคสนี้
            </Button>
          ) : null}
          <Link className="ui-button ui-button--primary" href={href(t)}>
            เปิดเคส <ArrowRight size={18} />
          </Link>
          {voiceEnabled() && user?.role === "nurse" && t.kind === "intake" ? (
            <Link
              className="ui-button ui-button--secondary"
              data-testid="live-entry-task"
              href={`/live?case=${encodeURIComponent(t.case_id)}&run=${encodeURIComponent(runId)}`}
            >
              <AudioLines size={18} /> เปิด MedX Live
            </Link>
          ) : null}
        </div>
      ),
    },
  ];

  const caseColumns: DataTableColumn<QueueCase>[] = [
    {
      key: "safety",
      header: "สัญญาณเตือน",
      render: (c) =>
        c.safety_level === "critical" ? (
          <StatusChip tone="critical" icon={<AlertOctagon size={16} />}>
            พบสัญญาณเร่งด่วน
          </StatusChip>
        ) : c.not_evaluated_count ? (
          <StatusChip tone="warning" icon={<Clock size={16} />}>
            ยังประเมินไม่ครบ ({c.not_evaluated_count} กฎ)
          </StatusChip>
        ) : (
          <StatusChip tone="neutral">ไม่พบสัญญาณจากข้อมูลที่มี</StatusChip>
        ),
    },
    {
      key: "case",
      header: "เคส",
      render: (c) => (
        <>
          <strong>{c.view_only ? c.display_name : c.case_id}</strong>{" "}
          {c.view_only ? (
            <>
              <small className="muted">{c.case_id}</small> <StatusChip tone="info">ดูข้อมูลอย่างเดียว</StatusChip>
            </>
          ) : null}
          <div className="muted">
            {c.sex} · {c.age} ปี{c.view_only ? "" : " · เดโมครบขั้นตอน"}
          </div>
          <div>{c.chief_complaint}</div>
        </>
      ),
    },
    {
      key: "open",
      header: "ดูข้อมูล",
      hideLabel: true,
      className: "ui-cell-actions",
      render: (c) => (
        <div className="ui-table__actions">
          <Link className="ui-button ui-button--secondary" href={`/app/cases/${c.case_id}/overview?run=${runId}`}>
            ดูข้อมูลเคส <span className="sr-only">{c.case_id}</span> <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      ),
    },
  ];

  const tools = user ? [...roleTools[user.role], ...(user.role === "nurse" && voiceEnabled() ? [liveTool] : [])] : [];
  return (
    <div className="page-stack">
      <PageHeader
        title={user ? roleTitle[user.role] : "คิวงานตามบทบาท"}
        subtitle="จัดลำดับตามความปลอดภัยและขั้นตอนที่ต้องดำเนินการต่อ"
        meta={
          <StatusChip tone="neutral" icon={<BriefcaseMedical size={14} />}>
            รอบ {runId ? runId.slice(0, 8) : "—"}
          </StatusChip>
        }
      />
      {error ? (
        <Notice
          tone="critical"
          role="alert"
          title="โหลดข้อมูลไม่สำเร็จ"
          actions={
            <Button variant="secondary" onClick={load}>
              <RefreshCw size={18} />
              ลองโหลดอีกครั้ง
            </Button>
          }
        >
          <p>{error}</p>
        </Notice>
      ) : null}
      {loading ? <LoadingState label="กำลังโหลดคิวงาน…" /> : null}
      {!runId && !loading ? (
        <EmptyState
          icon={<BriefcaseMedical size={28} />}
          title="ยังไม่ได้เริ่มรอบเดโม"
          description={<p>เปิด seeded journey เพื่อสร้างคิวงานสังเคราะห์ที่แยกจากรอบอื่น</p>}
          action={
            <Link className="ui-button ui-button--primary" href="/demo">
              ไปที่รอบเดโม <ArrowRight size={18} />
            </Link>
          }
        />
      ) : null}
      {!loading && runId && !error ? (
        <Section
          title="งานที่ต้องดำเนินการ"
          titleId="queue-title"
          actions={<StatusChip tone="neutral">{tasks.length} รายการ</StatusChip>}
        >
          <DataTable
            columns={columns}
            rows={tasks}
            rowKey={(t) => t.task_id}
            caption="งานที่ต้องดำเนินการ แสดงเฉพาะงานของบทบาทที่เข้าสู่ระบบ"
            empty={
              <EmptyState
                icon={<CheckCircle2 size={28} className="success" />}
                title="ยังไม่มีเคสที่ต้องดำเนินการ"
                description={<p>ตรวจสอบบทบาทที่เข้าสู่ระบบ หรือกลับมาดูคิวอีกครั้งภายหลัง</p>}
              />
            }
          />
        </Section>
      ) : null}
      {!loading && runId && !error && cases.length ? (
        <Section
          title="เคสทั้งหมดในรอบนี้"
          titleId="queue-cases-title"
          actions={<StatusChip tone="neutral">{cases.length} เคส</StatusChip>}
        >
          <p className="muted">เรียงเคสที่พบสัญญาณเตือนก่อน · เคสตัวอย่างสำหรับดูข้อมูลอย่างเดียว ยังไม่เปิดให้ดำเนินการ</p>
          <DataTable
            testId="queue-cases"
            columns={caseColumns}
            rows={cases}
            rowKey={(c) => c.case_id}
            caption="เคสสังเคราะห์ทั้งหมดในรอบนี้ เรียงเคสที่พบสัญญาณเตือนก่อน"
          />
        </Section>
      ) : null}
      {!loading && tools.length ? (
        <Section title="เครื่องมือของบทบาท" titleId="role-tools-title">
          <div className="ui-tool-grid">
            {tools.map((t) => (
              <Link key={t.href} className="ui-tool-card" href={t.href}>
                <strong>
                  {t.icon}
                  {t.title}
                </strong>
                <span>{t.text}</span>
              </Link>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}
