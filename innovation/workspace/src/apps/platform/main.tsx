import React, { useEffect, useState } from "react";
import { apiCall } from "../../shared/api";
import { Shell, mount, type NavItem } from "../../shared/Shell";
import { useWorkspace } from "../../shared/useWorkspace";
import { CasesPage } from "./CasesPage";
import { SettingsPage } from "./SettingsPage";
import { Research } from "./system";
import { PharmacyPage } from "./journey";
import type { Draft } from "../../shared/types";
type Page = "cases" | "research" | "settings" | "pharmacy";
const pages: Record<string, Page> = { experiments: "research", settings: "settings", pharmacy: "pharmacy" };
function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  return { page: pages[parts[0]] || "cases", id: parts[0] === "cases" ? parts[1] : undefined, pharmacy: parts[0] === "pharmacy" && parts[1] ? decodeURIComponent(parts[1]) : undefined, step: parts[2], draft: parts[0] === "drafts" ? parts[1] : undefined };
}
function PlatformApp() {
  const ws = useWorkspace();
  const [page, setPage] = useState<Page>(route().page);
  const [pharmacyCase, setPharmacyCase] = useState<string | undefined>(route().pharmacy);
  const openRoute = async (role = ws.session?.role) => {
    const next = route();
    if (next.id && ["intake", "facts"].includes(next.step || "")) { location.replace(`/nurse#/voice/${next.id}/${next.step}`); return; }
    setPage(role === "evaluator" && next.page === "cases" ? "research" : role === "pharmacist" && ["research", "cases"].includes(next.page) && !next.id ? "pharmacy" : role !== "pharmacist" && next.page === "pharmacy" ? "cases" : next.page);
    setPharmacyCase(next.pharmacy);
    if (role === "physician" || role === "pharmacist") {
      if (next.id) await ws.load(decodeURIComponent(next.id));
      if (next.draft) { const draft = await apiCall<Draft & { encounter_id: string }>(`/drafts/${next.draft}`); await ws.load(draft.encounter_id); }
    }
  };
  const initialize = async () => { const session = await ws.bootstrap(); await openRoute(session.role); };
  useEffect(() => { ws.work(initialize, true); }, []);
  useEffect(() => { const changed = () => { ws.work(() => openRoute()); }; window.addEventListener("hashchange", changed); return () => window.removeEventListener("hashchange", changed); }, [ws.session]);
  const navigate = (next: Page) => {
    if (ws.unsaved && !window.confirm("มีร่างที่แก้ไขยังไม่บันทึก ต้องการเปลี่ยนหน้าหรือไม่?")) return;
    setPage(next); location.hash = next === "research" ? "#/experiments" : `#/${next}`;
  };
  const changeCase = (id: string) => {
    if (ws.unsaved && !window.confirm("มีร่างที่แก้ไขยังไม่บันทึก ต้องการเปลี่ยนเคสหรือไม่?")) return;
    location.hash = `#/cases/${encodeURIComponent(id)}/draft`;
  };
  const nav: NavItem<Page>[] = [
    ...(ws.session?.role === "physician" || ws.session?.role === "pharmacist" ? [{ id: "cases" as Page, label: "คิวตรวจทบทวน", description: "หลักฐานและร่างรอตัดสินใจ", icon: "cases" as const }] : []),
    ...(ws.session?.role === "pharmacist" ? [{ id: "pharmacy" as Page, label: "ห้องยา", description: "ตรวจคำสั่งยาก่อนจ่าย", icon: "cases" as const }] : []),
    ...(ws.session?.role === "physician" || ws.session?.role === "evaluator" ? [{ id: "research" as Page, label: "การทดลอง workflow", description: "เปรียบเทียบและตรวจผล", icon: "research" as const }] : []),
    { id: "settings", label: "ความพร้อมระบบ", description: "ความสามารถและหลักฐาน", icon: "settings" },
  ];
  return <Shell product="platform" identity={{ name: "MedX Clinical Review", tagline: "ทบทวนข้อมูลทางคลินิก" }} nav={nav} page={page} onNavigate={navigate}
    switchLink={{ href: "/nurse", label: "MedX Intake", icon: "mic" }} title={page === "pharmacy" ? "ห้องยา · Pharma Agent" : page === "cases" ? "ทบทวนข้อมูลทางคลินิก" : page === "research" ? "การทดลอง workflow" : "ความพร้อมระบบ"}
    description="ตรวจหลักฐาน ทบทวนข้อเสนอ และบันทึกการตัดสินใจ" ws={ws} onSignedIn={initialize}>
    {ws.session?.role === "intake" ? <section className="panel"><h2>บัญชีรับข้อมูลใช้งาน MedX Intake</h2><a href="/nurse">เปิดหน้ารับข้อมูลและซักประวัติ</a></section> : !ws.session ? null : page === "settings" ? <SettingsPage session={ws.session} caps={ws.caps} logout={ws.signOut} /> : page === "research" ? <Research /> : page === "pharmacy" ? <PharmacyPage ws={ws} selected={pharmacyCase} /> : <CasesPage ws={ws} changeCase={changeCase} />}
  </Shell>;
}
mount(PlatformApp);
