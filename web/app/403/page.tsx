import type { Metadata } from "next";

import Forbidden from "@/components/Forbidden";

export const metadata: Metadata = { title: "403 — Clinical Front Door (research prototype)" };

export default function ForbiddenPage() {
  return <Forbidden />;
}
