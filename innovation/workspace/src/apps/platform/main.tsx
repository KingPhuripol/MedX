import React, { useEffect, useState } from "react";
import { apiCall, createIdempotencyKey, sendApi } from "../../shared/api";
import { Shell, mount, type NavItem } from "../../shared/Shell";
import type { Draft, Fact, Session } from "../../shared/types";
import { useWorkspace } from "../../shared/useWorkspace";
import { deriveRecommendedStep, type ClinicalWorkspaceStep } from "../../shared/workflow";
import { CasesPage } from "./CasesPage";
import { SettingsPage } from "./SettingsPage";
import { Research } from "./system";

/** Pratu Console: case queue, physician review, audit, research and system readiness. */
type Page = "cases" | "research" | "settings";

function parseRoute(): { page: Page; encounter?: string; draft?: string; step?: ClinicalWorkspaceStep } {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "experiments") return { page: "research" };
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "drafts" && parts[1]) return { page: "cases", draft: parts[1], step: "draft" };
  const step = ["intake", "facts", "draft"].includes(parts[2]) ? parts[2] as ClinicalWorkspaceStep : undefined;
  return { page: "cases", encounter: parts[0] === "cases" ? parts[1] : undefined, step };
}
const allowedPage = (role: Session["role"], requested: Page): Page => role === "evaluator" && requested === "cases" ? "research" : requested;
function routeFor(page: Page, encounter?: string, step?: ClinicalWorkspaceStep) {
  if (page === "research") return "#/experiments";
  if (page === "settings") return "#/settings";
  return encounter ? `#/cases/${encodeURIComponent(encounter)}/${step || "intake"}` : "#/cases";
}
const pages: Record<Page, { title: string; description: string }> = {
  cases: { title: "รับข้อมูลให้ครบ ส่งต่ออย่างชัดเจน", description: "พื้นที่ทำงานสำหรับรับข้อมูล ตรวจทาน และเตรียมร่างส่งต่อ" },
  research: { title: "การทดลอง Agent Design", description: "เปรียบเทียบ workflow และตรวจผลการทดลองที่ทำซ้ำได้" },
  settings: { title: "สถานะและความพร้อม", description: "ตรวจบัญชี ความสามารถ และหลักฐานความพร้อมของระบบ" },
};

