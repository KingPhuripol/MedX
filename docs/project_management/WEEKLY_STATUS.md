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

### Not done, and owed

- **TASK-0005 is at REVIEW, not DONE** — evidence gathered, owner sign-off outstanding (TASK-0019),
  and the MIMIC access dimension cannot close before CITI and a human-signed DUA.
- **TASK-0004** novelty matrix, search protocol and baseline shortlist still do not exist. Required for DL-0004.
- **TASK-0006** clinical workflow and gateway feasibility, still not started.
- **TASK-0018** no compute estimate for 27B exists.
- **The Research track still has no code.** `research/` remains a README. The Innovation
  spine is built; the Case Graph Compiler, encoders and training pipeline are not started.
- **No model exists.** The gateway's only provider is a deterministic mock. Nothing in this
  work is evidence about medical capability, and it must not be presented as such.
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
