# U4 — Hospital-blue MedX UI becomes the main web design

## Goal

Merge `ui/medx-clinical-ops` (bc259b3) into current `main` so the hospital-blue "MedX Clinical Operations" UI
(`docs/UI-SPEC.md`) is the only web design, without losing the S5 pharma page, the int2 care/I2 screening work or any
safety test coverage. Owner decision: `docs/DECISIONS.md` 2026-09-29 "MedX web design: hospital blue replaces SCBX
grey/purple".

## Scope decisions

- Role homes `/nurse`, `/physician`, `/pharmacist` redirect to `/app/queue` (UI-SPEC).
- Domain work pages (`/nurse/triage[/:id]`, `/nurse/intake`, `/physician/care[/:id]`, `/pharmacist/reconcile`) keep
  their routes and RoleGuard and render inside the `AppShell`; the shell navigation links each role to its pages.
  They are not redirected into `/app/cases/SYN-2026-0017/...`: that header shows a different synthetic patient, and
  the case workspace needs a demo run, so the real triage/care flows would be unreachable without `DEMO_MODE=1`.
- The case workspace no longer embeds a real assessment through `?assessment=` (same wrong-patient reason).

## Acceptance

- **A1** `web/app/theme.css` holds the blue tokens only (grey/purple palette removed, not aliased); every page renders
  with blue tokens, SCBXBeta2 and one visible MedX wordmark, no brand logo; `pharma.css` uses theme tokens only.
- **A2** Restored and adapted e2e specs: `a11y`, `care`, `disclaimer`, `roles`, `theme` (rewritten), `triage`,
  `voice-intake`; `clinical-operations` kept. Axe: 0 serious/critical at 1280×800 and 768×1024 on login, queue,
  `/demo`, all case sections, role work pages, 403, 404. Theme: token-only computed colours, wordmark, fonts, no
  external requests, focus rings, no horizontal overflow at 1280/768/390.
- **A3** `web/tests/theme.test.ts` asserts the blue palette, contrast pairs, no hard-coded colours (all web sources),
  every `var(--x)` defined, self-hosted fonts, no brand logo, MedX titles; all vitest pass.
- **A4** Backend mounts pharma and demo routers; demo API synthetic-only with auth/RBAC; `make test` passes.
- **A5** `make data`, `make e2e` and the e2e-pharma specs on non-default ports: 0 failures except the known
  `voice-intake.spec.ts` "nurse runs a synthetic Thai intake…" (evidence 2 vs 7; slices/int2/SPEC.md:130).
- **A6** Recovered one-line files formatted with prettier (print width 120), no behaviour change.

## Evidence

Test counts and commit SHAs are in the builder report. Screenshots: `artifacts/factory/u4/*.png` (gitignored),
written by `web/e2e/theme.spec.ts`.
