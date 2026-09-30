/** V2C-C17: nurse-only access, the three login copies, demo one-click, 401 anywhere → login with state cleared. */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Login } from "@/components/Login";
import { ScribeApp } from "@/components/ScribeApp";
import { COPY } from "@/lib/copy";

import physician from "./fixtures/auth-me-physician.json";
import { installApi, installBrowser } from "./helpers";

function login(status: number | "network") {
  const api = installApi({ on: { "/api/auth/login": () => (status === "network" ? "network" : { status, body: status === 200 ? { user: { username: "nurse1", role: "nurse" } } : { detail: "x" } }) } });
  const onUser = vi.fn();
  render(<Login onUser={onUser} publicDemo={false} />);
  fireEvent.change(screen.getByLabelText(COPY.login.username), { target: { value: "nurse1" } });
  fireEvent.change(screen.getByLabelText(COPY.login.password, { selector: "input" }), { target: { value: "nurse1-dev" } });
  fireEvent.click(screen.getByRole("button", { name: COPY.login.cta }));
  return { api, onUser };
}

describe("login", () => {
  it("password login ok posts username/password and hands the user up", async () => {
    const { api, onUser } = login(200);
    await waitFor(() => expect(onUser).toHaveBeenCalledWith({ username: "nurse1", role: "nurse" }));
    expect(api.calls[0]).toMatchObject({ url: "/api/auth/login", method: "POST", body: { username: "nurse1", password: "nurse1-dev" } });
  });

  it.each([
    [401, COPY.login.unauthorized],
    [500, COPY.login.failed],
    ["network", COPY.login.network],
  ] as const)("%s → %s", async (status, copy) => {
    const { onUser } = login(status);
    expect(await screen.findByRole("alert")).toHaveTextContent(copy);
    expect(onUser).not.toHaveBeenCalled();
    expect(screen.getByLabelText(COPY.login.username)).toHaveAttribute("aria-describedby", "login-err");
  });

  it("public demo: one-click CTA posts demo-login {role:nurse} and hides the fields", async () => {
    const api = installApi();
    const onUser = vi.fn();
    render(<Login onUser={onUser} publicDemo />);
    expect(screen.queryByLabelText(COPY.login.username)).toBeNull();
    expect(screen.queryByLabelText(COPY.login.password)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: COPY.login.cta }));
    await waitFor(() => expect(onUser).toHaveBeenCalled());
    expect(api.calls[0]).toMatchObject({ url: "/api/auth/demo-login", body: { role: "nurse" } });
  });

  it("the password visibility toggle is a labelled button", () => {
    installApi();
    render(<Login onUser={vi.fn()} publicDemo={false} />);
    const t = screen.getByRole("button", { name: COPY.login.showPassword });
    fireEvent.click(t);
    expect(screen.getByRole("button", { name: COPY.login.hidePassword })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("role and session (ScribeApp)", () => {
  it("non-nurse /api/me → Wrong role copy + logout, no session start", async () => {
    const api = installApi({ on: { "/api/me": () => ({ status: 200, body: physician }) } });
    render(<ScribeApp />);
    expect(await screen.findByRole("alert")).toHaveTextContent(COPY.login.wrongRole);
    expect(api.calls.some((c) => c.url === "/api/auth/logout")).toBe(true);
    expect(api.calls.some((c) => c.url === "/api/voice/sessions")).toBe(false);
  });

  it("non-nurse login → Wrong role", async () => {
    installApi({
      on: { "/api/me": () => ({ status: 401, body: {} }), "/api/auth/login": () => ({ status: 200, body: physician }) },
    });
    render(<ScribeApp />);
    fireEvent.change(await screen.findByLabelText(COPY.login.username), { target: { value: "physician1" } });
    fireEvent.click(screen.getByRole("button", { name: COPY.login.cta }));
    expect(await screen.findByText(COPY.login.wrongRole)).toBeInTheDocument();
  });

  it("401 mid-session (turn POST) → login screen with in-memory state cleared", async () => {
    const b = installBrowser();
    const api = installApi();
    render(<ScribeApp />);
    fireEvent.click(await screen.findByRole("radio", { name: /SYN-2026-0023/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: COPY.start.consent }));
    fireEvent.click(screen.getByRole("button", { name: COPY.start.cta }));
    fireEvent.click(await screen.findByTestId("rec-button"));
    await waitFor(() => expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "listening"));
    api.turnStatus.push(401);
    act(() => b.rtc.say("i1", "ปวดท้องค่ะ"));
    expect(await screen.findByRole("heading", { name: COPY.login.heading })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("ปวดท้องค่ะ");
    expect(b.rtc.open).toBe(0);
    expect(b.track.readyState).toBe("ended");
    // Signing back in starts clean: no patient picked, consent unticked.
    api.on["/api/auth/login"] = () => ({ status: 200, body: { user: { username: "nurse1", role: "nurse" } } });
    fireEvent.change(screen.getByLabelText(COPY.login.username), { target: { value: "nurse1" } });
    fireEvent.click(screen.getByRole("button", { name: COPY.login.cta }));
    expect(await screen.findByRole("checkbox", { name: COPY.start.consent })).not.toBeChecked();
  });

  it("401 on the config call → login", async () => {
    installApi({ on: { "/api/voice/realtime/config": () => ({ status: 401, body: {} }) } });
    render(<ScribeApp />);
    expect(await screen.findByRole("heading", { name: COPY.login.heading })).toBeInTheDocument();
  });
});
