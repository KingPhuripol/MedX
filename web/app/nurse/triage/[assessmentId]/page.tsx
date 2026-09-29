import type { Metadata } from "next";

import RoleGuard from "@/components/RoleGuard";
import TriageReviewLoader from "@/components/TriageReviewLoader";

export const metadata: Metadata = { title: "Triage review" };

export default async function TriageReviewPage({ params }: { params: Promise<{ assessmentId: string }> }) {
  const { assessmentId } = await params;
  return (
    <RoleGuard role="nurse">
      <TriageReviewLoader assessmentId={assessmentId} />
    </RoleGuard>
  );
}
