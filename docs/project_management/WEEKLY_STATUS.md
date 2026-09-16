# Weekly Status

## Week of 31 August - 6 September 2026

**Project health:** RED
**Reason:** `scripts/project_status.py` derives health from open critical-impact risks and active P0
tasks, and four critical-impact risks plus three P0 tasks are still open. The derivation is correct and
was not adjusted to look better. What changed this week is that the record now matches reality and the
schedule is honest: **no task is overdue**, and P0/P1 concentration is back inside the capacity rule.

### Next official deadline

- **CITI: 25 Sep 2026 — 26 days out, immutable.** Then Proposal Report 2 Oct, Proposal Presentation 8-9 Oct.
- DL-0002 Project Idea was **submitted and advisor-signed on 28 Aug 2026**, within the immutable deadline.

### This week's outcomes

1. **M1 closed on evidence.** The submitted, advisor-signed PDF is archived at
   `sources/2026-08-28_project_idea_submitted_signed.pdf` with its SHA-256 and signature metadata
   recorded in `docs/academic/SUBMISSION_RECORD.md`. Signature: Sansiri Tarnpradab, 28 Aug 2026
   13:48:54 +07:00, read from the file, not inferred.
2. **The repository was holding the wrong document.** What was submitted is a different draft from the
   one in the repository: 5 references instead of 13, no in-text citations, all five Thai member names
   filled in, different wording throughout. `docs/academic/PROJECT_IDEA.md` is now a transcription of
   what was actually submitted, verified character-identical to the PDF (6,473 Thai characters, exact
   sequence match). `make idea-docx` reproduces the submitted text exactly.
3. The 13-reference draft is preserved as `docs/academic/PROPOSAL_SOURCE_DRAFT.md`. Its verified
   citation work is the starting capital for the Proposal Report, so none of it was discarded.
4. **DEC-0009 propagated everywhere (TASK-0017).** `CLAUDE.md`, `.claude/rules/research.md`, the
   charter, RESEARCH_SPEC, SUCCESS_CRITERIA, TRAINING_SPEC, HUMAN_APPROVAL_POLICY, MASTER_PLAN,
   MILESTONES, TASK_BOARD and the `.planning/` artifacts now all name 27B. The MASTER_PLAN scope
   fallback ladder was rewritten rather than search-replaced: its old rung 5, "remove 27B work
   entirely", was incoherent once 27B became the flagship.
5. **G0 moved from one of five closed to four of five.** `project_state/contract_versions.json`
   registers all five shared contracts at 1.0.0; `HUMAN_APPROVAL_POLICY.md` carries a version header;
   `schemas/dataset-feasibility.schema.json` and `project_state/dataset_feasibility.json` exist. Both
   new state files are registered in `scripts/verify_harness.py` and were negative-tested — an invalid
   verdict value makes the harness fail, so the checks are real. Harness: 236 → **241 checks, passing**.
6. **Schedule re-planned honestly.** Eight tasks that had silently passed their due dates were re-dated
   against real capacity. TASK-0004 moved from Phurinat to Thanapol; TASK-0005 and TASK-0011 raised to
   P0. Workload concentration: **50% → 33%**, inside the 40% rule.

### Second pass, 30 August — feasibility answered and decisions closed

1. **TASK-0005 answered, not just seeded.** All seven candidates now carry a `CONDITIONAL` verdict with
   a named condition and cited evidence. Sources were read at the providers' own pages where possible;
   dimensions resolved only from secondary sources stay `UNVERIFIED` and say so.
2. **DS-0007 CT-RATE added.** The submitted document claims 3D CT; none of the six original candidates
   supplied it — BraTS is brain MRI. CT-RATE is the dataset behind Hamamci et al. (2026), which the
   submitted document already cites. Adding it closes the gap, at the cost of a CC-BY-NC-SA licence.
