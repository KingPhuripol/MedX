# Decision Log

Machine-readable decisions are in `project_state/decisions.json` and validated against `schemas/decision.schema.json`. This document is the readable register. Decisions are append-only; superseded entries remain visible.

## DEC-0001 - One project, two tracks

- **Date:** 2026-08-11
- **Status:** accepted
- **Owners:** all five members
- **Decision:** Run one Senior Project under one title, with Research and Innovation as coordinated internal tracks.
- **Rationale:** The model contribution and Clinical Front Door share data, contracts, evaluation, and the final demonstration.
- **Consequences:** There is one schedule and one integration gate. Neither track may optimize in isolation at the expense of the joint deliverable.

## DEC-0002 - Flagship approximately 4B; 27B is stretch

- **Date:** 2026-08-11
- **Status:** superseded by DEC-0009 on 2026-08-26
- **Owner:** Phurinat Polasa
- **Decision:** Treat approximately 4B parameters as the flagship target. Permit 27B work only after the 4B release candidate passes architecture, data, safety, evaluation, compute, and schedule gates.
- **Rationale:** Evidence at small and 4B scales is more important than unsupported scale.
- **Consequences:** No 27B critical-path dependency and no 27B resource commitment before a separate approval.

## DEC-0003 - Stable Model Gateway

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Supreeya Nuamkhayan
- **Decision:** All Innovation inference uses the versioned Model API Contract through a Model Gateway. Mock and external APIs are prototype providers only.
- **Rationale:** Product work can proceed before the team model is ready without provider lock-in.
- **Consequences:** No provider-specific objects may cross the gateway boundary. Contract tests are required for every adapter.

## DEC-0004 - Patient-level temporal integrity

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Jakkapat Bunjongruxsa
- **Decision:** Split by patient before window generation and require `available_at_time` on every evidence and label item.
- **Rationale:** Encounter- or image-level splits and future information would inflate performance and invalidate the clinical simulation.
- **Consequences:** Any leakage finding invalidates affected results until data and experiments are rebuilt.

## DEC-0005 - Decision support with mandatory human review

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Thanrada Tungweerapornpong
- **Decision:** The system supports, but never autonomously makes, diagnosis, treatment, referral, or discharge decisions.
- **Rationale:** The project is a research prototype in a safety-critical domain.
- **Consequences:** User-facing outputs require limitations, uncertainty, escalation, and human confirmation.

## DEC-0006 - Restrict real-patient data from external APIs

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Jakkapat Bunjongruxsa
- **Decision:** Do not send real, identifiable, or linkable patient data to an external API without explicit, scoped, recorded authorization.
- **Rationale:** Privacy, consent, ethics, and vendor data-handling obligations must be resolved before transfer.
- **Consequences:** Default external-provider testing uses synthetic or approved de-identified fixtures.

## DEC-0007 - Official Semester 1 schedule is immutable

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** Lock the Semester 1 dates transcribed from `Senior_Project 2026_sem1_activities.pdf` into `project_state/official_deadlines.json`.
- **Rationale:** Planning buffers may move; faculty deadlines may not.
- **Consequences:** Corrections require a new official source, human approval, synchronized registry update, and a superseding decision.

## DEC-0008 - Planning-system ownership boundary

