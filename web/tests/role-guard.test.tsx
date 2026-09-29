import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { mockFetch, router } from "./router-mock";

import RoleHome from "@/components/RoleHome";

describe("RoleGuard via RoleHome", () => {
  beforeEach(() => {
    router.replace.mockReset();
  });

  it("renders the role placeholder when the API allows it", async () => {
    const fetchFn = mockFetch(200, { role: "nurse", message: "features arrive in later slices" });
    render(<RoleHome role="nurse" />);
    expect(await screen.findByRole("heading", { name: "Nurse home" })).toBeInTheDocument();
    expect(screen.getByText(/features arrive in later slices/)).toBeInTheDocument();
    expect(fetchFn).toHaveBeenCalledWith("/api/home/nurse", expect.anything());
  });

  it("shows the 403 view for another role's home", async () => {
    mockFetch(403, { detail: "this home belongs to another role" });
    render(<RoleHome role="pharmacist" />);
    expect(await screen.findByTestId("forbidden")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("403");
    expect(screen.queryByRole("heading", { name: "Pharmacist home" })).not.toBeInTheDocument();
  });

  it("redirects to /login without a session", async () => {
    mockFetch(401, { detail: "authentication required" });
    render(<RoleHome role="physician" />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("heading", { name: "Physician home" })).not.toBeInTheDocument();
  });
});
