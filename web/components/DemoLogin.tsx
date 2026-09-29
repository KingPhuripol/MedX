"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
      setError("Sign-in failed. Please try again.");
    } catch {
      setError("Sign-in service unavailable. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="group" aria-labelledby="demo-roles-label" aria-describedby={error ? "login-error" : undefined}>
      <p id="demo-roles-label">
        Public demo, synthetic data only. Choose a role (no password). เลือกบทบาทเพื่อทดลองใช้งาน (ข้อมูลสังเคราะห์)
      </p>
      {ROLES.map((role) => (
        <p key={role}>
          <button type="button" disabled={busy} onClick={() => signIn(role)}>
            {ROLE_LABELS[role]} · {ROLE_LABELS_TH[role]}
          </button>
        </p>
      ))}
      {error && (
        <p id="login-error" role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