- **Date:** 2026-08-11
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** `project_state/` and `docs/` remain the sole authoritative record of deadlines, milestones, tasks, risks, decisions, approvals, contracts, and specifications. `.planning/`, introduced by the GSD toolchain, is a subordinate execution layer that owns phase sequencing and per-phase execution artifacts only. `.planning/` may reference an authoritative identifier such as `M1`, `TASK-0003`, or `RISK-0002`, but may never be the place where that item's status, scope, or definition lives. `.planning/REQUIREMENTS.md` is a derived index: every requirement must cite its source document, and any substantive change is made in the source first.
- **Rationale:** The repository now carries two vocabularies for the same work — `docs/project_management/` (M0-M9, TASK-XXXX, RISK-XXXX) and `.planning/` (Phase 1-7, REQUIREMENTS, STATE). Divergence has already occurred: `MILESTONES.md` M8 and `MASTER_PLAN.md` Phase 6 give different 4B release-candidate windows, and recording one Group Application status required editing five files by hand. Authority must sit with `project_state/` and `docs/` for two reasons. First, they are enforced — 199 harness checks and JSON Schema validation cover them, while `.planning/` had zero coverage when this decision was written. Second, `.planning/` is a third-party format owned by the `@opengsd/gsd-core` release cycle; installing it overwrote 71 skill files in one command, and a future update may change its structure. A project's source of truth may not depend on another project's upgrade path.
- **Consequences:**
  - `.planning/README.md` states this boundary at the point of use so future sessions and agents see it without reading this log.
  - `scripts/verify_harness.py` enforces the boundary: phase dependencies must resolve to real phases, requirement identifiers must map to a phase, and any `TASK-`/`RISK-`/`DEC-` identifier appearing in `.planning/` must exist in `project_state/`.
  - Deleting or regenerating `.planning/` must never lose project state. If it would, the boundary has been violated and the content belongs in `docs/` or `project_state/`.
  - Where the two disagree, `project_state/` and `docs/` win, and the `.planning/` artifact is corrected.
  - Accepted by the human owner on 2026-08-11 and in force from that date. Superseding it requires a new Decision Log entry, not an edit to this one.

## DEC-0009 - Approximately 27B replaces approximately 4B as the flagship target

- **Date:** 2026-08-26
- **Status:** accepted
- **Supersedes:** DEC-0002
- **Owner:** Phurinat Polasa
- **Decision:** Approximately 27B is the flagship target of the Research Track. The approximately 4B target is withdrawn and no longer appears as a project deliverable. Every gate that DEC-0002 attached to the 4B release candidate now attaches to the 27B release candidate, unchanged in substance: G0-G4 must close on recorded evidence, and a valid Tier 4 manifest plus explicit time-bounded human approval are required before any flagship run.
- **Rationale:** The flagship scale is the project owner's decision and was given directly on 2026-08-26 while the Project Idea document was being prepared for the immutable DL-0002 deadline. Recording it as a superseding entry keeps the submitted document consistent with the enforced record instead of leaving it contradicting a locked decision.
- **Consequences:**
  - RISK-0004 is restated against 27B and its probability raised to `CRITICAL`. Compute feasibility is now the dominant threat to the Research Track flagship.
  - The scope fallback ladder is unchanged and load-bearing. If compute cannot support stable 27B training, the delivered model is reported at its true scale and is never relabelled as approximately 27B.
  - Small-scale architecture validation before scaling is unchanged and still gates any flagship run. A larger target does not license skipping a gate.
  - Compute, storage, cost, and schedule impact must be re-estimated against 27B before any Tier 3 or Tier 4 request. No estimate carried over from 4B remains valid.
  - `docs/PROJECT_CHARTER.md`, `docs/research/RESEARCH_SPEC.md`, `docs/research/SUCCESS_CRITERIA.md`, `docs/research/TRAINING_SPEC.md`, `docs/project_management/MASTER_PLAN.md`, `docs/project_management/MILESTONES.md`, and the `.planning/` artifacts still name 4B. They must be reconciled before the Proposal Report on 2026-10-02.
- **Open concern recorded, not resolved:** approximately 27B is roughly a sevenfold parameter increase over the withdrawn target, against a risk register that already rated 4B compute feasibility `HIGH`. This decision records the owner's direction; it does not establish that the compute exists. The feasibility evidence is owed at the flagship gate.

## DEC-0010 - Python and FastAPI as the Clinical Front Door runtime

- **Date:** 2026-08-30
- **Status:** accepted
- **Owner:** Supreeya Nuamkhayan
- **Decision:** Implement the Clinical Front Door API, the Model Gateway and the shared contract runtime in Python with FastAPI. Contract models are Pydantic models bound to the JSON Schemas already in `schemas/`, which remain the machine source of truth. Provider SDKs stay inside gateway adapters per DEC-0003.
- **Rationale:** One language across the project. The Research Track is Python by necessity and `scripts/` is already Python. The five shared contracts exist as JSON Schema, and Pydantic binds to them directly, so the executable contract and the machine contract cannot drift into two separate definitions. A second language would mean maintaining contract models twice and syncing them by hand — exactly the drift RISK-0006 describes.
- **Alternatives considered:**
  - TypeScript with Node — better for a frontend-heavy project, but adds a second language and a second copy of the contract models.
  - Python with Django REST Framework — heavier than an API-first service with no admin or ORM requirement needs at this stage.
  - Defer and let the choice emerge from the first implementation — forbidden by GOV-01, and it is how architecture decisions become accidents.