3. **Three findings that change the project, not just the record:**
   - Patient-level cross-modality linkage exists **only** inside the MIMIC family. A single-patient
     five-modality journey is not achievable from this candidate set. RISK-0002 → probability CRITICAL.
   - `available_at_time` must derive from **`storetime`, not `charttime`**. Using `charttime` would put
     future information inside the decision snapshot — the exact failure RISK-0003 exists to prevent.
   - **Every candidate except VQA-RAD is non-commercial**, CT-RATE is ShareAlike, and PhysioNet is silent
     on whether trained weights may be released. The open-weight promise faces a non-commercial ceiling.
     RISK-0010 → probability HIGH. TASK-0020 puts the weights question to PhysioNet in writing.
4. **G0 is closed** — five of five. The gate asked that feasibility be recorded; it is, negative findings
   included. Owner sign-off (TASK-0019) and the raised risks are tracked as residuals, not as an open gate.
5. **The harness now enforces the rule the survey rests on**: no dimension may claim `VERIFIED`, and no
   dataset may carry a verdict, without citing evidence. Negative-tested. 243 → **286 checks, passing**.
6. **DEC-0010 accepted: Python + FastAPI**, recorded before any Phase 2 file exists, as GOV-01 requires.
   TASK-0021 and TASK-0022 are open for the contract models and the mock provider.
7. **The two pending decisions are closed, both unfavourably, and recorded that way:**
   - Phase 1 CONTEXT **D-03 was NOT MET** — the Project Idea was written and submitted by one person.
     New **RISK-0011**: the Proposal Report is four times longer with more technical claims, and the same
     failure there costs proportionally more.
   - The Group Application receipt is **unrecoverable**. M0 closes on the owner's recollection with the
     limitation stated in the milestone itself. New **RISK-0012**: capture submission evidence at
     submission time, as was done for the Project Idea.

**What the Proposal Report now owes**, beyond what was already listed: the 3D CT claim needs CT-RATE or
narrowing; the open-weight claim needs qualifying against the licences; and the modality story must
distinguish linked-cohort evidence from unlinked-capability evidence rather than reporting one number.

### Third pass, 30 August — the Innovation track has running code

The repository had no implementation at all this morning. It now has the contract spine,
the gateway, the Front Door and an HTTP API, with 66 passing tests wired into the smoke test.

1. **Release decision recorded (DEC-0011).** The non-commercial ceiling is accepted:
   released weights are for non-commercial research use only, and the candidate set is not
   narrowed to avoid it. This is an academic project, so the licence costs nothing it needs,
   whereas dropping MIMIC or CT-RATE would cost the only patient-linked cohort and the only
   3D CT source. **An unqualified "open-weight" claim is now a known inaccuracy** for
   TASK-0008 to correct in the Proposal. RISK-0010 stays OPEN — TASK-0020 and the CT-RATE
   ShareAlike question are untouched by this.
2. **TASK-0021 contract models.** `shared/contracts/` binds Pydantic models to the JSON
   Schemas, which stay the source of truth. The round-trip test compares the emitted field
   set against the fixture, so the two contracts cannot drift apart quietly (RISK-0006).
3. **`shared/snapshot.py`** is the single implementation of the temporal rule. It reproduces
   the contract's worked example exactly and withholds `ev-003` — the final diagnosis sitting
   in the same file — from any decision made before 13:00.
4. **TASK-0022 gateway.** All ten contract cases from `MODEL_API_CONTRACT.md` pass. The
   temporal case uses a tripwire provider that fails the test if it is ever reached, so
   "blocked before the provider" is proven rather than asserted.
5. **Deterministic safety layer** (`safety-policy-v1`): a triggered red flag forces
   IMMEDIATE_REVIEW; an UNKNOWN flag escalates instead of reassuring; missing required
   evidence abstains instead of concluding. A parametrised test asserts urgency is **never
   lowered** from any provider proposal. These rules sit in the gateway, not in a provider,
   so swapping providers cannot change safety behaviour.
6. **TASK-0023 Front Door + TASK-0024 API.** Human confirmation is structural:
   `act_on()` raises until a reviewer confirms, and only CONFIRM or MODIFY count — rejecting
   is a decision not to act. Overrides preserve the original output. `GET /recommendations/
   {id}/effective` returns 409 until confirmed. Non-synthetic journeys are refused at 403.
7. **Innovation release stage 1 is complete**: `make demo` runs the whole flow offline with
   no network. Stage 2's mock-provider prototype now has its API to call.

