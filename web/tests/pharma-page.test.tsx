import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "./router-mock";

import PharmaReconcile from "@/components/PharmaReconcile";
import { NLM_ATTRIBUTION, PHRASING_LABEL, formatDose, runSummary } from "@/lib/pharma";

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
  rule_id: "missing_field@2.1.0",
  field: "dose",
  detail: { field: "dose", field_status: "not_stated", incomplete_source: "new_order", stated_in: ["home_list"] },
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
  comparisons_made: 3,
  unchecked_comparisons: 1,
  unchecked_by_reason: { unverifiable: 0, not_recognised: 0, not_stated: 1 },
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

type RunLike = Omit<typeof RUN, "issues"> & { issues: Record<string, unknown>[] } & Record<string, unknown>;

function installFetch(run: RunLike = RUN) {
  decided = {};
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
    if (url === "/api/home/pharmacist") return json({ role: "pharmacist" });
    if (url === "/api/pharma/fixtures")
      return json({ fixtures: [{ fixture_ref: "demo-01", patient_ref: "s5-demo-01", split: "demo", label: "Demo" }] });
    const withStatus = () => ({
      ...run,
      issues: run.issues.map((i) => ({ ...i, status: decided[i.issue_id as string] ?? "open" })),
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
    expect(mf.getByRole("heading", { level: 3 })).toHaveTextContent("Dose not stated: warfarin");
    expect(mf.getByText(/dose not stated in the first source listed/)).toBeInTheDocument();
    const table = mf.getByRole("table");
    expect(table.querySelector("caption")).toHaveTextContent(/Conflicting sources for Dose not stated/);
    const row = within(table).getByRole("rowheader", { name: "New order" }).closest("tr")!;
    expect(within(row).getByText("not stated")).toBeInTheDocument();
    expect(within(table).getByText("3 mg (quantity not stated; stated amount used)")).toBeInTheDocument();
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

  it("scope limits: the scope section is visible before and after a run", async () => {
    installFetch();
    render(<PharmaReconcile />);
    const check = () => {
      const scope = screen.getByRole("heading", { level: 2, name: "Scope of this check" }).closest("section")!;
      expect(scope).toHaveAttribute("aria-labelledby", "scope-title");
      expect(scope).toHaveTextContent(/dose per administration \(strength × quantity\)/);
      for (const term of ["drug–drug interaction", "dose range", "renal", "hepatic", "route"])
        expect(within(scope).getByText(/Not checked/).nextElementSibling).toHaveTextContent(new RegExp(term));
      // s5r3: the dose is read by a fixed, listed grammar; anything else could not be verified (residual risk kept).
      expect(scope).toHaveTextContent(/read by a fixed, listed grammar/);
      expect(scope).toHaveTextContent(/Any other dose form is shown as could not be verified/);
      expect(scope).toHaveTextContent(/still read as 2 tablets per dose/);
      expect(scope.textContent).not.toMatch(/may be misread|all doses|every dose/i);
    };
    await screen.findByRole("button", { name: "Run check" });
    check();
    await waitFor(() => expect(screen.getByLabelText("Synthetic patient")).toHaveValue("demo-01"));
    await userEvent.click(screen.getByRole("button", { name: "Run check" }));
    await screen.findByRole("heading", { level: 2, name: /Issues for pharmacist review/ });
    check();
  });

  const ALLERGY_DETAIL: Record<string, Record<string, unknown>> = {
    allergy_direct: { basis: "The allergen maps to the ingredient amoxicillin (RxCUI 723) in formulary s5-formulary-1.0.0.", formulary_version: "s5-formulary-1.0.0" },
    allergy_class: {
      basis: "The allergen and amoxicillin share the class Penicillin-class Antibacterial.",
      class_name: "Penicillin-class Antibacterial",
      class_source: "FDA Established Pharmacologic Class (EPC) name, US federal work",
      formulary_version: "s5-formulary-1.0.0",
    },
    allergy_cross_reactivity: {
      basis: "Curated cross-reactivity row xr-001 (s5-cross-reactivity-1.0.0); pending pharmacist sign-off.",
      citation: "Khan DA, et al. Drug allergy: A 2022 practice parameter update. doi:10.1016/j.jaci.2022.08.028",
      clinical_review_status: "pending_pharmacist",
    },
  };

  for (const [key, type] of [["direct", "allergy_direct"], ["class", "allergy_class"], ["cross_reactivity", "allergy_cross_reactivity"]]) {
    it(`allergy basis[${key}]`, async () => {
      installFetch({ ...RUN, issues: [{ ...issue(1, type, 1, "high"), detail: ALLERGY_DETAIL[type] }] });
      await runCheck();
      const basis = screen.getByTestId("allergy-basis");
      expect(basis).toHaveTextContent(String(ALLERGY_DETAIL[type].basis));
      if (type === "allergy_class") {
        expect(basis).toHaveTextContent("Penicillin-class Antibacterial");
        expect(basis).toHaveTextContent(/class source: FDA Established Pharmacologic Class/);
        expect(basis).toHaveTextContent("s5-formulary-1.0.0");
      }
      if (type === "allergy_direct") expect(basis).toHaveTextContent("amoxicillin (RxCUI 723) in formulary s5-formulary-1.0.0");
      if (type === "allergy_cross_reactivity") {
        expect(basis).toHaveTextContent("doi:10.1016/j.jaci.2022.08.028");
        expect(basis).toHaveTextContent("Review status: pending pharmacist sign-off");
      }
    });
  }

  const OVERCLAIM = /all doses|every dose|doses match|Every comparison/i;
  const WORDING: Record<string, { made: number; by: { unverifiable: number; not_recognised: number; not_stated: number } }> = {
    zero: { made: 6, by: { unverifiable: 0, not_recognised: 0, not_stated: 0 } },
    not_stated: { made: 4, by: { unverifiable: 0, not_recognised: 0, not_stated: 2 } },
    not_recognised: { made: 4, by: { unverifiable: 0, not_recognised: 1, not_stated: 0 } },
    unverifiable: { made: 3, by: { unverifiable: 3, not_recognised: 0, not_stated: 0 } },
  };
  for (const [key, w] of Object.entries(WORDING)) {
    it(`unchecked wording[${key}]`, async () => {
      const unchecked = w.by.unverifiable + w.by.not_recognised + w.by.not_stated;
      installFetch({ ...RUN, comparisons_made: w.made, unchecked_comparisons: unchecked, unchecked_by_reason: w.by });
      await runCheck();
      const summary = screen.getByTestId("unchecked-summary");
      const page = document.body.textContent ?? "";
      if (unchecked === 0) {
        expect(summary).toHaveTextContent("Every comparison between lists was made");
        expect(summary).toHaveTextContent("dose per administration and frequency");
        expect(within(summary).getByRole("link", { name: "Scope of this check" })).toHaveAttribute("href", "#scope-title");
      } else {
        expect(page).not.toMatch(OVERCLAIM);
        expect(summary).toHaveTextContent(`${w.made} comparison(s) made; ${unchecked} comparison(s) could not be checked`);
        expect(summary).toHaveTextContent(
          `${w.by.unverifiable} not verifiable, ${w.by.not_recognised} not recognised, ${w.by.not_stated} not stated`,
        );
      }
      expect(runSummary({ comparisons_made: w.made, unchecked_comparisons: unchecked, unchecked_by_reason: w.by }).complete).toBe(
        unchecked === 0,
      );
    });
  }

  it("field status labels: not stated / not recognised / not verifiable (reason) and missing_field titles", async () => {
    const mf = (n: number, field: string, status: string, reason: string | null, sourceOverrides: Record<string, unknown>) => ({
      ...MISSING_FIELD_ISSUE,
      issue_id: `run1-i1${n}`,
      field,
      detail: { field, field_status: status, unverifiable_reason: reason },
      conflicting_sources: [src({ source_type: "new_order", raw_span: `line ${n}`, ...sourceOverrides }), MISSING_FIELD_ISSUE.conflicting_sources[1]],
    });
    installFetch({
      ...RUN,
      issues: [
        mf(1, "dose", "not_stated", null, { frequency_code: "q24h", frequency_status: "recognised", dose_status: "not_stated" }),
        mf(2, "frequency", "not_recognised", null, { dose_value: 3, dose_unit: "mg", dose_status: "resolved", frequency_status: "not_recognised" }),
        mf(3, "dose", "unverifiable", "variable_regimen", { dose_status: "unverifiable", dose_unverifiable_reason: "variable_regimen", frequency_code: "q24h" }),
        mf(4, "frequency", "not_stated", null, { dose_value: 3, dose_unit: "mg", dose_status: "resolved", frequency_status: "not_stated" }),
      ],
    });
    await runCheck();
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual([
      "Dose not stated: warfarin",
      "Frequency not recognised: warfarin",
      "Dose could not be verified: warfarin",
      "Frequency not stated: warfarin",
    ]);
    const rows = [...document.querySelectorAll("ol.issue-list article")].map(
      (a) => within(a as HTMLElement).getByRole("rowheader", { name: "New order" }).closest("tr")!,
    );
    expect(within(rows[0]).getByText("not stated")).toBeInTheDocument();
    expect(within(rows[1]).getByText("not recognised")).toBeInTheDocument();
    expect(within(rows[2]).getByText("not verifiable (variable regimen)")).toBeInTheDocument();
    expect(within(rows[3]).getAllByText("not stated").length).toBe(1);
    expect(screen.getByText(/frequency not recognised in the first source listed/)).toBeInTheDocument();
    expect(screen.getByText(/dose not verifiable \(variable regimen\) in the first source listed/)).toBeInTheDocument();
  });

  const NEW_REASONS: Record<string, string> = {
    range: "a range or alternative between two amounts",
    unparsed_token: "a dose form this checker does not read",
  };
  for (const [reason, label] of Object.entries(NEW_REASONS)) {
    it(`field status labels[${reason}]`, async () => {
      installFetch({
        ...RUN,
        issues: [
          {
            ...MISSING_FIELD_ISSUE,
            detail: { field: "dose", field_status: "unverifiable", unverifiable_reason: reason },
            conflicting_sources: [
              src({ source_type: "new_order", raw_span: "Warfarin 3 mg 1-2 tabs od", dose_status: "unverifiable", dose_unverifiable_reason: reason, frequency_code: "q24h" }),
              MISSING_FIELD_ISSUE.conflicting_sources[1],
            ],
          },
        ],
      });
      await runCheck();
      expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Dose could not be verified: warfarin");
      const row = within(document.querySelector("ol.issue-list article") as HTMLElement)
        .getByRole("rowheader", { name: "New order" })
        .closest("tr")!;
      expect(within(row).getByText(`not verifiable (${label})`)).toBeInTheDocument();
      expect(document.body.textContent).not.toMatch(/not verifiable \(unverifiable\)/);
    });
  }

  it("dose per administration: strength × quantity, or the stated amount when no quantity", async () => {
    expect(formatDose({ dose_value: 3, dose_unit: "mg", quantity: 2, dose_per_administration: 6, dose_status: "resolved" })).toBe("3 mg × 2 = 6 mg");
    expect(formatDose({ dose_value: 3, dose_unit: "mg", quantity: 0.5, dose_status: "resolved" })).toBe("3 mg × 0.5 = 1.5 mg");
    expect(formatDose({ dose_value: 3, dose_unit: "mg", quantity: null, dose_status: "resolved" })).toBe(
      "3 mg (quantity not stated; stated amount used)",
    );
    const dm = {
      ...issue(2, "dose_mismatch", 3, "moderate"),
      conflicting_sources: [
        src({ source_type: "home_list", dose_value: 3, dose_unit: "mg", quantity: 1, dose_per_administration: 3, dose_status: "resolved", frequency_code: "q24h" }),
        src({ source_type: "new_order", dose_value: 3, dose_unit: "mg", quantity: 2, dose_per_administration: 6, dose_status: "resolved", frequency_code: "q24h" }),
      ],
    };
    installFetch({ ...RUN, issues: [dm] });
    await runCheck();
    const table = within(document.querySelector("ol.issue-list article") as HTMLElement).getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Dose per administration" })).toBeInTheDocument();
    expect(within(table).getByText("3 mg × 2 = 6 mg")).toBeInTheDocument();
    expect(within(table).getByText("3 mg × 1 = 3 mg")).toBeInTheDocument();
  });

  it("unverifiable dose_mismatch title never says differs", async () => {
    installFetch({ ...RUN, issues: [{ ...issue(2, "dose_mismatch", 3, "moderate"), unverifiable: true }] });
    await runCheck();
    const h3 = screen.getByRole("heading", { level: 3 });
    expect(h3).toHaveTextContent("Dose not comparable (units): simvastatin");
    expect(h3.textContent).not.toMatch(/differs/i);
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