- **Consequences:**
  - Phase 2 is unblocked: contract models, the mock provider and the ten contract fixtures can be written.
  - `shared/` holds the versioned Pydantic contract models; `schemas/` stays authoritative and the models are tested against the existing fixtures in `tests/fixtures/`.
  - Provider-specific types may not appear in Front Door business logic or in any client.
  - A dependency file and a virtual environment enter the repository for the first time. `scripts/` stays stdlib-only so `verify_harness.py` keeps running with no install step.
  - A browser UI, if later required, consumes the same API as any other client and does not reopen this decision.
- **Ordering constraint honoured:** recorded and accepted before any Phase 2 implementation file exists.

## DEC-0011 - Accept a non-commercial research-use ceiling on the open-weight release

- **Date:** 2026-08-30
- **Status:** accepted
- **Owner:** Phurinat Polasa
- **Decision:** Accept the ceiling. Released weights are for **non-commercial research use only**, and the candidate dataset set is not narrowed to avoid it. Every artifact describing the release — Proposal Report, Progress Report, model card, README, any publication — states the restriction explicitly instead of using the unqualified term *open-weight*. The term may still describe what it actually denotes, that the weights are published and inspectable, but never as an implied grant of unrestricted use.
- **Rationale:** This is an academic Senior Project; its deliverable is research evidence, not a commercial artifact, so a non-commercial licence costs nothing the project needs. Narrowing the candidate set to preserve commercial rights would cost real capability — dropping the MIMIC family removes the only patient-linked multimodal cohort, and dropping CT-RATE removes the only 3D CT source. Paying in evidence quality for a permission the project has no use for is a bad trade.
- **Alternatives considered:**
  - Restrict to permissively licensed data only — would leave VQA-RAD as effectively the sole source, removing patient linkage, longitudinal structure and 3D coverage.
  - Defer the release terms until release — would let the submitted document's unqualified claim stand through two more reports.
  - Release no weights, only code and evaluation artifacts — remains the RISK-0010 fallback, but is not warranted by the present evidence.
- **Consequences:**
  - An unqualified *open-weight* claim is now a **known inaccuracy**, not a pending detail. TASK-0008's retrospective review must list it for correction in the Proposal Report.
  - **RISK-0010 stays OPEN.** This decision does not settle whether PhysioNet permits releasing weights trained on MIMIC at all (TASK-0020), nor whether CT-RATE's ShareAlike term propagates to the released weights.
  - If TASK-0020 returns that PhysioNet does not permit a weights release, this decision does not authorise one anyway.
  - The release licence is chosen at the release gate, and must be at least as restrictive as the most restrictive contributing dataset.

## DEC-0012 - The literature registry is the single citation contract

- **Date:** 2026-09-02
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** Every external factual claim in any project document cites a `LIT-` identifier resolving to `project_state/literature.json`. Formatted references are generated from `citation.apa7` and never retyped. A reference may only be `ACCEPTED` when `verification.status` is `VERIFIED`, which requires a named primary-source method and date. A `CONFLICT` record may never be `ACCEPTED`.
- **Rationale:** The project maintained two independent reference lists — five entries in the submitted Project Idea and thirteen in the unsubmitted draft — with no machine-readable store and no way to tell a citation that had been checked from one written from memory. Re-verification on 2026-09-02 found a page range carried since August that no primary source confirms (LIT-0008); a prose bibliography could not have caught it. The dataset feasibility survey already proved the pattern works: schema, plus a `project_state` registry, plus a docs page, plus a harness check.
- **Alternatives considered:**
  - Keep citations as prose and rely on care at review time — rejected, because that is exactly the regime under which LIT-0008's unconfirmed page range survived five rounds of review.
  - Adopt an external reference manager and a `.bib` file — rejected, because it would sit outside `project_state/` and so outside DEC-0008's authority boundary and outside the harness.
