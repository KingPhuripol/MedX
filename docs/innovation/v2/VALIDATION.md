# Validation record — 14 September 2026

This record covers synthetic software behaviour only. No real patient data, paid calls, hospital trial or clinical accuracy claim is included.

- Full suite: **465 tests passed** (`python3 -m pytest -q`). This includes the original 264 tests.
- Repository harness: **1,135 checks passed** (`python3 scripts/verify_harness.py`).
- React: production build and **3 Vitest tests passed**; npm production audit found zero known vulnerabilities.
- Browser: **8 Playwright checks passed** across desktop and tablet, including the complete reviewed workflow, keyboard entry, drawer focus return, narrow reflow, unsent-text and expired-session recovery, and Axe critical/serious checks.
- `git diff --check` passed.
- Offline CLI: create → correction → ask/check → draft → physician confirmation completed; only corrected evidence was cited.
- Browser: loaded the built `/workspace`, completed a synthetic case, confirmed revision 2 and visually inspected the BDMS-inspired semantic-token layout. Microphone recording and audible playback were not exercised because no speech endpoint is configured.
- Scripted regression: **24/24 passed**, zero invalid runs. Simulated timeout/malformed output, future/label/cross-case boundaries, idempotency, stale drafts, modifications, transcript correction, injection and restart are covered.
- Search: feedback heuristic and random search each evaluated 12 designs with equal development/validation repetition budgets; three candidates per method were validated.
- Freeze/held-out smoke: explicitly froze the fixed baseline and exercised 30 held-out configurations × 5 repetitions for each arm. This is pipeline verification, not final research selection. The selected fixed arm repeats the fixed baseline intentionally.

Machine-readable aggregate results are in `validation-summary.json`. Full local traces and source/data/configuration hashes are in ignored `artifacts/v2/*-20260912.json`; rerun the documented commands to regenerate them with fresh output filenames. The source hash captures uncommitted v2 Python implementation, so the Git HEAD alone is not the build identifier.

These 120 generated configurations share one factorial generator. Mock outputs and repeats are deterministic; they cannot establish LLM reliability, diagnostic utility, hospital generalization or clinical safety. Form/single/fixed comparisons assess the implemented orchestration and software assertions, not comparable autonomous LLM architectures. Expert-authored families, clinical gold labels, independent clinical review and live-provider robustness results remain pending. The constrained-language simulator scaffold is tested separately and is not evidence of a validated LLM patient simulator.

Transport tests use an in-process mock HTTP transport to check zero-budget network prevention, retained reservations on uncertain failures, sanitized errors and unconfirmed transcripts. No live external endpoint or vendor SDK compatibility is claimed. Future provider validation must verify semantic grounding and charge limits at the gateway, in addition to these contract checks.
