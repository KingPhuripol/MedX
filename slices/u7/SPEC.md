# U7 — V2 opens several synthetic cases, with engine output on each Overview

Owner request (2026-09-29): "make the system really work and really visible". Today the V2 demo serves one hard-coded
case (SYN-2026-0017, `backend/app/demo/router.py`). U7 lets the queue and case workspace open several synthetic cases,
so viewers can see the Overview summary and the safety behaviour across different patients. Base is `factory/u6`
(`95702be`); main may already contain u6.

Roles: planner = this spec (Opus). Builder = Sonnet on `factory/u7`. Checker = `e2e-tester`. Reviewer = read-only
general-purpose reviewer. Deployment happens only after checker and reviewer both PASS **and** the owner says go.

## Scope (time-boxed; the numbered order is the priority)

1. **Committed demo fixture (synthetic only).**
   - Add `scripts/export_demo_cases.py`. It exports **6 cases** from the v1 synthetic dataset's **train split only**
     (`data/synthetic/v1`, gitignored locally). Never use dev, test or any `g2-heldout-*` split: those are evaluation
     data.
   - Cover at least: one case with a vitals red flag, one with a medication discrepancy, one with an allergy recorded,
     one with `null` allergy status, and one with a missing vital.
   - Export each case at its decision point T2 with the temporal filter: nothing with `available_at_time > T`.
   - Output goes to `backend/app/demo/fixtures/cases_v1.json` in the same shape the u6 case endpoint returns
     (header, `vitals` series, `allergies`, `labs`, `decision_time`), plus medication sources and timeline items.
   - Leave out gold labels, `expected_action` and injected-issue logs.
   - Write the script's seed/source/split into the fixture's `provenance` block.
2. **Router serves every fixture case.**
   - `backend/app/demo/router.py`: `GET` case, medications and timeline work for SYN-2026-0017 (unchanged) and for
     each fixture case. Any other id returns 404.
   - The queue lists every case, sorted with red flags first.
   - Workflow actions (acknowledge, handoff, confirm) stay working for SYN-2026-0017 only. Fixture cases are
     **view-only** and are clearly labelled so ("เคสตัวอย่างสำหรับดูข้อมูล — ยังไม่เปิดให้ดำเนินการ"), with no
     disabled buttons that look broken.
3. **Real engines on fixture cases, computed at request time.**
   - Red-flag banner: run the existing triage engine on main (`backend/app/triage/redflags.py`, current ruleset) on
     facts built from the snapshot vitals and demographics.
     - Rules that need symptom facts the snapshot cannot supply are shown as **not evaluated** ("ยังประเมินไม่ได้ —
       ข้อมูลอาการยังไม่ถูกดึง"). They are never shown as negative.
     - When the engine raises no alert, the banner says only that no alert was raised from the available data. It
       never says "safe".
   - Medication discrepancy count: run the existing pharma reconcile engine (`backend/app/pharma`) on the case's
     medication sources. Show the count and the Medications tab list from that output.
   - Show the engine and ruleset version in the Overview's safety summary.
4. **Web.**
   - `/app/queue` shows all cases. `/app/cases/<id>/overview` renders the u6 summary for any served case.
   - Remove the hard-coded `CASE_ID` and task-id assumptions only where they block this (`web/lib/demo.ts`,
     `CaseWorkspace.tsx` `:110`, `:120`), and keep SYN-2026-0017's workflow intact.

## Rules

- Carry every rule from U5 global rules 2–8 and U6.
- Tokens only. Red flags come first. Missing is never shown as normal or negative. There is no new h1 and no new
  `role="status"`. Every load-bearing selector keeps working.
- No new dependency. No external API. Mock provider only.
- Human confirmation stays required.

## Acceptance (checker)

- A1: the queue lists 7 cases (SYN-2026-0017 plus 6 fixture cases), with red-flag cases first.
- A2: each fixture case's Overview renders all 6 summary items. The banner or not-evaluated text matches the engine
  output returned by the API. The discrepancy count equals the pharma engine's issue count.
- A3: the null-allergy, missing-vital and not-evaluated paths render as missing or not evaluated in the live app.
- A4: the fixture holds no gold or eval keys, no item after T, and only train-split ids. A test enforces all three.
- A5: SYN-2026-0017's full journey e2e still passes. `make test`, vitest, tsc, and the e2e specs clinical-operations,
  a11y, theme and disclaimer all pass.

## Clinical risks

- A fixture case could look "safe" because symptom rules were not evaluated. The not-evaluated text is mandatory.
- View-only cases could be mistaken for actionable ones. The label is mandatory.
- Train-split cases shown publicly are synthetic and carry the synthetic label.
