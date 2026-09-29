"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, FlaskConical, Stethoscope } from "lucide-react";
import AppShell from "@/components/clinical/AppShell";
import { Button } from "@/components/ui/button";
import { api, RUN_KEY, type DemoRun } from "@/lib/demo";

type Journey={journey_id:string;title:string;description:string;roles:string[];case_count:number};
export default function DemoLauncher({enabled}:{enabled:boolean}){
 const router=useRouter();const [items,setItems]=useState<Journey[]>([]);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 useEffect(()=>{if(enabled)api<{items:Journey[]}>("/api/demo/v1/journeys").then(x=>setItems(x.items)).catch(e=>{if(e.status===401)router.replace("/login");else setError(e.message)})},[enabled,router]);
 async function start(id:string){setBusy(true);setError("");try{const run=await api<DemoRun>(`/api/demo/v1/journeys/${id}/runs`,{method:"POST",body:"{}"});localStorage.setItem(RUN_KEY,run.run_id);router.push("/app/queue");router.refresh()}catch(e){setError(e instanceof Error?e.message:"สร้างรอบเดโมไม่สำเร็จ")}finally{setBusy(false)}}
 return <AppShell><div className="page-stack">
  <header className="page-heading"><div><h1>รอบนำเสนอข้อมูลสังเคราะห์</h1><p>แต่ละรอบแยก state และประวัติออกจากกัน โดยไม่ลบหรือรีเซ็ตรอบก่อนหน้า</p></div><span className="badge"><FlaskConical size={14}/>Synthetic only</span></header>
  {!enabled?<div className="state-panel"><h2>Demo mode ปิดอยู่</h2><p>ตั้งค่า <code>DEMO_MODE=1</code> แล้วเริ่ม web server ใหม่เพื่อเปิด seeded journey</p></div>:null}
  {error?<div className="error-panel" role="alert"><strong>โหลดข้อมูลไม่สำเร็จ</strong><br/>{error} — ลองอีกครั้ง หากยังพบปัญหาให้แจ้งผู้ดูแลเดโม</div>:null}
  {enabled&&items.map(j=><article className="card content-grid" key={j.journey_id}>
    <div className="stack"><div className="cluster"><Stethoscope size={24} className="text-primary"/><h2 style={{margin:0}}>{j.title}</h2></div><p>{j.description}</p><div className="cluster"><span className="badge"><CheckCircle2 size={14}/>1 เคสสังเคราะห์</span><span className="badge">Nurse → Physician → Pharmacist</span></div></div>
    <div className="stack"><p className="muted">ล็อกอินด้วย synthetic account ตามบทบาท ระบบไม่ bypass RBAC และทุก action ถูกบันทึก</p><Button disabled={busy} onClick={()=>start(j.journey_id)}>เริ่มรอบเดโมใหม่ <ArrowRight size={18}/></Button></div>
  </article>)}
 </div></AppShell>;
}
