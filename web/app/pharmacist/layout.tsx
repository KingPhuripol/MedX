import type { ReactNode } from "react";

import AppShell from "@/components/clinical/AppShell";

// Pharmacist work pages keep their own RoleGuard and domain APIs; the shell only adds MedX navigation.
export default function PharmacistLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <div className="page-stack">
        <div className="card domain-panel">{children}</div>
      </div>
    </AppShell>
  );
}
