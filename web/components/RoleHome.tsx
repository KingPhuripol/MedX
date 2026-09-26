"use client";

import { useRouter } from "next/navigation";

import PageFrame from "@/components/PageFrame";
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
      <PageFrame
        eyebrow={`${ROLE_LABELS[role]} workspace`}
        titleId="home-title"
        title={`${ROLE_LABELS[role]} home`}
        claim="This workspace is a placeholder for the research prototype."
        next={
          <>
            Sign out when you finish. <em>Nothing on this page affects care.</em>
          </>
        }
      >
        <p className="meta">Signed in as role: {role}.</p>
        <p>Placeholder: features arrive in later slices.</p>
        <button type="button" className="secondary" onClick={logout}>
          Sign out
        </button>
      </PageFrame>
    </RoleGuard>
  );
}