**Honest limits of what was built.** The gateway routes evidence *references*, never
payloads, so the deterministic rules reason about which evidence types are present and what
the provider declared — not about clinical content. Every response says so in its
limitations. The mock provider is plumbing, not a clinical model, and never claims a red
flag is absent. Nothing here is validated against real data, and no dataset has been obtained.

### Fourth pass, 30 August — Innovation measured against its acceptance criteria

Measuring the morning's work against `ACCEPTANCE_CRITERIA.md` rather than against
intuition showed it passed **A0 only**. A0–A4 are now closed; A5 is blocked on there
being no model; A6 is end-of-project. 222 tests, harness 293 → **300 checks**.

**Three defects the measurement exposed, one of them in my own record.**

1. The contract suite was **not** parametrised over adapters, though TASK-0022's evidence
   and the README both said a future adapter would be certified by it unchanged. That was
   untrue when written. It is true now — `BaselineProvider` is a second real adapter and
   23 cases run per provider — and the record carries the original claim and its
   correction rather than a quiet fix.
2. The deterministic screen ran **only after** the provider. Workflow step 3 and A1 require
   it before learned inference. It now runs first, and a provider that tries to clear every
   flag cannot lower what the screen found.
3. The models were **looser than their schema** and would have accepted documents the
   contract rejects. Testing that valid fixtures pass constrains the acceptance surface and
   leaves the refusal surface free; constraint-parity tests now pin both.

That third pass also found a genuine contract conflict: `PATIENT_JOURNEY_SCHEMA.md`
documents an `outcomes` field that `patient-journey.schema.json` forbids. The code follows
the machine schema; **the discrepancy needs a human decision** and was not settled by
changing a contract unilaterally.

**Built:** intake distinguishing known / unknown / refused / not-yet-available; immutable
append; an adaptive interview that will not re-queue a declined question; structured
override reasons; a second adapter with config-only swap; enforced timeouts and a circuit
breaker; append-only SQLite whose triggers refuse UPDATE and DELETE; five accessible
screens; and a frozen 12-case evaluation.

**Verified rather than asserted:** contrast measured in a browser at 8.95:1 against a
4.5:1 requirement, 0 of 8 controls off the tab order; both providers driven live over HTTP
by changing one environment variable; an encounter recovered after a process restart.

**The number worth reading: escalation rate 0.83.** The system escalates five cases in six.
It is safe and close to useless. It is reported beside under-triage precisely because a
system that escalates everything scores perfectly on the primary safety metric. That is the
bar the case-adaptive model has to beat, and it is what the Innovation track can honestly
claim today.

**Two bugs found by writing tests that had not existed.** `_rehydrate` loaded the
recommendation history and then reset it, so a restart silently lost every prior
assessment. And the DAG explorer read its withheld-evidence list from the audit record,
which is always empty — the Front Door filters future evidence before the gateway ever
sees it. Both fixed; the first was confirmed by re-introducing it and watching the new test
fail.

### Not done, and owed

- **TASK-0005 is at REVIEW, not DONE** — evidence gathered, owner sign-off outstanding (TASK-0019),
  and the MIMIC access dimension cannot close before CITI and a human-signed DUA.
- **TASK-0004** novelty matrix, search protocol and baseline shortlist still do not exist. Required for DL-0004.
- **TASK-0006** clinical workflow and gateway feasibility, still not started.
- **TASK-0018** no compute estimate for 27B exists.
- **The Research track still has no code.** `research/` remains a README. The Case Graph
  Compiler, encoders and training pipeline are not started. This is now the whole gap.
- **No model exists.** The gateway's providers are a deterministic mock and a fixed-path
  baseline. Nothing here is evidence about medical capability and must not be presented as
  such. A5 cannot begin until there is a model to adapt.
- **The independent safety and integration review has not run.** It cannot be
  self-certified: those reviewers are read-only and must not judge work they wrote. It is
  the one A4 item still open.
- **The `outcomes` contract conflict is unresolved** and needs a human decision.
- The advisor contact path is still unrecorded.

### CITI is a data blocker, not just an academic one

