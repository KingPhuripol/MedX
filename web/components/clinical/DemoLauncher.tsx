"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, FlaskConical, Settings, Stethoscope } from "lucide-react";
import AppShell from "@/components/clinical/AppShell";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { Section } from "@/components/ui/Section";
import { StatusChip } from "@/components/ui/StatusChip";
import { api, RUN_KEY, type DemoRun } from "@/lib/demo";

type Journey = { journey_id: string; title: string; description: string; roles: string[]; case_count: number };
export default function DemoLauncher({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [items, setItems] = useState<Journey[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (enabled)
      api<{ items: Journey[] }>("/api/demo/v1/journeys")
        .then((x) => setItems(x.items))
        .catch((e) => {
          if (e.status === 401) router.replace("/login");
          else setError(e.message);
        });
  }, [enabled, router]);
  async function start(id: string) {
    setBusy(true);
    setError("");
    try {
      const run = await api<DemoRun>(`/api/demo/v1/journeys/${id}/runs`, { method: "POST", body: "{}" });
      localStorage.setItem(RUN_KEY, run.run_id);
      router.push("/app/queue");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "สร้างรอบเดโมไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }
  return (
    <AppShell>
      <div className="page-stack">
        <PageHeader
          title="รอบนำเสนอข้อมูลสังเคราะห์"
          subtitle="แต่ละรอบแยก state และประวัติออกจากกัน โดยไม่ลบหรือรีเซ็ตรอบก่อนหน้า"
          meta={
            <StatusChip tone="neutral" icon={<FlaskConical size={14} />}>
              Synthetic only
            </StatusChip>
          }
        />
        {!enabled ? (
          <EmptyState
            icon={<Settings size={28} />}
            title="Demo mode ปิดอยู่"
            description={
              <p>
                ตั้งค่า <code>DEMO_MODE=1</code> แล้วเริ่ม web server ใหม่เพื่อเปิด seeded journey
              </p>
            }
          />
        ) : null}
        {error ? (
          <Notice tone="critical" role="alert" title="โหลดข้อมูลไม่สำเร็จ">
            <p>{error} — ลองอีกครั้ง หากยังพบปัญหาให้แจ้งผู้ดูแลเดโม</p>
          </Notice>
        ) : null}
        {enabled &&
          items.map((j) => (
            <Section key={j.journey_id} title={j.title} titleId={`journey-${j.journey_id}`}>
              <div className="content-grid">
                <div className="stack">
                  <div className="cluster">
                    <Stethoscope size={24} className="text-primary" aria-hidden="true" />
                    <p className="ui-flush">{j.description}</p>
                  </div>
                  <div className="cluster">
                    <StatusChip tone="neutral" icon={<CheckCircle2 size={14} />}>
                      1 เคสสังเคราะห์
                    </StatusChip>
                    <StatusChip tone="info">Nurse → Physician → Pharmacist</StatusChip>
                  </div>
                </div>
                <div className="stack">
                  <p className="muted">
                    ล็อกอินด้วย synthetic account ตามบทบาท ระบบไม่ bypass RBAC และทุก action ถูกบันทึก
                  </p>
                  <Button disabled={busy} onClick={() => start(j.journey_id)}>
                    เริ่มรอบเดโมใหม่ <ArrowRight size={18} />
                  </Button>
                </div>
              </div>
            </Section>
          ))}
      </div>
    </AppShell>
  );
}
