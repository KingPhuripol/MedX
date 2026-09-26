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
    expect(screen.getByLabelText("Username")).toHaveAttribute("id", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows an error message on 401 and does not navigate", async () => {
    const fetchFn = mockFetch(401, { detail: "invalid username or password" });
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Username"), "nurse1");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
    expect(fetchFn).toHaveBeenCalledWith("/api/auth/login", expect.objectContaining({ method: "POST" }));
    expect(router.push).not.toHaveBeenCalled();
  });

  it("redirects to the user's own role home on success (keyboard only)", async () => {
    mockFetch(200, { user: { role: "physician", home: "/physician" } });
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Username"), "physician1");
    await userEvent.type(screen.getByLabelText("Password"), "pw{Enter}");
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/physician"));
  });
});
