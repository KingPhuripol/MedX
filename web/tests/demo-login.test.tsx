import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockFetch, router } from "./router-mock";

import DemoLogin from "@/components/DemoLogin";

async function loginPage(demo: string | undefined) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_PUBLIC_DEMO", demo as string);
  return (await import("@/app/login/page")).default;
}

describe("public demo role picker (slice d1)", () => {
  beforeEach(() => {
    router.push.mockReset();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("login page shows the role picker, not the password form, when NEXT_PUBLIC_PUBLIC_DEMO=1", async () => {
    const Page = await loginPage("1");
    render(<Page />);
    for (const name of [/Nurse · พยาบาล/, /Physician · แพทย์/, /Pharmacist · เภสัชกร/]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.getByRole("group")).toHaveTextContent("synthetic data only");
  });

  it("login page keeps the password form by default", async () => {
    const Page = await loginPage(undefined);
    render(<Page />);
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nurse/ })).not.toBeInTheDocument();
  });

  it("posts the chosen role and goes to that role's home (keyboard only)", async () => {
    const fetchFn = mockFetch(200, { user: { role: "pharmacist", home: "/pharmacist" } });
    render(<DemoLogin />);
    await userEvent.tab();
    await userEvent.tab();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: /Pharmacist/ })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/pharmacist"));
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/auth/demo-login",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ role: "pharmacist" }) }),
    );
  });

  it("shows an alert and stays on the page when the demo login fails", async () => {
    mockFetch(503, { detail: "demo user not seeded" });
    render(<DemoLogin />);
    await userEvent.click(screen.getByRole("button", { name: /Nurse/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in failed");
    expect(router.push).not.toHaveBeenCalled();
  });
});
