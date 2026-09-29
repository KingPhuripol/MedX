import { redirect } from "next/navigation";
export default async function LegacyTriageReview({params}:{params:Promise<{assessmentId:string}>}){const {assessmentId}=await params;redirect(`/app/cases/SYN-2026-0017/triage?assessment=${encodeURIComponent(assessmentId)}`)}