MIMIC-family data is reached through PhysioNet credentialed access, which requires completed CITI
training. If that holds on verification, TASK-0011 is a prerequisite for the access dimension of
TASK-0005 — so a late CITI delays the data path, not merely a certificate. TASK-0011 is now P0 and
started. The licence, patient-linkage, temporal-validity and modality-coverage dimensions do not
depend on CITI and must proceed now regardless.

### What the 27B propagation did not settle

It made the documents consistent with an accepted decision. It did not establish that the compute
exists. Approximately 27B is roughly a sevenfold increase over the withdrawn target, against a register
that already rated 4B feasibility HIGH. RISK-0004 stays CRITICAL, and rungs 3 and 5 of the rewritten
fallback ladder — deliver a smaller model reported at its true scale, or drop the flagship run — remain
live until TASK-0018 produces numbers.

### Top risks

1. RISK-0004 compute feasibility at 27B — CRITICAL, no estimate exists.
2. RISK-0002 multimodal data feasibility — no dataset accepted, no dimension verified.
3. RISK-0008 academic writing absorbing technical capacity — three immutable deadlines in six weeks
   alongside the first real implementation work, which has not begun.
4. RISK-0003 temporal or patient-identity leakage.

### Human decisions — all three closed on 30 August

1. **TASK-0008** — answered: no internal review took place. D-03 recorded as NOT MET; RISK-0011 raised.
2. **Group Application receipt** — answered: unrecoverable. M0 closed with the limitation stated;
   RISK-0012 raised.
3. **Phase 2 runtime** — answered: Python + FastAPI, recorded as DEC-0010 before any code exists.

### Now awaiting a decision

- **The non-commercial ceiling on the release.** Is a weights release restricted to non-commercial
  research acceptable, or should the candidate set narrow to protect a freer release? This is a scope
  question about what the project promises, not a technical one (TASK-0019).
- **RISK-0004** is still CRITICAL with no compute estimate for 27B (TASK-0018).

### Next update protocol

Replace this section at weekly review with completed evidence, carry-over reasons, changed risks,
workload concerns, decisions, and the next seven-day plan. Do not report a task complete without its
referenced evidence.

---

## 2 September 2026 - TASK-0004 literature and novelty survey, wave 1

**The headline is adverse and is reported first.** The project's core computational pattern is not
novel. As of March 2026 the per-case dynamic workflow graph is a **named, surveyed research area**
(LIT-0031). Typed DAG execution with schema validation, determinism and full auditability is shipped
engineering practice (LIT-0035). Per-input graph generation is peer-reviewed prior art (LIT-0033).
Per-case adaptation in medicine is demonstrated in clinical intake (LIT-0037) and medical
decision-making (LIT-0038). **MedGemma 1.5 (LIT-0014) already holds the 27B scale, open weights, 3D
CT/MRI and longitudinal imaging simultaneously**, which removes breadth, scale and open weights as
differentiators.

Any Proposal sentence of the form *"we are the first to compile a per-case typed DAG"* would be false
as written. What survives is a **composite claim plus an evaluation contribution in a domain the
dynamic-workflow literature has not entered** — that survey confirms zero clinical applications and
names *structural credit assignment* an open problem, and across every system screened **not one
scored DEMONSTRATED on equal-compute evidence**. RISK-0013 is raised REALIZED. Reframing the claim is
a human decision requiring a Decision Log entry.

**C-02 resolved against the claim as written.** SRCH-0002 looked for evidence that existing systems
are uniformly fixed-path and found the opposite in the medical multimodal domain — the very domain
the project claims differentiation in. Restoring Han et al. (2022) would have weakened it, not
supported it: a TPAMI survey of dynamic networks exists because the field is large. Three defensible
replacement wordings are recorded; the choice is the owner's.

**The strict 2022-2026 window cost less than feared.** LIT-0040 supplies an in-window, peer-reviewed
definition of faithfulness and LIT-0041 a formal *graded* co-anchor, so RQ3 does not need a
project-internal definition. In-window replacements were found for Futoma 2020 and Wong 2021 — and
the Wong replacement (LIT-0046) is a better fit, being an emergency-department validation. What the
window still costs is the module-network method ancestry (Andreas 2016, Hu 2017), raised
independently by two searches; a narrow recorded exception is on the owner's list.