- **Consequences:**
  - Reference lists in the Proposal and every later document are generated from one store.
  - `scripts/verify_harness.py` gains `check_literature`; the harness rises from 241 to 1123 checks.
  - An unverified citation cannot reach a project document without failing verification.
  - `docs/academic/PROJECT_IDEA.md` is **not** edited — it stays byte-identical to the signed PDF, and repayment lands in the Proposal.
- **Evidence:** `schemas/literature.schema.json` · `project_state/literature.json` · `docs/research/RELATED_WORK.md` · `check_literature` in `scripts/verify_harness.py` · 19 negative tests in `tests/test_literature_registry.py` · `scripts/verify_citations.py`, with 52 of 52 identifiers re-verified online on 2026-09-02.

## DEC-0013 - Accept the baseline shortlist and add two comparison arms

- **Date:** 2026-09-02
- **Status:** proposed
- **Owner:** Thanrada Tungweerapornpong
- **Decision:** Record comparison families 2, 3, 4 and 6 as `INTERNAL_CONTROL`, owing a published method precedent rather than a checkpoint. Add two arms to `docs/research/BENCHMARK_CONTRACT.md`: an **LLM-orchestrated agentic planner** over the same operator vocabulary, and a **fixed-route-set conditional model**. Leave families 1 and 5 `DEFERRED` until SRCH-0006 reports licence, weights and evaluation reproducibility.
- **Rationale:** Naming baselines materially changes public benchmark rules, which `CLAUDE.md` puts behind human approval. The two new arms exist because without them the two sharpest novelty threats are untested: if an LLM-emitted plan matches the trained compiler at equal compute the architectural claim is dead, and if a ten-route weighting on MIMIC matches a compiled DAG the topology claim collapses to a routing claim.
- **Alternatives considered:**
  - Keep the six abstract families and name nothing — rejected; an experiment plan that cannot name its baselines is not yet an experiment plan, and TASK-0009 is blocked on it.
  - Select Mixtral as the family 5 checkpoint — rejected on evidence: it makes no equal-compute claim, and at 13B active it cannot be matched to a 300–700M model.
  - Add no new arms — rejected; it leaves the project unable to answer its two strongest challenges.
- **Consequences:**
  - `BENCHMARK_CONTRACT.md` gains a named baseline candidates section and two comparison arms.
  - **Family 4 (random/shuffled routing) becomes the load-bearing experiment of the project**, not a sanity check — LIT-0034 reports hash and random-fixed routing within 1.1–2.2 perplexity of learned routing across 62 controlled runs.
  - Med-PaLM M and Med-Gemini are fixed as novelty-matrix columns and never baselines, their weights being unavailable.
  - The compute budget rises by two arms and must be re-estimated against TASK-0018.
- **Approval:** APR-0001 (`SCOPE_CHANGE`, `PENDING`) — the first entry in an approvals file that has been empty since the project began.

## DEC-0014 - The Front Door target is a deployable multi-user research service

- **Date:** 2026-09-02
- **Status:** proposed
- **Owner:** Supreeya Nuamkhayan
- **Decision:** Target a deployable multi-user service: settings from the environment, a versioned API surface, a single error envelope, structured logging with correlation ids and redaction, token authentication tied to the human-review gate, readiness gating on the safety rules, SQLite in WAL on a volume, and one container. It remains a RESEARCH PROTOTYPE: the banner, the mandatory human confirmation and the non-deployment boundary stay, and `PRODUCT_SPEC.md`'s exclusion of production clinical deployment is unchanged.
- **Rationale:** Deployability and safety are the same requirement in two places. The human-review gate rests on `reviewer_id`, which is a caller-supplied string; on a network that gate is decoration. Authentication is what makes it real, so hardening is not separable from the safety claim.
- **Alternatives considered:**
  - Stay a local demo — rejected: the owner asked for a usable system, and the defects found on 2026-09-02 (a broken audit sink, silently erased human reviews) were invisible precisely because nothing exercised the deployment path.
  - Go to a full platform with Postgres, OIDC and metrics — rejected as ceremony: the append-only guarantee is implemented as SQLite triggers, and porting them buys a new failure mode and no marks.
