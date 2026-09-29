import Link from "next/link";
import { ShieldOff } from "lucide-react";

import { EmptyState } from "@/components/ui/EmptyState";

export default function Forbidden() {
  return (
    <div className="ui-standalone" data-testid="forbidden">
      <EmptyState
        headingLevel={1}
        icon={<ShieldOff size={28} />}
        title="403 — ไม่มีสิทธิ์เข้าถึงหน้านี้ (Not your role's page)"
        description={
          <>
            <p>หน้านี้เป็นของบทบาทอื่น คุณเปิดได้เฉพาะหน้าที่ตรงกับบทบาทของตนเอง</p>
            <p>Each role can open only its own pages.</p>
          </>
        }
        action={
          <>
            <Link className="ui-button ui-button--primary" href="/app/queue">
              กลับไปคิวงาน
            </Link>
            <Link className="ui-button ui-button--secondary" href="/login">
              เข้าสู่ระบบด้วยบัญชีอื่น
            </Link>
          </>
        }
      />
    </div>
  );
}