**Verification found a real defect in the existing citation set.** LIT-0008 (Bedi et al. 2025, *JAMA*)
has carried the page range 319-328 since 26 Aug. Crossref REST, DOI content negotiation and PubMed
E-utilities all return first page 319 and no end page. Recorded as `CONFLICT` and downgraded to
`CONDITIONAL` rather than corrected silently. Four further conflicts were raised: a BiomedGPT licence
contradiction, two arXiv identifier/date inconsistencies, and a three-fold disagreement between two
peer-reviewed under-triage rates that is almost certainly definitional — which is itself the finding.

**Safety consequence worth escalating.** LIT-0050, LIT-0051 and LIT-0052 together are evidence that
mandatory human confirmation — the project's principal safety control — is of unproven and possibly
negative reliability: a confident wrong AI suggestion drops expert accuracy from about 82% to about
46%, and a preregistered meta-analysis reports human-AI combination underperforming the better party
alone on decision tasks. `SAFETY_SPEC.md` should stop calling human confirmation a *mitigation* and
start calling it a *requirement whose effectiveness is itself an open evaluation question*. Safety
owner's call.

**State changes.** TASK-0004 to `REVIEW` (not `DONE`: `reviewed_by` is null by design, SRCH-0006 has
not run, SRCH-0005 is PARTIAL). TASK-0026 created for non-author sign-off, owned by Phurinat — the
first deliverable in this project with independent review built in rather than owed, which partly
answers RISK-0011. TASK-0027 created to hold the base-model decision. DEC-0012 and DEC-0013 recorded
`proposed`. **APR-0001 is the first entry in an approvals file that has been empty since the project
began.**

**Workload flag.** Thanapol Popit owns TASK-0004 (HIGH, 18 Sep) and TASK-0009 (HIGH, 20 Sep) back to
back, with TASK-0011 (CITI, P0) across both, and now TASK-0027. The mechanical work here was
delegable; the novelty judgement, the threat assessment and the shortlist rationale are not.

**Verification run:** `scripts/verify_harness.py` 1123 checks pass (was 241); `run_smoke_test.sh`
passes; 241 pytest tests pass including 19 new negative tests; `verify_citations.py --online`
re-verified 52 of 52 identifiers against Crossref, the arXiv API and PubMed.

**Still open from this work:** SRCH-0006 has not run, so **no baseline family has left `DEFERRED`**.
SRCH-0005 is PARTIAL and did not reach KTAS, JTAS or the Thai national triage scale. Twelve owner
decisions are listed in `docs/research/RELATED_WORK.md`.

---

## 7 September 2026 - the project commits to a care setting

**The project had been running a month with no committed care setting.** Not vague in one document —
absent everywhere: the advisor-signed Project Idea names "ด่านหน้าของโรงพยาบาล" only in background
prose, `CLINICAL_WORKFLOW.md` deliberately deferred the question, no schema carried a `care_setting`
field, and DEC-0001…DEC-0015 contained no decision about setting or taxonomy.

**DEC-0016 (proposed, APR-0002 pending): adult, non-trauma, emergency-department first-contact triage.**
Two decision moments — T0 when a chief complaint and a first vital set are both available, T1 when the
first result-class item arrives, capped at T0 + 120 minutes. Arrival mode is a recorded stratum, **not**
an inclusion criterion, because no surveyed dataset has a verified arrival-mode field and this project
does not write down inclusion criteria without sources. T1 is event-anchored rather than clock-anchored
because `available_at_time` derives from `storetime`, a non-trivial share of MIMIC rows carry
`charttime > storetime`, and nothing has been recorded about result turnaround in this setting.

**Ruled out on evidence, not taste.** Operating room, pre-op and anaesthesia: zero candidate datasets,
no `PROCEDURE`/`PREOP` event types, and `procedures_icd` is retrospective billing code the Data
Contract forbids as an early-snapshot input. The literature survey also **never searched**
peri-operative work, so its silence is `NOT_REPORTED`, not `ABSENT` — the niche could not be claimed
open without a new search. ICU and ward deterioration are occupied and are not a front door. Outpatient
multi-department intake is exactly where Aegle (LIT-0037) sits, which would put the project *inside*
threat T8 rather than beside it.

