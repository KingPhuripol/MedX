import type { Metadata } from "next";
import Link from "next/link";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Nurse home" };

export default function NurseHomePage() {
  return (
    <RoleHome role="nurse">
      <p>
        <Link href="/nurse/triage">Open triage cases</Link>
      </p>
    </RoleHome>
  );
}
