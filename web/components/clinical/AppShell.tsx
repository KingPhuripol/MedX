"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { ClipboardList, FlaskConical, LogOut, ShieldCheck } from "lucide-react";
import Wordmark from "@/components/Wordmark";
import { Button } from "@/components/ui/button";
import { api, RUN_KEY, type User } from "@/lib/demo";

const roleLabel={nurse:"พยาบาล",physician:"แพทย์",pharmacist:"เภสัชกร"};

export default function AppShell({children}:{children:ReactNode}){
  const router=useRouter(),pathname=usePathname();
  const [user,setUser]=useState<User|null>(null); const [ready,setReady]=useState(false);
  const [runId,setRunId]=useState("");
  useEffect(()=>{setRunId(localStorage.getItem(RUN_KEY)||"");api<{user:User}>("/api/me").then(x=>{setUser(x.user);setReady(true)}).catch(()=>router.replace("/login"));},[router]);
  async function logout(){await api("/api/auth/logout",{method:"POST"});router.replace("/login");router.refresh();}
  if(!ready)return <div className="app-main"><div className="page-stack" aria-live="polite"><div className="skeleton"/><div className="skeleton"/><p>กำลังตรวจสอบสิทธิ์…</p></div></div>;
  return <div className="clinical-shell">
    <aside className="app-nav" aria-label="เมนูหลัก">
      <div className="nav-brand"><Wordmark/><span className="role-chip"><ShieldCheck size={14}/>{user?roleLabel[user.role]:""}</span></div>
      <nav className="nav-links">
        <Link className={`nav-link ${pathname==="/app/queue"?"active":""}`} href="/app/queue"><ClipboardList size={18}/>คิวงาน</Link>
        <Link className={`nav-link ${pathname==="/demo"?"active":""}`} href="/demo"><FlaskConical size={18}/>รอบเดโม</Link>
      </nav>
      <div className="nav-meta">
        <span className="user-label">บัญชีสังเคราะห์ · {user?.username}</span>
        <span className="run-label">รอบเดโม · {runId?runId.slice(0,8):"ยังไม่เลือก"}</span>
        <Button variant="ghost" onClick={logout}><LogOut size={18}/>ออกจากระบบ</Button>
      </div>
    </aside>
    <section className="app-main">{children}</section>
  </div>;
}
