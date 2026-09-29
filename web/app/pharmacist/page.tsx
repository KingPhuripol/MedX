import type { Metadata } from "next";
import Link from "next/link";

import RoleHome from "@/components/RoleHome";

export const metadata: Metadata = { title: "Pharmacist home" };

export default function PharmacistHomePage() {
  return (
    <RoleHome role="pharmacist">
      <nav aria-label="Pharmacist tools">
        <ul>
          <li>
            <Link href="/pharmacist/reconcile">Medication reconciliation</Link>
          </li>
        </ul>
      </nav>
    </RoleHome>
  );
}
