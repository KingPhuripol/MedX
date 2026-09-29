"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/Notice";
import { ROLES, ROLE_LABELS, type Role } from "@/lib/copy";

const ROLE_LABELS_TH: Record<Role, string> = { nurse: "พยาบาล", physician: "แพทย์", pharmacist: "เภสัชกร" };

/** Slice d1: one-click sign-in as the synthetic user of a role (public demo builds only; see lib/publicDemo). */
export default function DemoLogin() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(role: Role) {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/auth/demo-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ role }),
      });
      if (resp.ok) {
        const data = await resp.json();
        router.push(data.user.home);
        return;
      }
      setError("เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้ง · Sign-in failed. Please try again.");
    } catch {
      setError("บริการเข้าสู่ระบบไม่พร้อมใช้งาน โปรดลองอีกครั้ง · Sign-in service unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="ui-form"
      role="group"
      aria-labelledby="demo-roles-label"
      aria-describedby={error ? "login-error" : undefined}
    >
      <p id="demo-roles-label" className="muted">
        เลือกบทบาทเพื่อทดลองใช้งาน (ข้อมูลสังเคราะห์ ไม่ต้องใช้รหัสผ่าน) · Public demo, synthetic data only. Choose a
        role (no password).
      </p>
      {ROLES.map((role) => (
        <Button key={role} type="button" variant="secondary" className="ui-block" disabled={busy} onClick={() => signIn(role)}>
          {ROLE_LABELS[role]} · {ROLE_LABELS_TH[role]}
        </Button>
      ))}
      {error && (
        <Notice tone="critical" role="alert" id="login-error">
          {error}
        </Notice>
      )}
    </div>
  );
}
