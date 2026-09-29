# Decisions

Dated approvals and material decisions. Old log (DEC-0001..0022) is in tag `archive/pre-factory-2026-09-26`.

## 2026-09-26 — Reset to Proposal v8
- **What:** removed old code and docs; `docs/PROPOSAL.md` is the single source of truth; four-role loop factory.
- **Approved by:** project owner (chat, 2026-09-26), including deletion and agent/config changes.
- **Rollback:** tags `archive/pre-factory-2026-09-26`, `archive/opd-2026-09-26`, `archive/agent-worktree-2026-09-26`; `../_archive/pre-factory-2026-09-26.tar.gz`.

## 2026-09-26 — Formulary licence decision (slice s5, Pharma Agent)
- **What:** which drug terminology the offline formulary (`backend/app/pharma/data/formulary.json`) may contain. Checked against primary sources on 2026-09-26 (planner), applied by the s5 builder.
- **RxNorm names + RXCUI (SAB=RXNORM): use.** NLM-created content is public domain; acknowledgement requested; the full release contains proprietary sources needing a UMLS licence — https://www.nlm.nih.gov/research/umls/rxnorm/docs/termsofservice.html. Current Prescribable Content is "No license required; public domain" — https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html. Only RXNORM ingredient names and RXCUIs are committed; no non-RXNORM SAB strings.
- **RxNav / RxClass APIs: curation time only.** Free, no licence (SNOMED CT exception), ≤20 req/s, NLM statement must be displayed — https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html, https://lhncbc.nlm.nih.gov/RxNav/applications/RxClassIntro.html. All 54 ingredient RXCUIs were verified via RxNav `/REST/rxcui.json` on 2026-09-26 (all TTY=IN); class names were cross-checked against RxClass FDASPL `has_epc`. No SNOMED CT-derived class data is committed.
- **Drug classes: FDA EPC names** (US federal work). One team grouping (`anticoagulant_group`) is recorded as team-authored. MED-RT is not used; the MED-RT UMLS restriction-level page (https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/MED-RT/index.html) returned HTTP 502 on 2026-09-26 and must be re-checked by the curator before any MED-RT use.
- **WHO ATC/DDD: do not commit.** "Copying and distribution for commercial purposes is not allowed. Changing or manipulating the material is not allowed." — https://www.whocc.no/copyright_disclaimer/. Proposal 3.2.4 allows RxClass or ATC; EPC satisfies it. Revisit only by human decision.
- **Thai Medicines Terminology (TMT): do not commit.** Release files are login-gated (https://this.or.th/service/tmt/download/) and the site is all-rights-reserved with no public redistribution licence (https://this.or.th/service/tmt/). `tmt_id` is reserved as `null`; Thai brand / Thai-script aliases are team-authored with `alias_source` recorded. Using TMT needs written permission from THIS plus a new entry here.
- **Attribution (shown on `/pharmacist/reconcile` and stored in formulary metadata):** "This product uses publicly available data from the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product."
- **Enforced by:** `test_formulary_licence_and_coverage` (0 ATC-pattern and 0 TMT-pattern codes).
- **Approved by:** planner decision in `slices/s5/SPEC.md`; pending human confirmation. Clinical sign-off of `cross_reactivity.json` and of `duplication_relevant` / `allergy_group` flags by a pharmacist is required before any non-synthetic use.

## 2026-09-26 — OPEN: do `missing_field` notices count as S5-A06 false alerts? (slice s5)
- **Context:** reviewers found that a dose or frequency not stated in one source was silently read as agreement (HIGH, CLAUDE.md data rule 6). The fix raises a visible, audited `missing_field` notice for every such comparison and shows every source list on the page.
- **Effect on A06:** A06 counts every issue and notice. The clean fixtures deliberately leave dose (about 40%) and frequency (about 15%) out of patient-reported lines, so clean lists now average 1.10 alerts (test) and 1.375 (all), all of them `missing_field` notices. With those notices excluded, the value is 0.00 on both scopes. Threshold: 0.10. Breakdown: `slices/s5/eval/results.json` → `alert_breakdown`.
- **Options:** (a) keep counting them, so A06 fails until the notice design or fixtures change; (b) report them as a separate "information gap" metric outside A06; (c) another rule decided by a human.
- **Status:** NOT DECIDED. The builder did not change the threshold or the metric. `test_eval_thresholds` fails on A06 alone and says so in its message.
- **Owner:** s5 implementation owner (ธัญรดา / ภูริณัฐ) with the project owner; pharmacist input advised.
- **Resolved:** 2026-09-27 by the project owner — see "2026-09-27 — S5 Pharma evaluation definitions" below; applied in `slices/s5r/SPEC.md`.

## 2026-09-27 — S5 Pharma evaluation definitions
- **What:** (1) A notice that a source does not state dose or frequency counts as an alert. Clean medication lists are therefore fully specified in every source; an incomplete source is its own labelled discrepancy type `missing_field`, injected and measured by recall like the others. The pipeline still never treats a missing value as agreement. (2) The S5 fixture set grows to at least 90 patients (at least 30 in the frozen test split) so each discrepancy type has at least 30 injected cases, one per patient, with patient-level bootstrap CIs.
- **Approved by:** project owner (chat, 2026-09-27).
- **Timing:** decided on dev results before any frozen test-split evaluation; thresholds unchanged (false alerts per clean list <= 0.10, recall per type >= 0.95).

## 2026-09-27 — Evaluation ledger: freeze and test runs allowed on factory branches
- **What:** Exception to `eval/ledger/README.md` rule 1 ("appends on `main` only"). A slice may freeze its evaluation manifests and run its single test-split evaluation on its own `factory/<slice>` branch, provided that: (1) the branch reaches `main` through `factory/int` by ordinary merges (no rebase, squash or force-push), so ledger history is preserved; (2) `python -m eval ledger verify --git-history` passes on `factory/int` and again on `main` after each merge; (3) only one slice appends to a given ledger file at a time — a ledger merge conflict is resolved per README rule 4 (redo the later freeze/run on top of the merged ledger), never by editing entries.
- **Applies to:** E1 and S6 now; later evaluation slices on the same terms.
- **Approved by:** project owner (chat, 2026-09-27).

## 2026-09-27 — Case Graph wiring (I2) prototype defaults
- **What:** For the research prototype on synthetic data, all labelled "pending clinical sign-off" (D1): (D-I2-1) vitals freshness window 60 min per vital, citing RCP NEWS2 (2017) Chart 4; a reading older than the window is `not_evaluated` with its time shown. (D-I2-2) `as_of` ceiling = latest `available_at_time` + 5 min on the assess API, plus a floor. (D-I2-3) same-timestamp conflicting readings resolve to the worse value or are flagged; latest-wins vs worst-in-window across timestamps is reported only, not decided. (D-I2-4) a symptom the patient never mentions is `unknown`, never `absent`; only an explicit denial is `absent`. (D-I2-5) graph export schema bumps to `casegraph-export/0.3`; ledger appends are sequenced after E1 (one writer at a time).
- **Scope:** synthetic data only; before any real data a licensed clinician must approve D-I2-1 to D-I2-4.
- **Approved by:** project owner (chat, 2026-09-27).

## 2026-09-27 — S6 test split redone on a fresh held-out set
- **What:** The S6 ledger recorded the frozen test evaluation `s6-care-test-0001` twice (runs seq 2 and 4, identical predictions sha256 `281c8d9f…`, the second a report re-render). The owner chose to redo it rather than accept it. `s6-care-test-0001` is retired and relabelled "seen — not a held-out result"; it must never be reported as the S6 test result. S6 may be improved on train/dev only; then a fresh held-out test set is generated from a new seed (patients disjoint from all existing splits), its manifest frozen before any run, and evaluated exactly once. The runner must allow a report re-render of an existing run without appending a new run line.
- **Approved by:** project owner (chat, 2026-09-27).

## 2026-09-27 — D-s6r-2: S6 held-out case mix fixed before any held-out result (orchestrator ruling)
- **What:** The first S6r held-out set (seed 20260927, data_factory v1.2.1) had 7 pregnancy cases against the predeclared S6R-A07 target 2 ± 2. Before any held-out prediction or result existed, the orchestrator ruled to add a held-out-only pregnancy quota (data_factory v1.2.2), regenerate with the same seed (tree `552b1acd…`, 2 pregnancy cases), rewrite the unfrozen manifest (d55273b), then freeze and run once (fec7677, d423d15). The v1 default-seed output is byte-identical.
- **Basis:** within the owner's 2026-09-27 decision "S6 test split redone on a fresh held-out set" (same case mix); no threshold, metric or seed changed.
- **Decided by:** main-session orchestrator, 2026-09-27; reported to the owner in chat the same day.
- **Open:** D-s6r-1 — the S8 harness owner (สุปรียา) reviews the `eval/runner.py` re-render change (identical frozen test re-run = re-render, no new run line).

## 2026-09-28 — S5 Pharma: final dose-grammar round (rev 5), then close
- **What:** Implement slices/s5r4/SPEC.md revision 5 (86ccf86) in one final build/check/review round (S5r5). Whatever that round still finds is recorded in slices/s5r4/RESIDUAL_RISK.md for pharmacist acceptance and the slice closes; no further grammar revisions before the 8–9 Oct Proposal presentation.
- **Approved by:** project owner (chat, 2026-09-28).
- **Open:** pharmacist sign-off on the rev-5 vocabularies (V_EN_FREE, V_TH_FREE, V_EN_PHRASES, P3_WORDS, P4 DAILY/MULTI, TIME_SLOTS) and on RR-01…RR-07.

## 2026-09-29 — One integrated app on main; stray UIs dropped; worktrees removed
- **What:** Running `make dev` from different worktrees showed different UIs: a green "CARIVA / Hospital Green" UI (uncommitted in `Full-Agent-i2`), a blue UI (uncommitted Tailwind rewrite in agent worktree `agent-a9f2…`, `--primary:#0B5CAD`), and the old S0 `--accent:#0b4f9c` in pre-T1 worktrees. Both uncommitted UIs are dropped, since they break the T1 theme rule. `factory/int-e1proj` and `factory/s5r5` are merged into `factory/int2` (34dd86e); `factory/int2` is merged into `main`; the 13 old worktree folders are removed.
- **Kept:** all branches. Green UI: `git stash` "green-cariva-ui dropped 2026-09-29" and `artifacts/archive/green-cariva-ui-*` (gitignored, local). Per-worktree dirty/untracked files and ignored evidence (artifacts, data, dev.db): `artifacts/archive/worktrees/<name>/` (local, gitignored).
- **Open from the s5r5 merge:** pharma `ExtractOutput`/`PhraseOutput` accept the exact mock label `"MOCK — not clinical"` (single-registry mock adapter); mock pharma model version strings now carry the rules version. Needs reviewer confirmation. Integration audit (read-only): CONDITIONAL_PASS. Further items: `/pharmacist/reconcile` does not yet use PageFrame (eyebrow, claim, `→` strip) and is missing from the `theme.spec.ts` PAGES list; the S5 eval is not in `eval/ledger`.
- **Verified on main (e887943):** `make test` 2136 passed / 3 skipped (pg), vitest 80/80. `make e2e-pharma` 10/10 (axe clean). After `make data`: care, a11y and the other specs pass; only `voice-intake.spec.ts` "nurse runs a synthetic Thai intake…" fails (evidence 2 vs 7), a failure that predates int2 and is documented in slices/int2/SPEC.md:130. S5 eval re-run is byte-identical; `eval ledger verify --git-history` OK. Theme grep for green/CARIVA/old blue: 0 hits.
- **Approved by:** project owner (chat, 2026-09-29).

## 2026-09-29 — MedX web design: hospital blue replaces SCBX grey/purple
- **What:** The "MedX Clinical Operations" UI (hospital-blue tokens, `--primary:#0B5CAD`, SCBXBeta2, AppShell, `/app/queue`, `/demo`, per `docs/UI-SPEC.md`; branch `ui/medx-clinical-ops`) becomes the main web design, replacing the T1 grey/purple palette. The CLAUDE.md theme rule is updated to match. Token discipline is unchanged: only `web/app/theme.css` tokens, no ad-hoc colours, MedX wordmark, never the SCBX logo.
- **Kept:** the safety e2e coverage that branch deleted (disclaimer, role gating, red-flag-first care, triage, a11y/axe, theme) is adapted to the new UI, not dropped.
- **Approved by:** project owner (chat, 2026-09-29): "อยากที่จะเอาสีฟ้าเป็นอันหลัก เพราะสีม่วงมันแย่เกินไป".

## 2026-09-29 — Public Vercel demo: two links (grey/purple T1 and hospital blue U4)
- **What:** Deploy two public Vercel projects under account `kingphuripol` for the advisor: (1) the grey/purple T1 UI (main at 9f0eb0d) and (2) the hospital-blue U4 UI (after U4 passes its tests). Each is the Next.js web plus the FastAPI backend as a Vercel Python function.
- **Scope and limits:** mock provider only (external providers refused by config); synthetic data only; SQLite in `/tmp`, so state resets when an instance is recycled; research-prototype disclaimer on every page.
- **Login:** no password. With `PUBLIC_DEMO=1` (Vercel only), the login page offers one-click nurse, physician and pharmacist buttons; RBAC still applies per role. Local and dev builds keep password login.
- **Approved by:** project owner (chat, 2026-09-29), including uploading code to Vercel and "no password" for the demo accounts.
- **Take-down:** `vercel remove <project>` by the owner, or on request.

## 2026-09-29 — Public Vercel demo deployed (both links live)
- **Links:** grey/purple T1: https://medx-demo-t1.vercel.app (project `medx-demo-t1`, source `factory/d1` aa3b557 = main b0f668c + D1). Hospital blue U4: https://medx-demo-u4.vercel.app (project `medx-demo-u4`, source `factory/u4` 138153b = U4 + D1, plus `DEMO_MODE=1` for the `/demo` launcher).
- **Env (both):** `PUBLIC_DEMO=1`, `NEXT_PUBLIC_PUBLIC_DEMO=1`, a random `SESSION_SECRET` per project (not recorded).
- **Smoke-tested live:** `/api/health` reports mock; one-click role login; physician sees 40 synthetic cases (80 assess buttons); other roles' APIs give 403; password login 404; forged cookie 401; blue nurse lands on `/app/queue`.
- **Incident:** the first T1 attempt auto-created a project named `t1` without env vars (the `--scope` flag failed). It was removed within minutes.
- **main** now carries U4 + D1 (hospital blue is the main design). The U4 route change (role homes go to `/app/queue`; real triage/care/voice pages stay at their routes inside the shell, with no demo-case embedding) is pending owner confirmation.
- **Take-down:** `vercel project rm medx-demo-t1` / `vercel project rm medx-demo-u4`.

## 2026-09-29 — Gate 2: AI-simulated users instead of real clinicians
- **What:** For Gate 2, AI-simulated users and simulated scenarios (τ-bench style: an LLM plays nurse / OPD physician / pharmacist and uses tools) stand in for usability testing with real doctors and nurses, who could not be recruited in time.
- **External API:** synthetic cases only may be sent to an OpenAI-compatible endpoint (OpenAI, small mini/nano model, total budget 5 USD) acting as the **simulated user**. MedX itself stays on the mock provider. The key lives only in the owner's local environment, never in the repo.
- **Claim limit:** results are reported as "Simulated-user evaluation (synthetic)" and never as human usability or user validation.
- **Approved by:** the project's physician advisor (name withheld under PDPA), relayed by the project owner in chat on 2026-09-29.

## 2026-09-29 — U5 UI/UX layout overhaul shipped (main 35bcada, blue demo redeployed)
- **What:** Opus lead audit (`slices/u5/AUDIT.md`, `SPEC.md`), then three Sonnet 5.5 workers in parallel: WP-A shell and shared primitives, WP-B nurse pages and case workspace, WP-C physician and pharmacist pages. The lead reviewed each package with one fix round, and the packages were integrated as `factory/u5-int`.
- **Login fix (b0eff99):** found during the audit. `/login` always showed the public-demo role picker because `PUBLIC_DEMO` was imported from a "use client" module.
- **Safety review:** CONDITIONAL_PASS (read-only, run as general-purpose/Opus, because the `clinical-safety-reviewer` agent preloads `security-review`, which needs a git remote). The conditions were fixed in `factory/u5-fix`:
  - Care Confirm after the suggestion.
  - Triage bar never reads all-clear when screening is incomplete.
  - Sticky action bar cannot cover red flags on load.
  - Sign-out DOM order.
- **Verified:** `make test` on main: pytest 2170 passed / 3 skipped, vitest 97/97. e2e on u5-int: 77 passed, 1 known voice-intake failure; fix-branch specs 60/60. Live https://medx-demo-u4.vercel.app redeployed from 35bcada and smoke-tested.
- **Open:**
  - Triage Confirm should also gate on incomplete screening. This is an API contract change and needs an owner decision.
  - Follow-ups: DataTable card-mode semantics; care red-flag section tone when there are 0 alerts; pharma high-severity chip tone; demo physician ack server-side; legacy CSS cleanup.
- **Approved by:** project owner (chat, 2026-09-29), lead + workers plan; redeploy within the approved blue-link scope.

## 2026-09-29 — Voice agent via OpenAI Realtime (synthetic audio only)
- **What:** Give the Voice intake (`/nurse/intake`) real Thai speech in and out through OpenAI Realtime. Speaking uses `gpt-realtime-2.1-mini` over WebRTC, and patient speech is transcribed with `gpt-4o-mini-transcribe`. The owner's OpenAI key is used.
  - The key stays server-side (`OPENAI_API_KEY` in gitignored `.env` and in Vercel env); the browser only gets a short-lived client secret.
  - Each transcribed patient utterance becomes the same Turn as typed text, so the existing rules-based intake policy decides the next question and extracts the facts. The voice model only speaks that question in Thai and never gives clinical advice.
- **Scope:** local `make dev`, plus the blue Vercel link (`medx-demo-u4`). This is a scoped exception to the 2026-09-29 public-demo "mock only" rule, and it covers only the voice session endpoint. The Model Gateway stays mock.
- **Access control on Vercel:**
  - a separate voice access code;
  - a maximum session length;
  - a per-instance rate limit.
- **Recommended but not done by us:** a monthly budget on the OpenAI project.
- **Data:** synthetic role-play or scripted voices only. Never real patients (CLAUDE.md data rule 7).
- **Approved by:** project owner (chat, 2026-09-29): "ยืนยัน สังเคราะห์เท่านั้น", local + Vercel.
- **Note:** the key was pasted into chat in plain text; the owner should rotate it after the demo.
- **2026-09-29 addendum (V1 spec, `slices/v1/SPEC.md`):**
  - **D-V1-1:** V1 uses direct browser WebRTC to OpenAI Realtime for speech in and out only. It does not use LiveKit with function-calling extraction as PROPOSAL §3.1 describes for Realtime mode. The policy picks every question, and extraction stays on the existing rules path. Recorded by the orchestrator under the owner's 2026-09-29 approval.
  - **D-V1-2 (default pending owner):** handoff from `/live` navigates to `/nurse/triage`, or to the case triage tab when the page was opened with a case. No new voice→triage API is added in V1.

## 2026-09-29 — Merge u6 into main and redeploy the hospital-blue demo
- **What:** merge `factory/u6` (V2 Overview as the shared case summary; checker PASS, reviewer PASS, `slices/u6/VERDICTS.md`) into main, then redeploy Vercel project `medx-demo-u4` from main. Main already carries U5, so the redeployed demo also shows the U5 UI overhaul.
- **Scope and limits:** same as the 2026-09-29 public demo entry. Synthetic data only, mock provider only, research-prototype disclaimer on every page, no password with `PUBLIC_DEMO=1`.
- **Also approved:** a step-by-step journey slide, a short screen-recording demo, a PDF export of the Gate 2 deck, and extending V2 so it opens several synthetic cases (a separate slice, deployed only after its checker and reviewer pass).
- **Approved by:** project owner (chat, 2026-09-29).

## 2026-09-29 — Redeploy medx-demo-u4 from main including V1 MedX Live voice
- **What:** deploy main HEAD (u6 Overview summary plus the V1 MedX Live voice merge, `/live`) to `medx-demo-u4`, rather than u6 alone. The existing production env vars for voice stay as the voice session set them.
- **Why:** the owner chose "deploy main ทั้งหมด (u6 + voice)" when told that main now contains the voice agent. The voice agent's own approval is entry 61ab4c9 (synthetic audio only, local + blue link).
- **Approved by:** project owner (chat, 2026-09-29).
