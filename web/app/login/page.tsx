import type { Metadata } from "next";

import DemoLogin, { PUBLIC_DEMO } from "@/components/DemoLogin";
import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="cover">
      <div className="cover-panel" data-testid="cover-panel" aria-hidden="true">
        <svg className="cover-motif" data-testid="cover-motif" viewBox="0 0 100 100" focusable="false">
          <path d="M18 18 L82 82 M82 18 L18 82" fill="none" strokeWidth="16" strokeLinecap="round" />
        </svg>
        <p className="cover-title">AI Clinical Front Door</p>
        <p className="cover-sub">Research prototype. Suggestions for clinician review.</p>
      </div>
      <section className="cover-form" aria-labelledby="login-title">
        <h1 id="login-title">Sign in</h1>
        {PUBLIC_DEMO ? <DemoLogin /> : <LoginForm />}
      </section>
    </div>
  );
}
