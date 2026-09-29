"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

export default function LoginForm() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username, password }),
      });
      if (resp.ok) {
        await resp.json();
        router.push("/app/queue");
        return;
      }
      setError(resp.status === 401 ? "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" : "เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้ง");
    } catch {
      setError("บริการเข้าสู่ระบบไม่พร้อมใช้งาน โปรดลองอีกครั้ง");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="ui-form" onSubmit={onSubmit} aria-describedby={error ? "login-error" : undefined} noValidate>
      <Field label="ชื่อผู้ใช้สังเคราะห์" htmlFor="username">
        <input
          id="username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </Field>
      <Field label="รหัสผ่าน" htmlFor="password">
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
      {error && (
        <Notice tone="critical" role="alert" id="login-error">
          {error}
        </Notice>
      )}
      <Button type="submit" className="ui-block" disabled={busy}>
        {busy ? "กำลังเข้าสู่ระบบ…" : "เข้าสู่ระบบเดโม"}
      </Button>
    </form>
  );
}