- **Consequences:**
  - The service refuses to start unauthenticated on a non-loopback address.
  - `/ready` gates traffic on the safety rule set: a Front Door without its rules must not take work.
  - One uvicorn worker, documented — the circuit breaker is per-process.
  - A deployment beyond loopback needs APR-0005 under the Human Approval Policy.
- **Evidence:** `innovation/config.py` · `innovation/api/errors.py` · `innovation/logging.py` · `build_router` and `create_app` in `innovation/api/app.py` · `tests/test_service_wiring.py`
- **Approval:** Pending — Supreeya Nuamkhayan (owner). This entry is proposed, not accepted.
- **Recorded in this document on 2026-09-16.** It was accepted into `project_state/decisions.json` on 2026-09-02 and never transcribed here, so the readable log jumped DEC-0013 to DEC-0016 for two weeks. The machine record is authoritative under DEC-0008; a readable log missing two of its entries is the failure `TASK_BOARD.md` already warns about in its own domain.

## DEC-0015 - Re-assessment at an unchanged decision point is idempotent

- **Date:** 2026-09-02
- **Status:** proposed
- **Owner:** Supreeya Nuamkhayan
- **Decision:** Request identity includes the snapshot checksum. An identical question already answered returns the answer already given, with its review history intact. A changed evidence set changes the checksum and is therefore a genuinely new question with a new recommendation.
- **Rationale:** A recommendation's identity was derived from journey and decision time alone, so re-assessing at the same instant built a fresh recommendation under the same identifier with an empty review history: a recommendation a clinician had confirmed silently reverted to unconfirmed, and `/recommendations/{id}/effective` flipped from 200 back to 409 with nothing raised. The natural keys were already deterministic; they were simply incomplete.
- **Alternatives considered:**
  - Require an `Idempotency-Key` header — rejected: it adds a client obligation to work around a server-side identity bug.
  - Refuse a duplicate assessment with 409 — rejected: re-reading a decision point is a normal clinical action, not a client error.
- **Consequences:**
  - A confirmed recommendation cannot be silently unconfirmed by a repeated request.
  - History no longer gains duplicate entries for the same question.
  - Recommendation identifiers change shape; nothing persists them across the change.
- **Evidence:** `assess` and `_build_request` in `innovation/frontdoor/service.py` · `tests/test_service_wiring.py::test_re_assessing_the_same_question_keeps_the_human_review`
- **Approval:** Pending — Supreeya Nuamkhayan (owner). This entry is proposed, not accepted.
- **Recorded in this document on 2026-09-16**, with DEC-0014, for the same reason.

## DEC-0016 - The evaluated care setting is adult non-trauma emergency-department first-contact triage

- **Date:** 2026-09-07
- **Status:** proposed
- **Owner:** Supreeya Nuamkhayan
- **Decision:** The evaluated setting is the **first-contact triage station of a hospital emergency department**, before physician assessment. Population: adults 18+, non-trauma, non-obstetric. Operator: a supervised triage nurse or intake staff member; confirmer: a clinician. **Arrival mode (walk-in vs ambulance) is a declared stratification variable recorded per case, not an inclusion criterion** — it becomes one only if a dataset survey verifies a source field for it. Two decision moments are evaluated:
  - **T0** — the earliest time at which a chief complaint *and* a first vital set both satisfy `available_at_time <= T0`. Derivable from the journey alone, and already what `REQUIRED_FRONT_DOOR_EVIDENCE` encodes in `innovation/gateway/safety.py`: the code defines T0, the contracts just now say so.
  - **T1** — the earliest time at which at least one result-class item (first laboratory result or first imaging report) satisfies `available_at_time <= T1`, **capped at T0 + 120 minutes**. A case with no result-class item by the cap is evaluated at the cap with the item recorded *not yet available*, never as normal. 60-90 minutes is a **reporting stratum, not the definition**.

  Every reported claim states which snapshot it was measured at. Explicitly out of scope: operating room, pre-operative assessment, anaesthesia, ICU management, ward deterioration, prehospital and field triage, consumer self-triage, paediatrics, major trauma.
