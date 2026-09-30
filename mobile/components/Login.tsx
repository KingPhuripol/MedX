"use client";

import { useState } from "react";

import { post } from "@/lib/api";
import { COPY } from "@/lib/copy";

import { Icon } from "./Icon";
import { Limit } from "./Limit";
import { Wordmark } from "./Wordmark";

export interface User {
  id?: number;
  username: string;
  role: string;
}

const PUBLIC_DEMO = process.env.NEXT_PUBLIC_PUBLIC_DEMO === "1";

/** Login (SPEC §2.1). Only the nurse role may enter; the caller checks the role. */
export function Login({
  onUser,
  initialError = null,
  publicDemo = PUBLIC_DEMO,
}: {
  onUser: (u: User) => void;
  initialError?: string | null;
  publicDemo?: boolean;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const r = publicDemo
      ? await post<{ user: User }>("/api/auth/demo-login", { role: "nurse" })
      : await post<{ user: User }>("/api/auth/login", { username, password });
    setBusy(false);
    if (r.data?.user) return onUser(r.data.user);
    setError(r.status === 401 ? COPY.login.unauthorized : r.status === 0 ? COPY.login.network : COPY.login.failed);
  }

  return (
    <main className="screen screen--fixed">
      <div className="appbar">
        <Wordmark size={28} />
      </div>
      <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8 }}>
        <h1 className="t-display">{COPY.login.heading}</h1>
        <p className="t-body muted">{COPY.login.purpose}</p>
      </div>

      <form
        style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 16 }}
        aria-label="เข้าสู่ระบบ"
        onSubmit={submit}
        noValidate
      >
        {!publicDemo && (
          <>
            <div className="field">
              <label htmlFor="u">{COPY.login.username}</label>
              <div className="input">
                <input
                  id="u"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  aria-describedby={error ? "login-err" : undefined}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="p">{COPY.login.password}</label>
              <div className="input">
                <input
                  id="p"
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  aria-describedby={error ? "login-err" : undefined}
                />
                <button
                  type="button"
                  className="adorn"
                  aria-label={show ? COPY.login.hidePassword : COPY.login.showPassword}
                  aria-pressed={show}
                  onClick={() => setShow((s) => !s)}
                >
                  <Icon name={show ? "eye-off" : "eye"} />
                </button>
              </div>
            </div>
          </>
        )}
        {error && (
          <div className="notice notice--warn" role="alert" id="login-err">
            <Icon name="triangle-alert" />
            <span>{error}</span>
          </div>
        )}
        <button type="submit" className="btn btn--primary btn--block" style={{ marginTop: 8 }} disabled={busy}>
          {busy ? COPY.login.loading : COPY.login.cta}
        </button>
      </form>

      <Limit style={{ marginTop: 16 }} />
    </main>
  );
}
