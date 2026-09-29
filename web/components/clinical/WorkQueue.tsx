"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, BriefcaseMedical, CheckCircle2, CircleUserRound, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, RUN_KEY, type TaskSummary, type User } from "@/lib/demo";

const roleTitle = { nurse: "คิวรับเข้าและคัดกรอง", physician: "เคสที่รอตรวจโดยแพทย์", pharmacist: "คิวทบทวนข้อมูลยา" };
export default function WorkQueue() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null),
    [tasks, setTasks] = useState<TaskSummary[]>([]),
    [runId, setRunId] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  async function load() {
    const run = localStorage.getItem(RUN_KEY) || "";
    setRunId(run);
    if (!run) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [me, q] = await Promise.all([
        api<{ user: User }>("/api/me"),
        api<{ items: TaskSummary[] }>(`/api/demo/v1/runs/${run}/queue`),
      ]);
      setUser(me.user);
      setTasks(q.items);
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
  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <h1>{user ? roleTitle[user.role] : "คิวงานตามบทบาท"}</h1>
          <p>จัดลำดับตามความปลอดภัยและขั้นตอนที่ต้องดำเนินการต่อ</p>
        </div>
        <span className="badge">
          <BriefcaseMedical size={14} />
          รอบ {runId ? runId.slice(0, 8) : "—"}
        </span>
      </header>
      {!runId && !loading ? (
        <div className="state-panel">
          <h2>ยังไม่ได้เริ่มรอบเดโม</h2>
          <p>เปิด seeded journey เพื่อสร้างคิวงานสังเคราะห์ที่แยกจากรอบอื่น</p>
          <Link className="ui-button ui-button--primary" href="/demo">
            ไปที่รอบเดโม <ArrowRight size={18} />
          </Link>
        </div>
      ) : null}
      {error ? (
        <div className="error-panel" role="alert">
          <strong>โหลดข้อมูลไม่สำเร็จ</strong>
          <br />
          {error}
          <div style={{ marginTop: 8 }}>
            <Button variant="secondary" onClick={load}>
              <RefreshCw size={18} />
              ลองโหลดอีกครั้ง
            </Button>
          </div>
        </div>
      ) : null}
      {loading ? (
        <>
          <div className="skeleton" />
          <div className="skeleton" />
        </>
      ) : null}
      {!loading && runId && !error ? (
        <section className="card" aria-labelledby="queue-title">
          <div className="cluster" style={{ justifyContent: "space-between" }}>
            <div>
              <h2 id="queue-title" style={{ marginBottom: 4 }}>
                งานที่ต้องดำเนินการ
              </h2>
              <p className="muted" style={{ margin: 0 }}>
                แสดงเฉพาะงานของบทบาทที่เข้าสู่ระบบ
              </p>
            </div>
            <span className="badge">{tasks.length} รายการ</span>
          </div>
          {tasks.length === 0 ? (
            <div className="state-panel">
              <CheckCircle2 size={28} className="success" />
              <h2>ยังไม่มีเคสที่ต้องดำเนินการ</h2>
              <p>ตรวจสอบบทบาทที่เข้าสู่ระบบ หรือกลับมาดูคิวอีกครั้งภายหลัง</p>
            </div>
          ) : (
            <table className="queue-table">
              <thead>
                <tr>
                  <th>ความสำคัญ</th>
                  <th>เคส</th>
                  <th>ขั้นตอน / งานถัดไป</th>
                  <th>ผู้รับผิดชอบ</th>
                  <th>การทำงาน</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => (
                  <tr key={t.task_id}>
                    <td>
                      <span className={`priority ${t.priority === "critical" ? "critical" : "warning"}`}>
                        <AlertTriangle size={16} />
                        {t.priority === "critical" ? "เร่งด่วน" : "ต้องตรวจทาน"}
                      </span>
                    </td>
                    <td>
                      <strong>{t.case_id}</strong>
                      <div className="muted">ข้อมูลสังเคราะห์</div>
                    </td>
                    <td>
                      <strong>{t.label}</strong>
                      <div className="muted">{t.next_action}</div>
                    </td>
                    <td>
                      <span className="cluster">
                        <CircleUserRound size={16} />
                        {t.owner ? "รับเคสแล้ว" : "ยังไม่มีผู้รับผิดชอบ"}
                      </span>
                    </td>
                    <td>
                      <div className="cluster">
                        {!t.owner ? (
                          <Button variant="secondary" onClick={() => claim(t)}>
                            รับเคสนี้
                          </Button>
                        ) : null}
                        <Link className="ui-button ui-button--primary" href={href(t)}>
                          เปิดเคส <ArrowRight size={18} />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : null}
    </div>
  );
}
