import type { Metadata } from "next";

import PharmaReconcile from "@/components/PharmaReconcile";

import "./pharma.css";

export const metadata: Metadata = { title: "Medication reconciliation — Clinical Front Door (research prototype)" };

export default function PharmacistReconcilePage() {
  return <PharmaReconcile />;
}
