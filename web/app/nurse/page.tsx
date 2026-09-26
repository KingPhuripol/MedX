import type { Metadata } from "next";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Nurse home" };

export default function NurseHomePage() {
  return <RoleHome role="nurse" />;
}
