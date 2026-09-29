import type { ReactNode } from "react";

import AppShell from "@/components/clinical/AppShell";

// Physician work pages keep their own RoleGuard and domain APIs; the shell only adds MedX navigation.
export default function PhysicianLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <div className="page-stack">
        <div className="card domain-adapter">{children}</div>
      </div>
    </AppShell>
  );
}
