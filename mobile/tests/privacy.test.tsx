/** V2C-C16: a full scripted session writes nothing to browser storage and keeps turn timestamps valid. */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScribeApp } from "@/components/ScribeApp";
import { COPY } from "@/lib/copy";

import { fact, turnResponse } from "./fixtures/scenario";
import { installApi, installBrowser } from "./helpers";

describe("privacy over a full session", () => {
  it("0 writes to localStorage, sessionStorage, indexedDB, caches or cookies; SDP carries no patient data", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const idb = vi.fn();
    const cachesOpen = vi.fn();
    vi.stubGlobal("indexedDB", { open: idb });
    vi.stubGlobal("caches", { open: cachesOpen, put: cachesOpen });
    const cookie = vi.spyOn(document, "cookie", "set");
    const b = installBrowser();
    const api = installApi(); // the review endpoint is unmocked: 404 → not-yet-connected
    api.turns.push(
      turnResponse({ turnId: "vt_1", text: "ปวดท้องค่ะ", facts: [fact("chief_complaint", "a", "ปวดท้อง", "vt_1")], known: { chief_complaint: "KNOWN" } }),
    );

    render(<ScribeApp />);
    fireEvent.click(await screen.findByRole("radio", { name: /SYN-2026-0023/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: COPY.start.consent }));
    fireEvent.click(screen.getByRole("button", { name: COPY.start.cta }));
    fireEvent.click(await screen.findByTestId("rec-button"));
    await waitFor(() => expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "listening"));
    act(() => b.rtc.say("i1", "ปวดท้องค่ะ"));
    act(() => b.rtc.say("i2", "เป็นมาสองวันค่ะ"));
    await waitFor(() => expect(api.posted).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.finish }));
    expect(await screen.findByRole("heading", { name: COPY.review.title })).toBeInTheDocument();
    for (const li of document.querySelectorAll<HTMLElement>(".review-list > li")) {
      const btn = within(li).queryByRole("button", { name: COPY.review.confirm }) ?? within(li).getByRole("button", { name: COPY.review.markUnknown });
      fireEvent.click(btn);
    }
    fireEvent.click(screen.getByRole("button", { name: new RegExp(COPY.review.submit) }));
    await screen.findByText("ยังส่งเข้าเคสไม่ได้");

    expect(setItem).not.toHaveBeenCalled();
    expect(idb).not.toHaveBeenCalled();
    expect(cachesOpen).not.toHaveBeenCalled();
    expect(cookie).not.toHaveBeenCalled();

    const sdp = api.calls.filter((c) => c.url.startsWith("https://"));
    expect(sdp).toHaveLength(1);
    expect(Object.keys(sdp[0].init.headers as object).sort()).toEqual(["Authorization", "Content-Type"]);
    expect(sdp[0].init.credentials).toBeUndefined();
    expect(String(sdp[0].init.body)).not.toMatch(/SYN-|ปวดท้อง/);
    expect(sdp[0].url).not.toContain("SYN-");

    const now = Date.now();
    let prev = 0;
    for (const t of api.posted as { started_at: string; ended_at: string }[]) {
      expect(t.started_at).toMatch(/[+-]\d{2}:\d{2}$/);
      expect(t.ended_at).toMatch(/[+-]\d{2}:\d{2}$/);
      const s = Date.parse(t.started_at);
      const e = Date.parse(t.ended_at);
      expect(s).toBeLessThanOrEqual(e);
      expect(e).toBeLessThanOrEqual(now);
      expect(s).toBeGreaterThanOrEqual(prev);
      prev = s;
    }
    // Only same-origin /api and the minted https connect_url were contacted.
    expect(api.calls.every((c) => c.url.startsWith("/api/") || c.url === "https://127.0.0.1/v1/realtime/calls")).toBe(true);
  });
});
