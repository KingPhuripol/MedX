"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { ClipboardList, FlaskConical, LogOut, Mic, Pill, ShieldAlert, ShieldCheck, Stethoscope } from "lucide-react";
import Wordmark from "@/components/Wordmark";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/LoadingState";
import { api, RUN_KEY, type Role, type User } from "@/lib/demo";

const roleLabel = { nurse: "พยาบาล", physician: "แพทย์", pharmacist: "เภสัชกร" };

// Role work pages backed by the domain APIs (triage, voice, care, pharma). Each page keeps its own RoleGuard.
// Visible label is Thai-first on one line; the English name stays in the accessible name (sr-only span).
const roleTools: Record<Role, { href: string; label: string; en: string; icon: ReactNode }[]> = {
  nurse: [
    { href: "/nurse/triage", label: "คัดกรอง", en: "Triage", icon: <ShieldAlert size={18} /> },
    { href: "/nurse/intake", label: "รับข้อมูลด้วยเสียง", en: "Voice intake", icon: <Mic size={18} /> },
  ],
  physician: [{ href: "/physician/care", label: "ข้อเสนอการดูแล", en: "Care suggestions", icon: <Stethoscope size={18} /> }],
  pharmacist: [
    { href: "/pharmacist/reconcile", label: "ทบทวนยา", en: "Medication reconciliation", icon: <Pill size={18} /> },
  ],
};

function NavLink({ href, label, en, icon, active }: { href: string; label: string; en?: string; icon: ReactNode; active: boolean }) {
  return (
    <Link className={`nav-link ${active ? "active" : ""}`} href={href} aria-current={active ? "page" : undefined}>
      {icon}
      {label}
      {en ? <span className="sr-only"> · {en}</span> : null}
    </Link>
  );
}

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
  // Loading keeps the shell frame (brand + skeleton nav) so the layout does not jump.
  if (!ready)
    return (
      <div className="clinical-shell">
        <aside className="app-nav" aria-label="เมนูหลัก">
          <div className="app-nav-inner">
            <div className="nav-brand">
              <Wordmark />
            </div>
            <div className="nav-links" aria-hidden="true">
              <div className="skeleton nav-skeleton" />
              <div className="skeleton nav-skeleton" />
            </div>
          </div>
        </aside>
        <section className="app-main">
          <div className="page-stack">
            <LoadingState label="กำลังตรวจสอบสิทธิ์…" />
          </div>
        </section>
      </div>
    );
  return (
    <div className="clinical-shell">
      <aside className="app-nav" aria-label="เมนูหลัก">
        <div className="app-nav-inner">
          <div className="nav-brand">
            <Wordmark />
            <span className="role-chip">
              <ShieldCheck size={14} />
              {user ? roleLabel[user.role] : ""}
            </span>
          </div>
          <div className="nav-meta">
            <span className="user-label">บัญชีสังเคราะห์ · {user?.username}</span>
            <span className="run-label">รอบเดโม · {runId ? runId.slice(0, 8) : "ยังไม่เลือก"}</span>
            <Button variant="ghost" onClick={logout}>
              <LogOut size={18} />
              ออกจากระบบ
            </Button>
          </div>
          <nav className="nav-links">
            <NavLink href="/app/queue" label="คิวงาน" icon={<ClipboardList size={18} />} active={pathname === "/app/queue"} />
            {(user ? roleTools[user.role] : []).map((t) => (
              <NavLink key={t.href} {...t} active={pathname.startsWith(t.href)} />
            ))}
            <NavLink href="/demo" label="รอบเดโม" icon={<FlaskConical size={18} />} active={pathname === "/demo"} />
          </nav>
        </div>
      </aside>
      <section className="app-main">{children}</section>
    </div>
  );
}