- **Rationale:** ED first-contact triage is the only candidate setting that is simultaneously implied by the signed Project Idea, already built into the machine contracts (the patient-journey event enum leads with `CHIEF_COMPLAINT` and `TRIAGE_NOTE`), already present in the twelve fixtures, and measured by the declared primary safety metric. The two decision moments are the substantive part: `available_at_time` is the project's own differentiator, and a single snapshot cannot exercise it. LIT-0037 (Aegle) demonstrates per-case specialist activation for clinical intake on a real cohort but is text-only, with no typed operators, no export or replay, no imaging, no compute matching and **no `available_at_time` semantics**. This setting places the project beside that gap, which threat T8 requires any Front Door claim to do explicitly.
- **Alternatives considered:**
  - **Operating room, pre-operative assessment or anaesthesia** — rejected on evidence, not preference. Zero candidate datasets carry peri-operative data; the `event_type` enum has no `PROCEDURE`, `SURGERY`, `PREOP_ASSESSMENT`, `INTRAOP_VITAL` or `PACU` value; and MIMIC-IV `procedures_icd` is retrospective billing code, which `DATA_CONTRACT.md` forbids as an early-snapshot input. The literature survey also **never searched** peri-operative work, so under RELATED_WORK.md Rule 4 its silence is `NOT_REPORTED`, not `ABSENT` — the niche could not be claimed open without a new search first.
  - **ICU management or ward deterioration** — rejected: occupied by NEWS2 and LIT-0046, and not a front door.
  - **Consumer-facing self-triage** — rejected: occupied by LIT-0055 and contradicts `PRODUCT_SPEC.md`, whose user is a supervised triage nurse, not a patient.
  - **Outpatient multi-department intake** — rejected: this is precisely the setting LIT-0037 (Aegle) occupies across 24 departments, which would put the project *inside* threat T8 rather than beside it.
  - **Name no setting and keep deferring** — rejected: it is the status quo that produced an evaluation set which cannot discriminate and a novelty claim with an undefined domain.
- **Consequences:**
  - The claim boundary in `PROJECT_CHARTER.md` — "clinical claims beyond the evaluated population and setting" — gains a referent and becomes enforceable rather than a placeholder.
  - **RISK-0014 raised:** the product setting and the surveyed data setting do not match. **MIMIC-IV-ED is not a candidate dataset** — it appears once in the whole repository, as an unexecuted search string — so `CHIEF_COMPLAINT` and `TRIAGE_NOTE` currently have no recorded data source. RISK-0002 covers modality linkage, not setting mismatch.
  - The frozen case set must be rebuilt to exercise all four urgency levels and to carry a T1 snapshot, and EVAL-0001 re-run. **The escalation rate will change, and the change is a property of the case set, not a safety improvement.**
  - `schemas/dataset-feasibility.schema.json` gains a required `care_setting` object and all seven datasets are backfilled — closing the gap that let a seven-dataset survey record no setting while `DATA_CONTRACT.md` mandates population, site and time period at manifest time.
  - The project **accepts** threats T5 (LIT-0036) and T6 (LIT-0025) rather than moving off MIMIC, because MIMIC is the only corpus supporting patient-level multimodal linkage and time-valid snapshots. The trade is stated in the Proposal, not left implicit.
  - **No triage taxonomy is adopted**, and none may be without a licence review: ESI requires written ENA permission; ACS Field Triage explicitly forbids incorporation into AI/ML applications; ATS requires ACEM permission; CTAS is unresolved; MTS is licensable but no software implementation holds accreditation; NEWS2 is free but is a deterioration score, not a triage taxonomy. KTAS, JTAS and the Thai national ED triage scale were never read (SRCH-0005 `PARTIAL`).
  - **Naming a setting is not adopting a protocol.** `CLINICAL_WORKFLOW.md`'s prohibition on mapping to a real operational triage scale without authorized clinical validation stays in force verbatim.
  - **The comparison cohort and the committed setting are different populations.** DEC-0013's fixed-route-set arm runs on MIMIC-IV `hosp` + `icu` — a hospital course, not a first contact. No Front Door result may be reported on that data as if it were triage-point evidence, and every results table must name its population.
  - The setting is committed for the **contracts, product, safety screen and synthetic evaluation**, all of which are under project control. Any **dataset-backed** claim in this setting is conditional on DS-0008 and remains a hypothesis until surveyed.
  - **RISK-0015 raised.** Tracing the deterministic screen shows the evaluation cannot currently discriminate *at all*, and the cause is structural rather than a shortage of cases: SCR-002 raises `COMPLAINT_NOT_EVALUATED_BY_RULE` as `UNKNOWN` for every request carrying a chief complaint, and SR-002 turns any `UNKNOWN` flag into `URGENT_REVIEW` + `ESCALATED` — so **every complaint-bearing case escalates by construction, independently of its content**. The only route to `IMMEDIATE_REVIEW` is a `TRIGGERED` flag, and the only `TRIGGERED` flag produced anywhere is `REQUIRED_INFORMATION_INCOMPLETE`, so **the top urgency level is reachable only through absent information, never through clinical severity**; neither provider ever emits `TRIGGERED`. Adding `ROUTINE_REVIEW` cases therefore cannot make the set discriminate — it makes the failure visible and drives escalation toward 1.0. That is the intended next step (TASK-0032), with the fix designed and deliberately scheduled after the Proposal (TASK-0033).
