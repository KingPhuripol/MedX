import type { Metadata } from "next";

import RoleGuard from "@/components/RoleGuard";
import TriageCaseList from "@/components/TriageCaseList";

export const metadata: Metadata = { title: "Triage cases" };

export default function NurseTriagePage() {
  return (
    <RoleGuard role="nurse">
      <TriageCaseList />
    </RoleGuard>
  );
}
