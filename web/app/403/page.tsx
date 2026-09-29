import type { Metadata } from "next";

import Forbidden from "@/components/Forbidden";

export const metadata: Metadata = { title: "403" };

export default function ForbiddenPage() {
  return <Forbidden />;
}