function PlatformApp() {
  const ws = useWorkspace();
  const [page, setPage] = useState<Page>(parseRoute().page);
  const [clinicalStep, setClinicalStep] = useState<ClinicalWorkspaceStep>(parseRoute().step || "intake");
  const [newCase, setNewCase] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [age, setAge] = useState(40);

  /** Opens a case at the step its state recommends, unless the URL already names one. */
  const openCase = async (id: string, step?: ClinicalWorkspaceStep) => {
    const loaded = await ws.load(id);
    const target = step || deriveRecommendedStep(loaded.facts, loaded.runs, loaded.drafts, loaded.encounter.case_revision);
    setClinicalStep(target);
    if (!step) history.replaceState(null, "", routeFor("cases", id, target));
    return target;
  };
  const initialize = async () => {
    const session = await ws.bootstrap();
    const route = parseRoute(); const permitted = allowedPage(session.role, route.page);
    setPage(permitted); if (permitted !== route.page) location.hash = routeFor(permitted);
    if (session.role === "evaluator") return;
    if (route.encounter) await openCase(decodeURIComponent(route.encounter), route.step);
    if (route.draft) { const draft = await apiCall<Draft & { encounter_id: string }>(`/drafts/${route.draft}`); await openCase(draft.encounter_id, "draft"); history.replaceState(null, "", routeFor("cases", draft.encounter_id, "draft")); }
  };

  useEffect(() => { ws.work(initialize, true); }, []);
  useEffect(() => {
    if (!ws.session) return;
    const routeChanged = () => {
      const route = parseRoute();
      setPage(allowedPage(ws.session!.role, route.page));
      if (route.step) setClinicalStep(route.step);
      if (route.encounter && ws.session!.role !== "evaluator" && route.encounter !== ws.currentRef.current?.encounter_id) ws.work(async () => { await openCase(decodeURIComponent(route.encounter!), route.step); });
    };
    window.addEventListener("hashchange", routeChanged);
    return () => window.removeEventListener("hashchange", routeChanged);
  }, [ws.session]);

  const navigate = (target: Page) => {
    if (ws.unsaved && target !== page && !window.confirm("มีงานที่ยังไม่บันทึก ต้องการออกจากหน้านี้หรือไม่?")) return;
    setPage(target); location.hash = routeFor(target);
  };
  const changeCase = async (id: string) => {
    if (ws.unsaved && ws.current?.encounter_id !== id && !window.confirm("มีข้อความหรือข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนเคสหรือไม่?")) return;
    ws.setEditing(null); await ws.work(async () => { location.hash = routeFor("cases", id, await openCase(id)); });
  };
  const changeClinicalStep = (step: ClinicalWorkspaceStep) => {
    if (!ws.current) return;
    if ((ws.dirty || ws.editing) && step !== clinicalStep && !window.confirm("มีข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนขั้นตอนหรือไม่?")) return;
    setClinicalStep(step); location.hash = routeFor("cases", ws.current.encounter_id, step);
  };
  const newFact = (old?: Fact) => {
    const timestamp = new Date().toISOString();
    ws.setEditing({ event_id: createIdempotencyKey(), kind: old?.kind || "CHIEF_COMPLAINT", state: old?.state || "KNOWN", value: old?.value || "", observed_at: timestamp, available_at_time: timestamp, supersedes_event_id: old?.event_id || null, source: "STAFF_CONFIRMED" });
  };
  const createCase = () => ws.work(async () => {
    await sendApi("/encounters", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": ws.session!.csrf, "Idempotency-Key": createIdempotencyKey() }, body: JSON.stringify({ encounter_id: caseId, age }) });
    setNewCase(false); await ws.loadList(); await ws.load(caseId); setClinicalStep("intake"); location.hash = routeFor("cases", caseId, "intake");
  });
  const saveFact = () => ws.current && ws.editing && ws.work(async () => {
    await apiCall(`/encounters/${ws.current!.encounter_id}/events`, "POST", { expected_revision: ws.current!.case_revision, idempotency_key: createIdempotencyKey(), fact: ws.editing });
    ws.setEditing(null); await ws.load(ws.current!.encounter_id); await ws.loadList();
  });

  const nav: NavItem<Page>[] = ws.session?.role === "evaluator"
    ? [{ id: "research", label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล", icon: "research" }, { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม", icon: "settings" }]
    : [
        { id: "cases", label: "พื้นที่ตรวจเคส", description: "ตรวจข้อมูลและร่างส่งต่อ", icon: "cases" },
        ...(ws.session?.role === "physician" ? [{ id: "research" as Page, label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล", icon: "research" as const }] : []),
        { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม", icon: "settings" },
      ];

  return <Shell product="platform" identity={{ name: "Pratu Console", tagline: "ตรวจเคส ตัดสินใจ และประเมินระบบ" }} nav={nav} page={page} onNavigate={navigate}
    switchLink={{ href: "/nurse#/voice", label: "เปิด Pratu Intake", icon: "mic" }} title={pages[page].title} description={pages[page].description} ws={ws} onSignedIn={initialize}>
    {!ws.session ? null
      : page === "settings" ? <SettingsPage session={ws.session} caps={ws.caps} logout={ws.signOut} />
      : page === "research" ? <Research />
      : <CasesPage cases={ws.cases} current={ws.current} facts={ws.facts} runs={ws.runs} drafts={ws.drafts} session={ws.session} caps={ws.caps} step={clinicalStep} changeStep={changeClinicalStep}
          query={ws.query} setQuery={ws.setQuery} caseStatus={ws.caseStatus} setCaseStatus={ws.setCaseStatus} nextOffset={ws.nextOffset} newCaseOpen={newCase} setNewCaseOpen={setNewCase}
          caseId={caseId} setCaseId={setCaseId} age={age} setAge={setAge} editing={ws.editing} setEditing={ws.setEditing} message={ws.message} setMessage={ws.setMessage}
          busy={ws.busy} job={ws.job} voiceState={ws.voiceState} loadList={() => ws.work(() => ws.loadList())} moreCases={() => ws.nextOffset !== null && ws.work(() => ws.loadList(ws.nextOffset!, true))}
          createCase={createCase} changeCase={changeCase} refresh={() => ws.current && ws.work(async () => { await ws.load(ws.current!.encounter_id); })}
          startRun={ws.startRun} record={ws.record} speak={ws.speak} stopAudio={ws.stopAudio} newFact={newFact} saveFact={saveFact} act={ws.act} trackDirty={ws.trackDirty} />}
  </Shell>;
}

mount(PlatformApp);
