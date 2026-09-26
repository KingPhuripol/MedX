import type { Metadata } from "next";

import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = { title: "Sign in — Clinical Front Door (research prototype)" };

export default function LoginPage() {
  return (
    <section aria-labelledby="login-title">
      <h1 id="login-title">Sign in</h1>
      <LoginForm />
    </section>
  );
}
