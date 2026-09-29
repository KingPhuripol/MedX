import type { Metadata } from "next";
import Link from "next/link";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Physician home" };

export default function PhysicianHomePage() {
  return (
    <RoleHome role="physician">
      <p>
        <Link href="/physician/care">Open care suggestion cases</Link>
      </p>
    </RoleHome>
  );
}
