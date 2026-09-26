"use client";

import { useRouter } from "next/navigation";

import RoleGuard from "@/components/RoleGuard";
import { ROLE_LABELS, type Role } from "@/lib/copy";

export default function RoleHome({ role }: { role: Role }) {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
    router.push("/login");
  }

  return (
    <RoleGuard role={role}>
      <section aria-labelledby="home-title">
        <h1 id="home-title">{ROLE_LABELS[role]} home</h1>
        <p>Signed in as role: {role}. Placeholder: features arrive in later slices.</p>
        <button type="button" onClick={logout}>
          Sign out
        </button>
      </section>
    </RoleGuard>
  );
}
