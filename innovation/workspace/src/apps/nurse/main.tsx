import React, { useEffect } from "react";
import { Shell, mount } from "../../shared/Shell";
import { useWorkspace } from "../../shared/useWorkspace";
import { VoicePage } from "./VoicePage";

/** Pratu Intake: one job, voice-assisted history taking. Review, audit and research live on /platform. */
const encounterFromHash = () => {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return ["voice", "cases"].includes(parts[0]) && parts[1] ? decodeURIComponent(parts[1]) : undefined;
};
const platformCase = (id?: string) => id ? `/platform#/cases/${encodeURIComponent(id)}/intake` : "/platform#/cases";

function NurseApp() {
  const ws = useWorkspace();
  const openCase = async (id?: string) => {
    if (id) await ws.load(id); else if (!ws.currentRef.current) await ws.loadLatest();
  };
  const initialize = async () => {
    const session = await ws.bootstrap();
    if (session.role !== "evaluator") await openCase(encounterFromHash());
  };

  useEffect(() => { ws.work(initialize, true); }, []);
  useEffect(() => {
    if (!ws.session || ws.session.role === "evaluator") return;
    const routeChanged = () => {
      const id = encounterFromHash();
      if (id !== ws.currentRef.current?.encounter_id) ws.work(() => openCase(id));
    };
    window.addEventListener("hashchange", routeChanged);
    return () => window.removeEventListener("hashchange", routeChanged);
  }, [ws.session]);

  const changeCase = (id: string) => {
    if (ws.unsaved && ws.current?.encounter_id !== id && !window.confirm("มีข้อความหรือข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนเคสหรือไม่?")) return;
    location.hash = `#/voice/${encodeURIComponent(id)}`;
  };

  return <Shell product="nurse" identity={{ name: "Pratu Intake", tagline: "สำหรับพยาบาลและเจ้าหน้าที่รับข้อมูล" }}
    nav={[{ id: "voice", label: "รับข้อมูลด้วยเสียง", description: "สำหรับบุคลากรระหว่างซักประวัติ", icon: "mic" }]} page="voice" onNavigate={() => undefined}
    switchLink={{ href: "/platform#/cases", label: "เปิด Pratu Console", icon: "cases" }}
    title="รับข้อมูลด้วยเสียงสำหรับบุคลากร" description="พยาบาลหรือเจ้าหน้าที่ตรวจ transcript ก่อนส่งให้ผู้ช่วยทุกครั้ง"
    ws={ws} onSignedIn={initialize}>
    {ws.session?.role === "evaluator"
      ? <section className="panel"><h2>บัญชีผู้ประเมินใช้งานที่ Pratu Console</h2><p>หน้านี้สำหรับบุคลากรที่รับข้อมูลผู้ป่วยเท่านั้น</p><a className="button button--primary" href="/platform#/experiments">เปิด Pratu Console</a></section>
      : ws.session ? <VoicePage cases={ws.cases} current={ws.current} facts={ws.facts} runs={ws.runs} session={ws.session} caps={ws.caps} voiceState={ws.voiceState} busy={ws.busy} job={ws.job}
          message={ws.message} setMessage={ws.setMessage} record={ws.record} speak={ws.speak} stopAudio={ws.stopAudio} startRun={ws.startRun}
          changeCase={changeCase} newCaseOpen={false} setNewCaseOpen={() => location.assign("/platform#/cases")}
          onNavigateToCockpit={() => location.assign(platformCase(ws.current?.encounter_id))} /> : null}
  </Shell>;
}

mount(NurseApp);