### Two findings that are worse than the decision they came from

1. **The data does not cover the setting the product was built for.** The surveyed cohort is MIMIC-IV
   `hosp` and `icu` — a hospital course. **MIMIC-IV-ED is not a candidate dataset**; it appears once in
   the whole repository, as an unexecuted search string. So `CHIEF_COMPLAINT` and `TRIAGE_NOTE` have no
   recorded data source, and under-triage cannot be measured on a cohort that was never triaged.
   RISK-0002 covers modality linkage, not setting mismatch — this was genuinely uncovered. **RISK-0014.**

2. **The evaluation cannot discriminate, and adding cases will not fix it.** Tracing the screen rather
   than trusting the plan: `SCR-002` raises `COMPLAINT_NOT_EVALUATED_BY_RULE` as `UNKNOWN` for *every*
   request carrying a chief complaint, and `SR-002` escalates any `UNKNOWN` — so **every
   complaint-bearing case escalates by construction, independently of its content**. The only route to
   `IMMEDIATE_REVIEW` is a `TRIGGERED` flag, and the only one produced anywhere is missing required
   evidence, so **the top urgency level is reachable only through absent information, never through
   clinical severity**; neither provider ever emits `TRIGGERED`. `under_triage_rate` is therefore 0.0 by
   construction and no metric records the opposite error. **RISK-0015, raised REALIZED.**

   This corrects the plan this work started from, which assumed adding `ROUTINE_REVIEW` cases would make
   the set discriminate. It will not: escalation will climb toward 1.0. That is now the *intended*
   outcome of TASK-0032 — make the failure visible and measured — with `over_triage_rate` frozen first,
   because `EVALUATION_CONTRACT.md` requires metrics frozen before results and adding one after seeing
   0.83 would be metric-shopping. The fix (TASK-0033) is deliberately scheduled **after** the Proposal.

**The case set was not rebuilt today, on purpose.** Rebuilding it before the metric is frozen and before
the mechanism was understood would have produced a number that moved for unexplained reasons.

### Landed

`care_setting` is a required dimension in `schemas/dataset-feasibility.schema.json` with all seven
datasets backfilled, and DS-0001 now carries `covers_evaluated_setting: NO` as a machine fact rather
than a sentence in a document. The harness enforces two rules — a `VERIFIED` care setting must cite
evidence, and a dataset may only claim to cover the evaluated setting on a `VERIFIED` basis — both
negative-tested. A seventh test pins RISK-0014 itself: it fails the day any dataset claims coverage, so
closing the gap requires deleting that test deliberately rather than a document quietly changing.

Propagated to `PROJECT_CHARTER.md`, `PRODUCT_SPEC.md`, `CLINICAL_WORKFLOW.md`, `SAFETY_SPEC.md`,
`DATA_CONTRACT.md`, `BENCHMARK_CONTRACT.md` and `ACCEPTANCE_CRITERIA.md` (A4 reopened as A4.1). The
highest-value edit is the Setting constraint paragraph in the benchmark contract: **no Front Door result
may be reported on `hosp`/`icu` data as if it were first-contact triage**, and DEC-0013's fixed-route-set
arm is setting-agnostic architecture evidence, explicitly not Front Door evidence.

