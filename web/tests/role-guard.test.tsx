import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { mockFetch, router } from "./router-mock";

import RoleGuard from "@/components/RoleGuard";

describe("RoleGuard", () => {
  beforeEach(() => {
    router.replace.mockReset();
  });

  it("renders the page when the API allows the role", async () => {
    const fetchFn = mockFetch(200, { role: "nurse" });
    render(
      <RoleGuard role="nurse">
        <h1>Triage cases</h1>
      </RoleGuard>,
    );
    expect(await screen.findByRole("heading", { name: "Triage cases" })).toBeInTheDocument();
    expect(fetchFn).toHaveBeenCalledWith("/api/home/nurse", expect.anything());
  });

  it("shows the 403 view for another role's page", async () => {
    mockFetch(403, { detail: "this home belongs to another role" });
    render(
      <RoleGuard role="pharmacist">
        <h1>Medication reconciliation</h1>
      </RoleGuard>,
    );
    expect(await screen.findByTestId("forbidden")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("403");
    expect(screen.queryByRole("heading", { name: "Medication reconciliation" })).not.toBeInTheDocument();
  });

  it("redirects to /login without a session", async () => {
    mockFetch(401, { detail: "authentication required" });
    render(
      <RoleGuard role="physician">
        <h1>Care suggestion cases</h1>
      </RoleGuard>,
    );
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("heading", { name: "Care suggestion cases" })).not.toBeInTheDocument();
  });
});
