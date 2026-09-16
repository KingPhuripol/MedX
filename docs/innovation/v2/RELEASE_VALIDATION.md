# Completion validation — 14 September 2026

The delivery extends the initial prototype with conversation/proposal acceptance, short database transactions around durable run reservations, a fixed typed tool registry, editable UI forms, compatible provider adapters, and a separately written synthetic vignette suite.

## Verified

- 465 Python tests pass. Repository harness passes 1,135 checks. The Prompt-based React production build and three Vitest component tests pass; dependency audit reports zero known production vulnerabilities.
- Eight Playwright checks pass at 1440×900 and 768×1024. They cover create → conversation → batch proposal review → draft edit → confirmation, keyboard access, unsent-text recovery, responsive drawer focus/reflow, expired-session recovery, and Axe with zero critical/serious findings.
- Repository harness: 1,135 checks pass. JavaScript syntax and `git diff --check` pass.
- The original 24 scripted regressions pass, and all 120 authored synthetic workflow vignettes pass the fixed-workflow assertions.
- Tests cover conversation without draft creation, reviewed/edited proposal acceptance, retry without duplicate facts, evaluator-role denial, concurrent human writes during provider latency, stale-result suppression and interrupted-run recovery without automatic replay.
- HTTP contract tests cover compatible chat completion and multipart transcription with a loopback free adapter, plus remote free-mode rejection, zero-budget prevention and transport failures. These are mocked HTTP responses, not live model results.
- Browser walkthrough: the built `/workspace` UI was visually inspected with the black/blue semantic-token system and self-hosted Prompt. Real recording/transcription remains untested because no speech endpoint is configured.
- Search: feedback heuristic and random search each evaluate 12 candidates, followed by three validation candidates. The fixed baseline was frozen to exercise the complete held-out pipeline, with 30 cases × 5 repeats per arm. This is a pipeline smoke selection, not the final research selection.

`release-validation-20260914.json` contains the current source/scenario/configuration hashes and aggregate results. The corresponding full traces were regenerated in `/tmp/frontdoor-*-20260914.json`; they are reproducible with the commands in `QUICKSTART.md`. Existing experiment files are preserved; changed code requires a new search/freeze sequence.

## Remaining external validation

No reasoning endpoint, speech endpoint or paid budget was configured on this machine. Adapters are implemented and contract-tested; live model quality, Thai ASR and device recording remain untested. The application reports this distinction. No paid calls or real patient processing occurred.

The 120 TSV entries are synthetic workflow vignettes, not clinician-approved or independent clinical disease families. Time/ID expansion and workflow patterns are shared. State/action checks and extractive content checks are software evidence. Free-form semantic correctness and diagnostic usefulness require independent clinical review. Invalid simulator expectations are reported separately before agent execution. Actual billed cost is unknown; reported reservations are not invoices.

The simulator's optional language-model scaffold and clinician-calibrated semantic judging are not validated clinical components. The default simulator remains scripted. Nan Hospital participation, department-specific policies and clinical evaluation remain pending and do not block running this delivered offline system.

Final checks on 13 September 2026 additionally cover an invalid designer exhausting exactly 12 proposal attempts and retaining the baseline, plus frontend request-state checks that retain uncertain mutations but allow text after a speech-network failure.

# Re-validation — 16 September 2026

`release-validation-20260916.json` is the current record. **The 14 September record stopped
describing the repository the same evening it was written**: the three-step workspace refactor was
left in the working tree uncommitted, so `code_revision` `5f73ff4e` named a revision that did not
contain the code being described. Those changes are now committed, along with the safety work below,
and this record names a revision that exists.

## What changed

The deterministic screen now runs on the `/workspace` path. It had not, and the gap was total:
`grep` over `innovation/v2/` returned zero hits for `ModelGateway`, `SafetyPolicy`, `red_flag`,
`urgency` and `audit`. `SafetyPolicy.screen()` is now a wrapper over `screen_evidence()`, which takes
evidence types rather than a `GatewayRequest`, and `innovation/v2/safety.py` calls the same function.
One implementation of SCR-001 and SCR-002, two callers. `SafetyScreen` is attached to `ClinicalDraft`
rather than `DraftContent`, because `content` is what a provider produces and what a physician
`MODIFY` replaces, so a finding stored there would be one a reviewer could overwrite.

The v2 interface now carries `RESEARCH PROTOTYPE — HUMAN REVIEW REQUIRED` and the non-deployment
sentence, as `innovation/ui/templates/base.html` always has. `ESCALATE`, accepted by `ReviewDecision`
since v2 shipped but never sent by any client, is reachable from the review panel.

`playwright.config.ts` no longer hardcodes `/opt/anaconda3/bin/python3`, so the e2e suite runs on any
machine with the requirements installed. The case-id `pattern` attribute was `[A-Za-z0-9_-]+`, which
throws under the RegExp `v` flag, so Chrome had silently disabled that field's client-side
validation; it now rejects a Thai name and a space while still accepting `demo-001`.

## Verified

- **468 Python tests** pass (three new; deleting the v2 screen call fails two of them, checked).
  Repository harness **1,137 checks**. Smoke test passes.
- Frontend quality gate: **9 Vitest tests**, `tsc --noEmit` clean, `vite build`, **8 Playwright
  checks** at 1440×900 and 768×1024 with Axe reporting no critical or serious findings.
- The 24 scripted regressions were re-run on this revision: 24 valid runs, success rate 1.0,
  no failures, `clinical_verdict: NOT_REVIEWED`.
- Browser walkthrough of the `QUICKSTART.md` demo script: a case carrying a chief complaint and no
  vital sign shows urgency floor `URGENT_REVIEW`, `REQUIRED_INFORMATION_INCOMPLETE` as `TRIGGERED`,
  `COMPLAINT_NOT_EVALUATED_BY_RULE` as `UNKNOWN`, and the missing `VITAL` named — each in text, not
  by colour alone.

## Not re-run, and not to be cited as if it were

**Search, freeze and held-out were not re-run.** `QUICKSTART.md` states that changed code requires a
new search/freeze sequence, so the selection evidence in `release-validation-20260914.json` and
`validation-summary.json` is carried, not renewed. Note also that `validation-summary.json` records
`policy: synthetic-workflow-v1` while `innovation/v2/runtime.py:14` has read `synthetic-workflow-v2`
since commit `8c1f601` — that mismatch predates this work and is recorded rather than edited into a
file documenting an earlier run.

No reasoning endpoint, speech endpoint or paid budget is configured. Live model quality, Thai ASR and
device recording remain untested, and no paid call was made.

## Two acceptance criteria still do not hold on v2

`docs/innovation/ACCEPTANCE_CRITERIA.md` now states per criterion whether it was measured on v1, on
v2, or neither. Two rows read **no**: **A0**, because v2 does not route through the Model Gateway,
and **A3.5**, because v2 writes no audit record tying model version, provider version, reviewer
identity and overrides together. Closing either is a decision under DEC-0003, not a defect fix
(TASK-0034, RISK-0016). Until then, no claim that the Clinical Front Door satisfies A0–A4 may be made
about `/workspace` without naming those two rows.
