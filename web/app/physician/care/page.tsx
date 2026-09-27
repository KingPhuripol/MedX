import type { Metadata } from "next";

import CareCaseList from "@/components/CareCaseList";
import RoleGuard from "@/components/RoleGuard";

export const metadata: Metadata = { title: "Care suggestion cases" };

export default function PhysicianCarePage() {
  return (
    <RoleGuard role="physician">
      <CareCaseList />
    </RoleGuard>
  );
}
