import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { mockFetch, router } from "./router-mock";

import LoginForm from "@/components/LoginForm";

describe("LoginForm", () => {
  beforeEach(() => {
    router.push.mockReset();
  });

  it("has labelled inputs", () => {
    render(<LoginForm />);
    expect(screen.getByLabelText("ชื่อผู้ใช้สังเคราะห์")).toHaveAttribute("id", "username");
    expect(screen.getByLabelText("รหัสผ่าน")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "เข้าสู่ระบบเดโม" })).toBeInTheDocument();
  });

  it("shows an error message on 401 and does not navigate", async () => {
    const fetchFn = mockFetch(401, { detail: "invalid username or password" });
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("ชื่อผู้ใช้สังเคราะห์"), "nurse1");
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "เข้าสู่ระบบเดโม" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง");
    expect(fetchFn).toHaveBeenCalledWith("/api/auth/login", expect.objectContaining({ method: "POST" }));
    expect(router.push).not.toHaveBeenCalled();
  });

  it("redirects to the shared work queue on success (keyboard only)", async () => {
    mockFetch(200, { user: { role: "physician", home: "/physician" } });
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("ชื่อผู้ใช้สังเคราะห์"), "physician1");
    await userEvent.type(screen.getByLabelText("รหัสผ่าน"), "pw{Enter}");
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/app/queue"));
  });
});
