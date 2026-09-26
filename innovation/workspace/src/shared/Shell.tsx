import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/prompt/400.css";
import "@fontsource/prompt/500.css";
import "@fontsource/prompt/600.css";
import "@fontsource/prompt/700.css";
import "./tokens.css";
import "./style.css";
import "./redesign.css";
import "./medx.css";
import { ApiError, apiCall, hasPendingRequest, retryPendingRequest } from "./api";
import type { Session } from "./types";
import type { Workspace } from "./useWorkspace";
import { BrandLogo } from "./ui/BrandLogo";
import { Icon, type IconName } from "./ui/Icon";
import { StatusBadge } from "./ui/StatusBadge";
import { LoginPage } from "./LoginPage";

export type NavItem<P extends string> = { id: P; label: string; description: string; icon: IconName };

const roleLabels: Record<Session["role"], string> = { intake: "ผู้รับข้อมูล", physician: "แพทย์ผู้ตรวจ", pharmacist: "เภสัชกร", evaluator: "ผู้ประเมินระบบ" };

/** Chrome shared by both apps: navigation, safety banner, request status and the sign-in gate.
 *
 * Each app passes only its own navigation; neither can reach the other's pages. */
export function Shell<P extends string>({ product, identity, nav, page, onNavigate, switchLink, title, description, ws, onSignedIn, children }: {
  product: "nurse" | "platform";
  identity: { name: string; tagline: string };
  nav: NavItem<P>[];
  page: P;
  onNavigate: (page: P) => void;
  switchLink: { href: string; label: string; icon: IconName };
  title: string;
  description: string;
  ws: Workspace;
  onSignedIn: () => Promise<void>;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [token, setToken] = useState("");
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const { session, caps, job, busy, error } = ws;
  const navigate = (target: P) => { setMenuOpen(false); onNavigate(target); window.requestAnimationFrame(() => menuButtonRef.current?.focus()); };
  const login = () => ws.work(async () => {
    await apiCall("/session", "POST", { token }).catch((reason) => { throw reason instanceof ApiError && reason.code === "AUTHENTICATION_REQUIRED" ? Error("รหัสเข้าถึงไม่ถูกต้อง กรุณาตรวจแล้วลองอีกครั้ง") : reason; });
    setToken(""); await onSignedIn();
  });

  return <div className={`app-shell app-shell--${product} ${session ? "app-shell--signed-in" : "app-shell--signed-out"}`}>
    <a className="skip-link" href="#main">ข้ามไปเนื้อหา</a>
    <button ref={menuButtonRef} className="mobile-menu button button--secondary" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>เมนู</button>
    {menuOpen ? <button className="nav-backdrop" aria-label="ปิดเมนู" onClick={() => { setMenuOpen(false); menuButtonRef.current?.focus(); }} /> : null}
    <aside className={`navigation ${menuOpen ? "navigation--open" : ""}`} aria-label="เมนูหลัก">
      <BrandLogo />
      <div className="surface-identity"><strong>{identity.name}</strong><span>{identity.tagline}</span></div>
      <div className="pilot-label"><StatusBadge tone="info">ข้อมูลสังเคราะห์เท่านั้น</StatusBadge><p>พื้นที่ทดลองภายใต้การดูแล</p></div>
      <nav id="primary-navigation">{nav.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "nav-item--active" : ""}`} aria-current={page === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><span className="nav-item__icon"><Icon name={item.icon} /></span><span className="nav-item__copy"><span>{item.label}</span><small>{item.description}</small></span></button>)}</nav>
      <a className="surface-switch" href={switchLink.href}><Icon name={switchLink.icon} /><span>{switchLink.label}</span></a>
      <div className="navigation__footer">{session ? <><span className="avatar" aria-hidden="true">{session.subject.slice(0, 1).toUpperCase()}</span><div><strong>{session.subject}</strong><span>{roleLabels[session.role]}</span></div><button className="button button--text" onClick={ws.signOut}>ออกจากระบบ</button></> : <span>ระบบต้นแบบ</span>}</div>
    </aside>
    <div className="app-body">
      <header className="topbar"><div><span className="eyebrow">RESEARCH PROTOTYPE · HUMAN REVIEW REQUIRED</span><h1>{title}</h1><p className="topbar__subtitle">{description}</p></div><StatusBadge tone={caps?.provider === "mock-v2" ? "warning" : "info"}>{caps?.provider === "mock-v2" ? "Offline · Mock provider" : "รอผลประเมินโมเดลจริง"}</StatusBadge></header>
      <div className="synthetic-banner" role="note"><span aria-hidden="true">i</span><div><strong>พื้นที่ทดลองสำหรับข้อมูลสังเคราะห์</strong><p>ต้องมีบุคลากรตรวจทุกครั้ง · ระบบไม่วินิจฉัย สั่งยา สั่งตรวจ หรือส่งต่อผู้ป่วย</p></div></div>
      <main id="main" tabIndex={-1}>
        <div className="global-status" aria-live="polite">
          {job && ["queued", "running"].includes(job.status) ? <div className="inline-message inline-message--info"><div><strong>{job.status === "queued" ? "งานอยู่ในคิว" : "ผู้ช่วยกำลังทำงาน"}</strong><span>เคส {job.encounter_id}</span></div><button className="button button--text" onClick={ws.cancelJob}>ยกเลิกงาน</button></div> : null}
          {busy ? <div className="inline-message inline-message--info" role="status"><span className="spinner" aria-hidden="true" />กำลังดำเนินการ กรุณารอสักครู่</div> : null}
          {error ? <div role="alert" className="inline-message inline-message--danger"><div><strong>ดำเนินการไม่สำเร็จ</strong><span>{error}</span></div>{hasPendingRequest() ? <button className="button button--secondary" onClick={() => ws.work(async () => { await retryPendingRequest(); if (ws.currentRef.current) await ws.load(ws.currentRef.current.encounter_id); })}>ตรวจคำขอเดิม</button> : null}</div> : null}
        </div>
        {session ? children : <LoginPage token={token} setToken={setToken} busy={busy} login={login} />}
      </main>
      <footer>ต้นแบบสำหรับข้อมูลสังเคราะห์ · ไม่มีการส่งต่อหรือดำเนินการรักษาภายนอกระบบ</footer>
    </div>
  </div>;
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="fatal-error"><section className="panel"><span className="eyebrow">ระบบหยุดอย่างปลอดภัย</span><h1>เปิดพื้นที่ทำงานใหม่</h1><p>หน้าจอพบข้อผิดพลาด ข้อมูลที่บันทึกแล้วไม่ถูกแก้ไข กรุณาโหลดหน้าใหม่ก่อนทำรายการต่อ</p><button className="button button--primary" onClick={() => location.reload()}>โหลดหน้าใหม่</button></section></main>;
    return this.props.children;
  }
}

export function mount(App: () => React.ReactElement) {
  const root = document.getElementById("root");
  if (root) createRoot(root).render(<ErrorBoundary><App /></ErrorBoundary>);
}
