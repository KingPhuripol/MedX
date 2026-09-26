import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "./router-mock";

import PharmaReconcile from "@/components/PharmaReconcile";
import { NLM_ATTRIBUTION, PHRASING_LABEL } from "@/lib/pharma";

const src = (s: Record<string, unknown>) => ({
  evidence_ref: `demo/${s.source_type}/1`,
  available_at_time: "2026-06-10T09:00:00+07:00",
  raw_span: "synthetic text",
  presence: "present",
  dose_value: null,
  dose_unit: null,
  frequency_code: null,
  ...s,
});

function issue(n: number, type: string, rank: number, severity: string, status = "open") {
  return {
    issue_id: `run1-i0${n}`,
    run_id: "run1",
    type,
    severity,
    severity_rank: rank,
    rule_id: `${type}@1.0.0`,
    ingredients: [type.startsWith("allergy") ? "amoxicillin" : "simvastatin"],
    conflicting_sources: [src({ source_type: type.startsWith("allergy") ? "allergy_record" : "home_list" }), src({ source_type: "new_order", dose_value: 40, dose_unit: "mg" })],
    phrasing: { text: `Phrasing ${n}. For pharmacist review.`, source: "model", provider: "mock", model_version: "mock-0.1.0" },
    status,
  };
}

// A dose not stated in the new order: an issue of its own (s5r), listed with the other issues.
const MISSING_FIELD_ISSUE = {
  issue_id: "run1-i03",
  run_id: "run1",
  type: "missing_field",
  severity: "moderate",
  severity_rank: 3,
  rule_id: "missing_field@2.0.0",
  field: "dose",
  ingredients: ["warfarin"],
  conflicting_sources: [
    src({ source_type: "new_order", raw_span: "Warfarin 2 tab daily", frequency_code: "q24h" }),
    src({ source_type: "home_list", raw_span: "Warfarin 3 mg daily", dose_value: 3, dose_unit: "mg", frequency_code: "q24h" }),
  ],
  phrasing: {
    text: "The dose of warfarin is not stated in the new order, so it could not be compared with the home list. For pharmacist review.",
    source: "model",
    provider: "mock",
    model_version: "mock-0.1.0",
  },
  status: "open",
};

// Deliberately out of order: the page must still show allergy first.
const RUN = {
  run_id: "run1",
  patient_ref: "s5-demo-01",
  as_of: "2026-06-10T10:00:00+07:00",
  mode: "rules_plus_model",
  status: "complete",
  formulary_version: "s5-formulary-1.0.0",
  rules_version: "s5-rules-1.0.0",
  excluded_future_items: 0,
  issues: [issue(2, "dose_mismatch", 3, "moderate"), MISSING_FIELD_ISSUE, issue(1, "allergy_class", 1, "high")],
  notices: [{ notice_id: "run1-n01", type: "unrecognised_drug", detail: "not in the formulary", raw_span: "Qelvadrine" }],
  unchecked_comparisons: 1,
  extraction: [
    {
      source_index: 0,
      source_type: "home_list",
      evidence_ref: "demo/home_list/1",
      available_at_time: "2026-06-10T09:00:00+07:00",
      status: "ok",
      failure_reason: null,
      entries: [
        { source_text: "Warfarin 3 mg daily", drug_name_raw: "Warfarin", dose_value: 3, dose_unit: "mg", route: null,
          frequency_code: "q24h", ingredients: ["warfarin"], recognised: true, discontinue_intent: false },
      ],
    },
    {
      source_index: 1,
      source_type: "patient_reported",
      evidence_ref: "demo/patient_reported/1",
      available_at_time: "2026-06-10T09:00:00+07:00",
      status: "extraction_failed",
      failure_reason: "timeout",
      entries: null,
    },
    {
      source_index: 2,
      source_type: "new_order",
      evidence_ref: "demo/new_order/1",
      available_at_time: "2026-06-10T09:50:00+07:00",
      status: "ok",
      failure_reason: null,
      entries: [
        { source_text: "Warfarin 2 tab daily", drug_name_raw: "Warfarin", dose_value: null, dose_unit: null, route: null,
          frequency_code: "q24h", ingredients: ["warfarin"], recognised: true, discontinue_intent: false },
      ],
    },
  ],
};

