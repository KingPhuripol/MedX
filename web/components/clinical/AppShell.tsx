"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { ClipboardList, FlaskConical, LogOut, Mic, Pill, ShieldAlert, ShieldCheck, Stethoscope } from "lucide-react";
import Wordmark from "@/components/Wordmark";
import { Button } from "@/components/ui/button";
import { api, RUN_KEY, type Role, type User } from "@/lib/demo";

const roleLabel = { nurse: "พยาบาล", physician: "แพทย์", pharmacist: "เภสัชกร" };

// Role work pages backed by the domain APIs (triage, voice, care, pharma). Each page keeps its own RoleGuard.
const roleTools: Record<Role, { href: string; label: string; icon: ReactNode }[]> = {
  nurse: [
    { href: "/nurse/triage", label: "คัดกรอง · Triage", icon: <ShieldAlert size={18} /> },
    { href: "/nurse/intake", label: "รับข้อมูลด้วยเสียง · Voice intake", icon: <Mic size={18} /> },
  ],
  physician: [{ href: "/physician/care", label: "Care suggestions", icon: <Stethoscope size={18} /> }],
  pharmacist: [{ href: "/pharmacist/reconcile", label: "Medication reconciliation", icon: <Pill size={18} /> }],
};

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter(),
    pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [runId, setRunId] = useState("");
  useEffect(() => {
    setRunId(localStorage.getItem(RUN_KEY) || "");
    api<{ user: User }>("/api/me")
      .then((x) => {
        setUser(x.user);
        setReady(true);
      })
      .catch(() => router.replace("/login"));
  }, [router]);
  async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }
  if (!ready)
    return (
      <div className="app-main">
        <div className="page-stack" aria-live="polite">
          <div className="skeleton" />
          <div className="skeleton" />
          <p>กำลังตรวจสอบสิทธิ์…</p>
        </div>
      </div>
    );
  const navLink = (href: string, label: string, icon: ReactNode, active: boolean) => (
    <Link
      key={href}
      className={`nav-link ${active ? "active" : ""}`}
      href={href}
      aria-current={active ? "page" : undefined}
    >
      {icon}
      {label}
    </Link>
  );
  return (
    <div className="clinical-shell">
      <aside className="app-nav" aria-label="เมนูหลัก">
        <div className="nav-brand">
          <Wordmark />
          <span className="role-chip">
            <ShieldCheck size={14} />
            {user ? roleLabel[user.role] : ""}
          </span>
        </div>
        <nav className="nav-links">
          {navLink("/app/queue", "คิวงาน", <ClipboardList size={18} />, pathname === "/app/queue")}
          {(user ? roleTools[user.role] : []).map((t) => navLink(t.href, t.label, t.icon, pathname.startsWith(t.href)))}
          {navLink("/demo", "รอบเดโม", <FlaskConical size={18} />, pathname === "/demo")}
        </nav>
        <div className="nav-meta">
          <span className="user-label">บัญชีสังเคราะห์ · {user?.username}</span>
          <span className="run-label">รอบเดโม · {runId ? runId.slice(0, 8) : "ยังไม่เลือก"}</span>
          <Button variant="ghost" onClick={logout}>
            <LogOut size={18} />
            ออกจากระบบ
          </Button>
        </div>
      </aside>
      <section className="app-main">{children}</section>
    </div>
  );
}
