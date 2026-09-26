import type { Metadata } from "next";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Pharmacist home" };

export default function PharmacistHomePage() {
  return <RoleHome role="pharmacist" />;
}