`SAFETY_SPEC.md` gained an over-triage/alarm-fatigue hazard row, which the log had never carried — it
had under-triage but nothing penalising a system that escalates everything, which is precisely the 0.83
problem. It also now requires every under-triage figure to carry its operational definition (LIT-0048's
3.3% and LIT-0056's 10.7% disagree threefold in opposite directions and the disagreement is unresolved),
labels `false_reassurance_rate` a project-defined construct, and restates human confirmation as a
requirement of unproven effectiveness rather than a demonstrated mitigation.

**Not changed, deliberately:** the four abstract urgency levels; the prohibition on mapping to a real
operational triage scale (`git diff` shows zero deletions in that file); the twelve case fixtures,
byte-identical; EVAL-0001; the signed Project Idea. **Naming the room is not adopting the protocol** —
every instrument surveyed is closed or unresolved, and ACS Field Triage forbids AI incorporation outright.

**Verification:** harness 1123 → **1135 checks**, passing; **264 tests** (was 257), including 7 new
negative tests; smoke test passes; EVAL-0001 re-run unchanged at escalation 0.83; workload concentration
27%, inside the 40% rule.

**Awaiting a human:** APR-0002, and DEC-0016 itself, which is `proposed`. Its rationale is written so it
does not depend on APR-0001's outcome, so the two may be decided in either order.

## 16 September 2026 - the web system was finished and the record never said so

**Project health:** RED (`scripts/project_status.py`, unchanged derivation: 4 critical-impact risks,
2 P0 tasks open). **Next official deadline: CITI, 25 Sep 2026 — 8.7 conservative days, immutable.**

This entry exists because the question that started the day was "the web is not finished yet, is it?
we planned to finish this week." Both halves of that sentence turned out to be wrong, and the second
error is the expensive one.

### The web was already finished, and nothing in the record said so

Measured on HEAD before any change was made today: `verify_harness.py` 1,135 checks passed,
`pytest -q` 465 passed, `vitest` 7 passed, `tsc --noEmit` clean, and a `grep` for
`TODO|FIXME|NotImplementedError` across `innovation/` outside `node_modules` returned **nothing**.

And yet **no `TASK-` record tracked the v2 workspace at all.** `project_state/tasks.json` read
`updated_at: 2026-09-07T18:15`, nine days stale, predating the entire 12–14 Sep delivery, and this
file had no entry for the week the system was built. A team reading its own planning system would
have concluded the work had not started. That is the failure DEC-0008 exists to prevent, arriving
from the opposite direction than expected: not a document contradicting the machine record, but a
machine record that had simply stopped being written to.

**No source-of-truth document ever scheduled the web for this week.** `docs/innovation/v2/README.md`
calls 11–17 Sep a *review* week. `tasks.json` gives 14–20 Sep to TASK-0004, 0009, 0010, 0011, 0018
and 0029 — research, CITI and the Proposal. The feeling of being behind came from the absence of a
record, not from a slip.

### The finding that matters: two Front Doors, and the safety evidence was on the wrong one

Three greps over `innovation/v2/` returned zero hits each: `ModelGateway|SafetyPolicy`,
`red_flag|urgency`, and `audit`. The same greps over `innovation/workspace/src/` returned zero for
urgency and red flags.

So the interface `innovation/config.py:57` enables **by default**, and `QUICKSTART.md` calls the
primary one while naming `/ui/v2` a "recovery fallback", produced clinical drafts carrying **no
red-flag findings, no urgency floor, no uncertainty and no audit record.** The deterministic screen,
the no-downgrade merge, SR-001..006, the urgency taxonomy and the DAG explorer all exist and are
tested — in v1, behind `/ui`. `MODEL_API_CONTRACT.md` opens by requiring every provider to reach the
model through the Model Gateway; the default UI path did not.

This was invisible for a specific, correctable reason: **commit `8c1f601`, which delivered v2, did
not touch `ACCEPTANCE_CRITERIA.md`.** No criterion pointed at `/workspace`, so nothing could fail.
A0–A6 had been silently scoped to a system that was no longer the one users opened. **RISK-0016.**

### Landed

`SafetyPolicy.screen()` now delegates to `screen_evidence()`, which takes evidence *types* instead
of a `GatewayRequest`, and `innovation/v2/safety.py` translates a `CaseRevision` into that call.
**One implementation of SCR-001 and SCR-002, two callers** — not a second copy, which would drift.
v1 behaviour is unchanged and its 465 tests pass untouched.

`SafetyScreen` is attached to `ClinicalDraft`, deliberately **not** to `DraftContent`: `content` is
what a provider produces and what a physician `MODIFY` replaces, so a finding stored there would be
one a reviewer could overwrite, which is not a safety control. A test asserts a review body cannot
carry its own screen.

Evidence counts as present **by kind, not by whether the answer was known** — matching v1 exactly,
where `EvidenceRef` carries no intake state, so an asked-but-unknown vital already satisfies SCR-001.
Tightening that is a clinical rule change needing review, tests and a Decision Log entry under
`SAFETY_SPEC.md`. It must not arrive as a side effect of wiring a second caller, so it did not.

Two claim-boundary defects closed with it. The v2 banner said only "synthetic data"; it now carries
`RESEARCH PROTOTYPE — HUMAN REVIEW REQUIRED` and the non-deployment sentence, which
`innovation/ui/templates/base.html:86` has always had and A3.1 requires. And `ESCALATE`, accepted by
`ReviewDecision` since v2 shipped but never sent by any client, was reachable from nowhere while
reading as implemented; the review panel now offers it under the same reason requirement as `REJECT`.

`playwright.config.ts` hardcoded `/opt/anaconda3/bin/python3`, so the e2e suite ran on one
developer's machine and nowhere else. It now uses `${PYTHON:-python3}`.

The case-id field's `pattern` was `[A-Za-z0-9_-]+`, which **throws under the RegExp `v` flag**, so
Chrome had silently disabled that field's client-side validation. Verified in the browser after the
fix: the field now rejects a Thai name and a space while still accepting `demo-001`. The server-side
pydantic pattern was never affected, so this restored defence in depth rather than closing a hole —
but the guard that was dead is precisely the one that stops a real patient name being typed as a
case identifier.

### Corrected in the record, not in reality

- **TASK-0034** created retrospectively for the v2 workspace, with the evidence it already had.
- **TASK-0028** REVIEW → DONE, re-verified on HEAD.
- **TASK-0012..0015** BACKLOG → IN_PROGRESS. `docs/academic/PROPOSAL_SOURCE_DRAFT.md` carries drafted
  material with 13 references, each verified against a primary source. `BACKLOG` said no work existed.
- **DL-0002** `IN_PROGRESS` → `SUBMITTED`. The Project Idea was submitted and advisor-signed on
  28 Aug; the registry had said otherwise for 19 days. **No official date was changed**, and an
  attempt to add a `submission_evidence` note to that file was rejected by the schema and dropped
  rather than the schema loosened — that evidence belongs in `SUBMISSION_RECORD.md`, where it is.

### Not done, deliberately

**A0 and A3.5 do not hold on v2 and are recorded as `no` in the new per-criterion table.** v2 does
not route through the Model Gateway, and it has no audit record tying model version, provider
version, reviewer identity and overrides together. Closing either is a decision under DEC-0003, not
a defect fix, and it is TASK-0034's remaining scope. Until it is made, **no claim that the Clinical
Front Door satisfies A0–A4 may be made about `/workspace` without naming those two rows.**

A5 waits on a model — `research/` still contains only `README.md`. A6 is end-of-project. TASK-0033 is
scheduled after the Proposal by `ACCEPTANCE_CRITERIA.md`. No live provider or Thai ASR was tested;
none is configured and no paid call was made.

### Verification

Harness 1123 → 1135 → **1137 checks**, passing. **468 tests** (was 465), including three that fail if
the v2 screen call is deleted — checked by deleting it. Smoke test passes. Frontend quality gate:
vitest **9** (was 7), `tsc` clean, vite build, Playwright **8 passed** at 1440×900 and 768×1024 with
Axe reporting no critical or serious findings. Browser walkthrough on a case with a chief complaint
and no vital sign shows urgency floor `URGENT_REVIEW`, both red flags with their states in text, and
the missing `VITAL` named.

### Awaiting a human

**APR-0001 and APR-0002 are both still `PENDING`**, and they are now blocking: TASK-0029 cannot
close, and TASK-0032 depends on it. DEC-0014 and DEC-0015 were transcribed into
`docs/DECISION_LOG.md` today after two weeks in `decisions.json` alone; both remain `proposed` and
need their owner.

**CITI is the real deadline pressure and no one has produced evidence.** TASK-0011 is P0,
`risk_level: CRITICAL`, `evidence: []`, owned by all five members, internal completion 18 Sep,
immutable 25 Sep — and it gates PhysioNet credentialed access that TASK-0005 needs, so a late CITI
costs the data path, not only a certificate.
