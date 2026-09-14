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
