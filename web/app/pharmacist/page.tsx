import type { Metadata } from "next";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Pharmacist home — Clinical Front Door (research prototype)" };

export default function PharmacistHomePage() {
  return <RoleHome role="pharmacist" />;
}