- **Approval:** APR-0002 (`SCOPE_CHANGE`, `PENDING`). Sequenced **before or with** APR-0001 — that approval reframes the contribution as "an evaluation contribution in a domain the field has not entered", which is empty until the domain is named.
- **Evidence:** `docs/academic/PROJECT_IDEA.md` · `docs/innovation/CLINICAL_WORKFLOW.md` · `project_state/dataset_feasibility.json` · `project_state/literature.json` (LIT-0037, LIT-0036, LIT-0025, LIT-0055, LIT-0046, and the sole MIMIC-IV-ED mention) · `docs/research/RELATED_WORK.md` (T5, T6, T8; the triage-taxonomy licence audit; owner decision 6) · `tests/fixtures/cases/` · `docs/innovation/ACCEPTANCE_CRITERIA.md` (EVAL-0001 escalation 0.83).

## DEC-0017 - The Front Door is one central backend and two separate frontends

- **Date:** 2026-09-19
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** One backend process and one versioned `/v2` API. Two frontend entry points with separate bundles from the existing Vite project: `nurse.html` (voice intake and handoff, role `intake`) and `platform.html` (queue, physician review, facts, audit, trace, research, readiness, settings). Shared code lives only in `src/shared/`; neither app imports from the other, enforced by a test. Access is enforced by server role checks, never by client-side hiding.
- **Rationale:** `/platform` and `/nurse` are one bundle today, with the surface picked from `location.pathname` and pages hidden client-side. Research views render inside the clinical flow and queue-only fields are computed in the route handler. Separate bundles make the boundary visible; one backend avoids duplicating auth, audit and the safety screen.
- **Alternatives considered:**
  - Two npm packages — rejected: identical dependencies, double maintenance.
  - One bundle with separate routes — rejected: the current, confusing state.
  - Split the Python backend now — deferred to TASK-0034 and DEC-0014.
- **Consequences:** `/workspace` redirects to `/platform`; entry-point tests pin two HTML files; owners of each app are named on acceptance.
- **Evidence:** `docs/innovation/v2/baseline/` · TASK-0035 · TASK-0036
- **Approval:** Pending — Phurinat Polasa (PM), Supreeya Nuamkhayan (Innovation). This entry is proposed, not accepted.

## DEC-0018 - The Innovation product family is named Pratu

- **Date:** 2026-09-19
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** Product family **Pratu** (ประตู, "door"), described as a Clinical Front Door. **Pratu Core** is the central backend (API, Model Gateway, deterministic safety screen, audit); **Pratu Intake** is the nurse app at `/nurse`; **Pratu Console** is the physician and evaluator app at `/platform`. The assistant is "ผู้ช่วยรับข้อมูล" with no persona name. The Research model family's working name is **CaseGraph**, with a size suffix only at the scale actually trained. The official academic project title is unchanged.
- **Rationale:** The interface carried "Clinical Front Door", "JARVIS workspace" and a "Luna" persona at once. JARVIS is a third-party character name, and a persona contradicts the design system. One Thai name ties the three parts together; keeping "Clinical Front Door" as the descriptor preserves existing references.
- **Alternatives considered:** keep the generic names (JARVIS/Luna would remain); a triage-role name (implies the system triages, beyond the claim boundary).
- **Consequences:** UI, tests and mockups use Pratu Intake and Pratu Console. No trademark search has been done for "Pratu" or "CaseGraph"; do one before any public release.
- **Approval:** Pending — Phurinat Polasa (PM), Supreeya Nuamkhayan (Innovation), team. This entry is proposed, not accepted.

