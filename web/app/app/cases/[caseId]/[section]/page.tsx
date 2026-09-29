import CaseWorkspace from "@/components/clinical/CaseWorkspace";
export default async function CaseSectionPage({params}:{params:Promise<{caseId:string;section:string}>}){const {caseId,section}=await params;return <CaseWorkspace caseId={caseId} section={section}/>}