let decided: Record<string, string> = {};

function installFetch() {
  decided = {};
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (url === "/api/home/pharmacist") return json({ role: "pharmacist" });
    if (url === "/api/pharma/fixtures")
      return json({ fixtures: [{ fixture_ref: "demo-01", patient_ref: "s5-demo-01", split: "demo", label: "Demo" }] });
    const withStatus = () => ({
      ...RUN,
      issues: RUN.issues.map((i) => ({ ...i, status: decided[i.issue_id] ?? "open" })),
    });
    if (url === "/api/pharma/reconcile" && init?.method === "POST") return json(withStatus());
    if (url.startsWith("/api/pharma/runs/")) return json(withStatus());
    const m = url.match(/^\/api\/pharma\/issues\/(.+)\/(confirm|dismiss)$/);
    if (m) {
      decided[decodeURIComponent(m[1])] = m[2] === "confirm" ? "confirmed" : "dismissed";
      return json({ status: "ok" });
    }
    return json({}, 404);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function runCheck() {
  render(<PharmaReconcile />);
  const button = await screen.findByRole("button", { name: "Run check" });
  await waitFor(() => expect(screen.getByLabelText("Synthetic patient")).toHaveValue("demo-01"));
  await userEvent.click(button);
  await screen.findByRole("heading", { level: 2, name: /Issues for pharmacist review/ });
}

describe("pharmacist reconciliation page", () => {
  beforeEach(() => {
    router.replace.mockReset();
    window.history.replaceState(null, "", "/pharmacist/reconcile");
  });

  it("has landmarks, headings, attribution and a live status region", async () => {
    installFetch();
    await runCheck();
    const h1 = screen.getByRole("heading", { level: 1, name: "Medication reconciliation" });
    const region = h1.closest("section");
    expect(region).toHaveAttribute("aria-labelledby", "reconcile-title");
    for (const s of document.querySelectorAll("section")) expect(s).toHaveAttribute("aria-labelledby");
    expect(screen.getByTestId("nlm-attribution")).toHaveTextContent(NLM_ATTRIBUTION);
    expect(screen.getByRole("status")).toHaveTextContent(/3 issue\(s\) and 1 notice\(s\)/);
    expect(screen.getByRole("status")).toHaveTextContent(/1 comparison\(s\) could not be checked/);
    expect(window.location.search).toBe("?run=run1");
  });

  it("renders issues as ol > li > article with allergy first and a captioned sources table", async () => {
    installFetch();
    await runCheck();
    const list = document.querySelector("ol.issue-list");
    expect(list).not.toBeNull();
    const articles = list!.querySelectorAll(":scope > li > article");
    expect(articles).toHaveLength(3);
    expect(articles[0]).toHaveAttribute("data-type", "allergy_class");
    const table = within(articles[0] as HTMLElement).getByRole("table");
    expect(table.querySelector("caption")).toHaveTextContent(/Conflicting sources for Allergy: drug class: amoxicillin/);
    const cols = table.querySelectorAll("thead th");
    expect(cols.length).toBeGreaterThanOrEqual(4);
    cols.forEach((th) => expect(th).toHaveAttribute("scope", "col"));
    table.querySelectorAll("tbody th").forEach((th) => expect(th).toHaveAttribute("scope", "row"));
    expect(within(articles[0] as HTMLElement).getByText(new RegExp(PHRASING_LABEL.replace(/\//g, "\\/")))).toBeInTheDocument();
  });

  it("shows every source list as read, with not-stated fields and the unchecked comparison count", async () => {
    installFetch();
    await runCheck();
    const lists = screen.getByRole("heading", { level: 2, name: /Medication lists as read \(3\)/ }).closest("section")!;
    expect(lists).toHaveAttribute("aria-labelledby", "lists-title");
    expect(screen.getByTestId("unchecked-summary")).toHaveTextContent(/1 comparison\(s\) could not be checked/);
    expect(screen.getByTestId("unchecked-summary")).toHaveTextContent(/not counted as matches/);
    const orders = within(lists).getByTestId("source-3");
    expect(orders.tagName).toBe("TABLE");
    expect(orders.querySelector("caption")).toHaveTextContent(/New order as read \(demo\/new_order\/1/);
    const row = within(orders).getByRole("rowheader", { name: "Warfarin 2 tab daily" }).closest("tr")!;
    expect(within(row).getAllByText("not stated").length).toBeGreaterThanOrEqual(2); // dose and route
    orders.querySelectorAll("thead th").forEach((th) => expect(th).toHaveAttribute("scope", "col"));
    expect(within(lists).getByTestId("source-2")).toHaveTextContent(/could not be read \(timeout\)/);
  });

  it("renders a missing_field issue in the issue list with its source shown as not stated", async () => {
    installFetch();
    await runCheck();
    const articles = [...document.querySelectorAll("ol.issue-list > li > article")];
    expect(articles.map((a) => a.getAttribute("data-type"))).toEqual(["allergy_class", "dose_mismatch", "missing_field"]);
    const mf = within(articles[2] as HTMLElement);
    expect(mf.getByRole("heading", { level: 3 })).toHaveTextContent("Dose or frequency not stated: warfarin");
    expect(mf.getByText(/dose not stated in the first source listed/)).toBeInTheDocument();
    const table = mf.getByRole("table");
    expect(table.querySelector("caption")).toHaveTextContent(/Conflicting sources for Dose or frequency not stated/);
    const row = within(table).getByRole("rowheader", { name: "New order" }).closest("tr")!;
    expect(within(row).getByText("not stated")).toBeInTheDocument();
    expect(within(table).getByText("3 mg")).toBeInTheDocument();
    // reviewable like every other issue, and there is no control that hides issues by type
    expect(mf.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(mf.getByLabelText("Reason for dismissing")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByLabelText(/filter|hide/i)).toBeNull();
    expect(document.querySelector(".notice-list")).not.toHaveTextContent(/missing_field|not stated/i);
  });

  it("requires a labelled reason to dismiss and confirms with the keyboard", async () => {
    const fetchFn = installFetch();
    await runCheck();
    const articles = document.querySelectorAll("ol.issue-list > li > article");
    const second = within(articles[1] as HTMLElement);
    const reason = second.getByLabelText("Reason for dismissing");
    expect(reason.tagName).toBe("TEXTAREA");
    await userEvent.click(second.getByRole("button", { name: "Dismiss" }));
    expect(await second.findByRole("alert")).toHaveTextContent("A reason is required");
    expect(fetchFn.mock.calls.some(([u]) => String(u).endsWith("/dismiss"))).toBe(false);
    await userEvent.type(reason, "synthetic: known intentional change");
    await userEvent.click(second.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/Issue dismissed/));

    const first = within(document.querySelectorAll("ol.issue-list > li > article")[0] as HTMLElement);
    first.getByRole("button", { name: "Confirm" }).focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/Issue confirmed/));
    const statuses = screen.getAllByTestId("issue-status").map((el) => el.textContent);
    expect(statuses).toEqual(["confirmed", "dismissed", "open"]);
  });

  it("uses no colour literals or clinical-claim terms in pharma page files", () => {
    const files = [
      "../components/PharmaReconcile.tsx",
      "../app/pharmacist/reconcile/page.tsx",
      "../app/pharmacist/reconcile/pharma.css",
      "../lib/pharma.ts",
    ];
    for (const rel of files) {
      const text = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
      expect(text, rel).not.toMatch(/#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/);
      expect(text, rel).not.toMatch(/diagnos|prescrib|treat/i);
    }
  });
});
