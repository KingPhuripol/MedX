import type { Metadata } from "next";

import CareReviewLoader from "@/components/CareReviewLoader";
import RoleGuard from "@/components/RoleGuard";

export const metadata: Metadata = { title: "Care suggestion review" };

export default async function CareReviewPage({ params }: { params: Promise<{ assessmentId: string }> }) {
  const { assessmentId } = await params;
  return (
    <RoleGuard role="physician">
      <CareReviewLoader assessmentId={assessmentId} />
    </RoleGuard>
  );
}
