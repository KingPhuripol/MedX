"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

import Forbidden from "@/components/Forbidden";
import { LoadingState } from "@/components/ui/LoadingState";
import { Notice } from "@/components/ui/Notice";
import type { Role } from "@/lib/copy";

type GuardState = "loading" | "allowed" | "forbidden" | "error";

/** Server-enforced guard: asks the API for this role's home; 401 -> /login, 403 -> 403 view. */
export default function RoleGuard({ role, children }: { role: Role; children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<GuardState>("loading");

  useEffect(() => {
    let active = true;
    fetch(`/api/home/${role}`, { credentials: "same-origin" })
      .then((resp) => {
        if (!active) return;
        if (resp.status === 401) {
          router.replace("/login");
        } else if (resp.status === 403) {
          setState("forbidden");
        } else {
          setState(resp.ok ? "allowed" : "error");
        }
      })
      .catch(() => active && setState("error"));
    return () => {
      active = false;
    };
  }, [role, router]);

  if (state === "forbidden") return <Forbidden />;
  if (state === "allowed") return <>{children}</>;
  if (state === "error")
    return (
      <Notice tone="critical" role="alert" title="ไม่สามารถตรวจสอบสิทธิ์ได้">
        <p>บริการไม่พร้อมใช้งาน โปรดลองอีกครั้ง · The service is unavailable. Please try again.</p>
      </Notice>
    );
  return <LoadingState label="กำลังตรวจสอบสิทธิ์…" />;
}