## DEC-0019 - Publish the redesign mockups as a public prototype for concept testing

- **Date:** 2026-09-21
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** Recompose the eight `.dc.html` screens in `docs/innovation/v2/mockups/project/` into one self-contained page and publish it as a shareable artifact, to be used as the stimulus for concept testing with OPD/ER physicians and triage nurses. Every screen carries the `ต้นแบบวิจัย · ข้อมูลสังเคราะห์` label, and the published page adds a persistent page-level banner because three of the eight screens (Before, Nurse-Mobile, Nurse-Tablet) never carried the in-screen badge.
- **Rationale:** Concept testing needs the participant to click real screens. The mockups could not be opened by anyone: each `.dc.html` loads `./support.js`, which does not exist in the repository, and the canvas recorded on TASK-0036 is private. The Figma file is not approved. Without a shareable artifact there is no stimulus, and the solution row of the portfolio stays untestable.
- **Alternatives considered:** ship the Figma link (rejected: unapproved by PM and team, and missing the audit/trace and mobile screens); add the missing `support.js` runtime to the repository (rejected: reimplements a canvas runtime to serve one review); screenshots only (rejected: cannot test the click-through that TC-01 to TC-05 depend on).
- **Consequences:** The product names from DEC-0018 go out on a public URL, and that decision records that no trademark search has been done for "Pratu" or "CaseGraph". The artifact is private on publication and must be shared deliberately with test participants, not broadcast. A published prototype is not evidence of validation: the Evidence Board solution rows stay `Untested` at confidence 1 until concept-test results exist.
- **Evidence:** `docs/innovation/v2/mockups/project/` (8 screens + canvas.json); published artifact https://claude.ai/artifact/36Xkw5XcLSTvy6Jdv1udbm; APR-0003.
- **Approval:** Granted for publication by Phurinat Polasa (APR-0003). Team review of the mockups themselves is still pending under TASK-0036.

## DEC-0020 - The Innovation product is named MedX (supersedes DEC-0018 if accepted)

- **Date:** 2026-09-23
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** The product is **MedX**, still described as a Clinical Front Door. The nurse app at `/nurse` and the physician and evaluator app at `/platform` carry the MedX name; the backend keeps its current module names. The assistant keeps no persona name. The Research model working name (CaseGraph) and the academic project title are unchanged.
- **Rationale:** The working build, the e2e tests and the Prototype V2 usability sessions already use MedX; one name across build, tests and user testing avoids participants seeing two brands.
- **Alternatives considered:** revert to Pratu (rejected by the owner on 2026-09-23 for the V2 test round).
- **Consequences:** DEC-0018 is superseded once this entry is accepted. The public showcase in `prototype/` and the DEC-0019 artifact still say Pratu and are not used as the V2 test stimulus. No trademark search has been done for "MedX"; do one before any public release.
- **Approval:** Pending — Phurinat Polasa (PM), Supreeya Nuamkhayan (Innovation), team. This entry is proposed, not accepted.

## DEC-0021 - OPD journey scope (intake → physician → pharmacy → passport → home) and agent harness

- **Date:** 2026-09-23
- **Status:** proposed
- **Owner:** Phurinat Polasa
- **Decision:** MedX extends from ED first contact to the adult OPD journey: care context `OPD_ADULT_GENERAL` is in scope alongside ED, which reopens the setting fixed by DEC-0016. Prescribing (`MEDICATION_ORDER`, `RETURN_PRECAUTION`) stays with physicians and dispensing (`DISPENSE`) with a new `pharmacist` role; the model neither prescribes nor dispenses and these records are excluded from its evidence snapshot (DEC-0005 unchanged). The journey stage is derived from recorded facts, not a new state machine. All data remains synthetic (DEC-0006 unchanged).
- **Approval:** Pending — Phurinat Polasa (PM), Supreeya Nuamkhayan (Innovation), team. This entry is proposed, not accepted.
