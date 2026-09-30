/** V2C-C4 consent gate + start screen states (§2.2, T12). */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScribeApp } from "@/components/ScribeApp";
import { Start } from "@/components/Start";
import { COPY, PROPOSED_V2C } from "@/lib/copy";
import type { Patient } from "@/lib/roster";

import config from "./fixtures/realtime-config.json";
import { installApi, installBrowser } from "./helpers";

const S = COPY.start;
const cta = () => screen.getByRole("button", { name: S.cta });

function renderStart(p: Partial<Parameters<typeof Start>[0]> = {}) {
  const onOpen = vi.fn();
  render(<Start username="nurse1" accessCodeRequired={false} onSignOut={vi.fn()} onOpen={onOpen} {...p} />);
  return { onOpen };
}

describe("consent × patient matrix (C4)", () => {
  it.each([
    [false, false],
    [true, false],
    [false, true],
    [true, true],
  ])("patient=%s consent=%s", async (pick, tick) => {
    const b = installBrowser();
    const api = installApi();
    render(<ScribeApp />);
    const radio = await screen.findByRole("radio", { name: /SYN-2026-0023/ });
    const consent = screen.getByRole("checkbox", { name: S.consent });
    expect(consent.tagName).toBe("INPUT");
    expect(consent).toHaveAttribute("type", "checkbox");
    if (pick) fireEvent.click(radio);
    if (tick) fireEvent.click(consent);
    const ready = pick && tick;
    if (ready) expect(cta()).toBeEnabled();
    else {
      expect(cta()).toBeDisabled();
      expect(cta()).toHaveAccessibleDescription(S.disabledHint);
    }
    fireEvent.click(cta());
    await act(() => new Promise((r) => setTimeout(r, 20)));
    const started = api.calls.filter((c) => c.url === "/api/voice/sessions");
    expect(started).toHaveLength(ready ? 1 : 0);
    if (ready) expect(started[0].body).toEqual({ patient_ref: "SYN-2026-0023", data_class: "synthetic", mode: "ambient" });
    expect(b.gum).not.toHaveBeenCalled(); // the mic is asked only on the record press
  });

  it("unticking consent re-disables the button", async () => {
    renderStart();
    fireEvent.click(await screen.findByRole("radio", { name: /SYN-2026-0017/ }));
    const consent = screen.getByRole("checkbox", { name: S.consent });
    fireEvent.click(consent);
    expect(cta()).toBeEnabled();
    fireEvent.click(consent);
    expect(cta()).toBeDisabled();
  });
});

describe("patient list states", () => {
  it("skeleton rows while loading, then the list as a radiogroup", async () => {
    let resolve!: (p: Patient[]) => void;
    renderStart({ roster: () => new Promise<Patient[]>((r) => (resolve = r)) });
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(3);
    expect(screen.getByRole("status")).toHaveTextContent(S.loading);
    resolve([{ id: "SYN-2026-0023" }]);
    expect(await screen.findByRole("radiogroup")).toBeInTheDocument();
  });

  it("empty roster → empty state with one next action", async () => {
    renderStart({ roster: async () => [] });
    expect(await screen.findByText(S.empty.head)).toBeInTheDocument();
    expect(screen.getByText(S.empty.body)).toBeInTheDocument();
  });

  it("load error → error copy and a reload action", async () => {
    let n = 0;
    renderStart({ roster: async () => (n++ === 0 ? Promise.reject(new Error("x")) : [{ id: "SYN-1" }]) });
    expect(await screen.findByText(S.loadError)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: S.reload }));
    expect(await screen.findByRole("radio", { name: /SYN-1/ })).toBeInTheDocument();
  });

  it("typing a valid unlisted SYN- id offers it as a choice", async () => {
    const { onOpen } = renderStart();
    await screen.findByRole("radiogroup");
    fireEvent.change(screen.getByLabelText(S.searchLabel), { target: { value: "SYN-TEST-9" } });
    fireEvent.click(screen.getByRole("radio", { name: /SYN-TEST-9/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: S.consent }));
    fireEvent.click(cta());
    expect(onOpen).toHaveBeenCalledWith({ id: "SYN-TEST-9" }, "");
  });

  it.each(["HN12345", "1234567890123", "สมชาย"])("non-synthetic id %s → Non-synthetic copy, nothing selectable", async (q) => {
    renderStart();
    await screen.findByRole("radiogroup");
    fireEvent.change(screen.getByLabelText(S.searchLabel), { target: { value: q } });
    expect(screen.getByText(S.nonSynthetic)).toBeInTheDocument();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("SYN- prefix with no match and an invalid id → no-match copy", async () => {
    renderStart();
    await screen.findByRole("radiogroup");
    fireEvent.change(screen.getByLabelText(S.searchLabel), { target: { value: "SYN-ZZ?" } });
    expect(screen.getByText(S.noMatch("SYN-ZZ?").head)).toBeInTheDocument();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });
});

describe("access code", () => {
  it("is hidden unless access_code_required", async () => {
    renderStart();
    await screen.findByRole("radiogroup");
    expect(screen.queryByLabelText(PROPOSED_V2C.accessCodeLabel)).toBeNull();
  });

  it("is required when configured, sent to onOpen, and never written to storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { onOpen } = renderStart({ accessCodeRequired: true });
    fireEvent.click(await screen.findByRole("radio", { name: /SYN-2026-0023/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: S.consent }));
    expect(cta()).toBeDisabled();
    fireEvent.change(screen.getByLabelText(PROPOSED_V2C.accessCodeLabel), { target: { value: "CODE-1" } });
    fireEvent.click(cta());
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: "SYN-2026-0023" }), "CODE-1");
    expect(setItem).not.toHaveBeenCalled();
    expect(document.cookie).not.toContain("CODE-1");
  });

  it("after access_code_invalid the field is focused with the error linked", async () => {
    renderStart({ accessCodeRequired: true, accessCodeError: true, initialPatient: { id: "SYN-2026-0023" }, initialConsent: true });
    const field = screen.getByLabelText(PROPOSED_V2C.accessCodeLabel);
    await waitFor(() => expect(document.activeElement).toBe(field));
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(`${PROPOSED_V2C.accessCodeInvalid.head} ${PROPOSED_V2C.accessCodeInvalid.body}`);
  });

  it("the mint carries the typed code (ScribeApp end to end)", async () => {
    installBrowser();
    const api = installApi({ on: { "/api/voice/realtime/config": () => ({ status: 200, body: { ...config, access_code_required: true } }) } });
    render(<ScribeApp />);
    fireEvent.click(await screen.findByRole("radio", { name: /SYN-2026-0023/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: S.consent }));
    fireEvent.change(await screen.findByLabelText(PROPOSED_V2C.accessCodeLabel), { target: { value: "CODE-1" } });
    fireEvent.click(cta());
    fireEvent.click(await screen.findByTestId("rec-button"));
    await waitFor(() => expect(api.calls.some((c) => c.url === "/api/voice/realtime/session")).toBe(true));
    const mint = api.calls.find((c) => c.url === "/api/voice/realtime/session")!;
    expect(mint.body).toMatchObject({ access_code: "CODE-1", purpose: "ambient" });
  });
});
