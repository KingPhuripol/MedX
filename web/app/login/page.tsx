import type { Metadata } from "next";

import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = { title: "เข้าสู่ระบบ" };

export default function LoginPage() {
  return (
    <div className="cover">
      <div className="cover-panel" data-testid="cover-panel">
        <p className="cover-title">Med<span className="cover-x">X</span> Clinical Operations</p>
        <div><p className="cover-sub">พื้นที่ทำงานเดียวสำหรับรับข้อมูล คัดกรอง ตรวจทาน และส่งต่อเคสสังเคราะห์</p><p>ออกแบบให้ red flags มาก่อนข้อเสนอ และทุกการตัดสินใจต้องยืนยันโดยบุคลากร</p></div>
      </div>
      <section className="cover-form" aria-labelledby="login-title">
        <span className="badge">Synthetic accounts only</span>
        <h1 id="login-title">เข้าสู่ระบบเดโม</h1>
        <p className="muted">ใช้บัญชีตามบทบาท ระบบจะนำไปยังคิวงานที่เกี่ยวข้อง</p>
        <LoginForm />
      </section>
    </div>
  );
}
