import type { Metadata } from "next";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Physician home" };

export default function PhysicianHomePage() {
  return <RoleHome role="physician" />;
}
