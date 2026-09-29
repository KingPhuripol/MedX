import type { Metadata } from "next";
import Link from "next/link";
import { FileQuestion } from "lucide-react";

import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "404" };

export default function NotFound() {
  return (
    <div className="ui-standalone">
      <EmptyState
        headingLevel={1}
        icon={<FileQuestion size={28} />}
        title="404 — ไม่พบหน้านี้ (Page not found)"
        description={
          <>
            <p>ไม่พบหน้าที่ต้องการ อาจมีการพิมพ์ที่อยู่ผิดหรือหน้านี้ถูกย้าย</p>
            <p>The page you asked for does not exist.</p>
          </>
        }
        action={
          <>
            <Link className="ui-button ui-button--primary" href="/app/queue">
              กลับไปคิวงาน
            </Link>
            <Link className="ui-button ui-button--secondary" href="/login">
              ไปหน้าเข้าสู่ระบบ
            </Link>
          </>
        }
      />
    </div>
  );
}
