import type { Metadata } from "next";

import PharmaReconcile from "@/components/PharmaReconcile";

import "./pharma.css";

export const metadata: Metadata = { title: "Medication reconciliation" };

export default function PharmacistReconcilePage() {
  return <PharmaReconcile />;
}
