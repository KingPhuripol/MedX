import { Suspense } from "react";

import LiveCall from "@/components/live/LiveCall";
import RoleGuard from "@/components/RoleGuard";
import { LoadingState } from "@/components/ui/LoadingState";

export default function LivePage() {
  return (
    <RoleGuard role="nurse">
      <Suspense fallback={<LoadingState label="กำลังเปิด MedX Live…" />}>
        <LiveCall />
      </Suspense>
    </RoleGuard>
  );
}
