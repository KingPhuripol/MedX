# U6 — V2 case Overview becomes the shared case summary

Owner request (2026-09-29): stay on V2 and fix "V2 needs more clicks". Gate 2 evidence (`simuser-g2-0001`, branch
`factory/g2-simuser`) found that preparing a case in V2 took 4.5 tool calls against 2.6 in the multi-system arm. Two
causes. The benchmark adapter under-represented the Overview. V2 also does not yet do what `docs/UI-SPEC.md:98` says:
Overview is the "shared case summary", but it has no vitals, allergy, labs or medications. This slice finishes V2 to
its own spec. It is not a new version.

Roles: planner = this spec (Opus). Builder = one Sonnet worker on branch `factory/u6` from main `35bcada`. Checker =
`e2e-tester`. Reviewer = read-only general-purpose reviewer (safety and UI-SPEC fit). The checker and reviewer never
edit product code.

## Scope

1. **Backend (additive only, `backend/app/demo/router.py`).**
   - Add synthetic `vitals`, `allergies` and `labs` to the fixed demo `CASE` (SYN-2026-0017).
   - `vitals` is a time-ordered series of at least 2 readings. Each reading has `observed_at`, `available_at_time`,
     hr, rr, sbp, dbp, spo2, temp_c, consciousness (ACVPU) and on_oxygen. A field may be `null`: missing, never 0.
   - `allergies` is a list of `{substance, reaction}`. `[]` means no known allergy was recorded. `null` means the
     allergy status is unknown. These are different states.
   - `labs` holds the latest results with `{test, value, unit, ref_low, ref_high, resulted_at}`.
   - Values must agree with the case's existing story and evidence ids (e.g. `EVD-VITAL-02`) and with the existing
     red-flag banner. Nothing may have `available_at_time` later than the case's decision time.
   - The case endpoint returns the new fields. Existing fields and routes are unchanged.
   - Add backend tests: the fields are present, null is preserved, and the temporal rule holds.
2. **Web Overview summary (`web/components/clinical/CaseWorkspace.tsx`, Overview section, today at `:361-397`).**
   On first open of `/app/cases/<id>/overview`, without clicking any tab, show:
   1. The red-flag banner, unchanged and still first.
   2. Chief complaint and onset (already present).
   3. **Latest vitals with a direction** against the previous reading (↑/↓/→ plus a word, not colour alone), with the
      time observed.
   4. **Allergy status**: listed substances and reactions, "ไม่มีประวัติแพ้ที่บันทึกไว้" for `[]`, and
      "ไม่ทราบสถานะการแพ้ — ต้องถาม" for `null`.
   5. **Current medications** (from the medications endpoint) with the **number of open discrepancies** and a link
      to the Medications tab.
   6. **Latest abnormal labs**, meaning any value outside its reference range, or "ไม่มีผลแล็บผิดปกติ" or
      "ยังไม่มีผลแล็บ".
   - Change `load()` (`:75-103`) to fetch medications on first open, not only on the Medications tab. The timeline
     stays lazy.
   - Types go in `web/lib/demo.ts`. Styles go in a co-located `*.module.css` using **tokens only** from
     `web/app/theme.css`.
3. **Tests.** Extend `web/e2e/clinical-operations.spec.ts`. On the Overview, before any tab click, assert that vitals,
   allergy, medications with a discrepancy count, and labs are visible. Add a vitest for the summary's missing-value
   rendering.

## Rules (carried from U5 `slices/u5/SPEC.md` global rules 2–8)

- Tokens only. There is no new h1 and no new `role="status"`.
- Red flags stay first in both DOM and visual order. The confirm gating is unchanged.
- Every load-bearing selector in U5 SPEC `:184-188` keeps working.
- axe reports 0 serious or critical issues at 1280×800, 768×1024 and 390 wide. There is no horizontal overflow.
- **Missingness:** a missing value is shown as missing and never as normal or negative.
- **Claim boundary:** the summary shows recorded facts. It adds no new interpretation, diagnosis or suggestion. Trend
  arrows describe the change in the recorded value only.

## Acceptance (checker measures)

- A1: a fresh load of the Overview at 1280×800 shows items 1–6 with no tab click and no scrolling past the first
  screen for items 1–4. Evidence is a screenshot plus a DOM assertion.
- A2: `make test`, `cd web && npx vitest run && npx tsc --noEmit`, and the e2e specs clinical-operations, a11y,
  theme and disclaimer all pass. The only allowed pre-existing failure is `voice-intake.spec.ts` (int2 note).
- A3: the null-vital and null-allergy fixture paths render as missing. This is covered by a unit test.
- A4: nothing changes outside the files named here, except tests.

## Clinical risks

- A trend arrow could be read as a clinical judgement. It is labelled as a change in the recorded value only.
- An empty allergy list could be confused with unknown status. The two states are required to render differently.
- A summary could hide a red flag below the fold. The banner is required to stay first.
