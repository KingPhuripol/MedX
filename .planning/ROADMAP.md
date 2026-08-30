# Roadmap: Case-Adaptive Medical Multimodal Model and AI Clinical Front Door

## Overview

The project starts from a true zero baseline: a verification harness, ten JSON schemas, six state
files, three fixtures, and twenty-three specification documents describing a system in which not one
line has been built. Seven phases carry it from that baseline to an authorized public release and a
rehearsed end-to-end demonstration.

Phases are bounded by the two forces that actually govern this project: the immutable academic
deadline ladder, and the cumulative research and acceptance gates in which a later gate cannot repair
an earlier integrity failure. Each phase therefore bundles both tracks and, where one falls inside
the window, the academic deliverable it must feed. Within a phase, Research and Innovation work
proceeds in parallel by owner — that is the shape DEC-0001 requires, one schedule and one integration
gate, and it is why the phases are not split into separate track chains.

The first four phases run against fixed calendar walls between now and 15 Dec 2026. The last three
run against planning-assumption windows in 2027 that are not official faculty dates and must never be
represented as such.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [~] **Phase 1: Governance Baseline and Project Idea** - Project Idea delivered and signed 28 Aug 2026; the G0 governance gate is still open (TASK-0016)
- [ ] **Phase 2: Executable Contract Spine and Proposal Defense** - Turn the shared contracts into runnable code behind a mock gateway, and defend the proposal on that evidence
- [ ] **Phase 3: Time-Valid Data Foundation and Supervised Front Door Alpha** - Audited patient-level splits, a replayable graph executor, and a supervised intake-to-human-review flow
- [ ] **Phase 4: Frozen Evaluation and Progress Gate** - Freeze the simulated case set, implement the metrics and the release veto, and report honestly at the December deadlines
- [ ] **Phase 5: Small-Model Architecture Gate and Cross-Track Integration** - Support or falsify the case-adaptive hypothesis at small scale, and serve the team model through the same contract as the mock
- [ ] **Phase 6: Flagship 27B Authorization, Training and Release Candidate** - Authorize approximately 27B on recorded evidence and human approval, or decline it and report the smaller outcome honestly
- [ ] **Phase 7: Final Integrated Release and Demonstration** - Ship an authorized reproducible release and a rehearsed demonstration that states its own limits

## Phase Details

### Phase 1: Governance Baseline and Project Idea
**Goal**: The project has a submitted, evidence-traceable Project Idea and a governance baseline solid enough for every later technical claim to rest on.
**Depends on**: Nothing
**Milestone**: M1 · **Deadline**: DL-0002 Project Idea, 28 Aug 2026 (immutable) · **Window**: 11-28 Aug 2026
**Requirements**: AC-01, RG-01, GOV-02, GOV-03
**Owners**: research-lead, data-governor-engineer, project-manager, documentation-agent
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. A reader of the Project Idea document (2-4 pages plus references) can trace every claim to a cited source or to a statement explicitly labelled hypothesis or planned work, and the document is delivered before 28 Aug 2026.
  2. Advisor identity and the Group Application submission evidence are recorded in project state from an authoritative source, with no field filled by inference.
  3. A reviewer opening the deadline registry sees either a transcription verified against a restored faculty source under `sources/`, or an explicit open risk with a named owner stating that the transcription is unverified.
  4. A reviewer can confirm the G0 gate closed: accepted research questions and claim boundary, five versioned shared contracts, a recorded dataset access/license/ethics feasibility inventory, working manifest validation with evidence lineage, and an accepted owner map.
**Plans**: TBD

**Notes**: RISK-0002 (no dataset supports all modalities linked at patient level) is the live threat to
criterion 4 — the feasibility inventory may legitimately conclude that a fallback is required, and
recording that honestly closes the gate. M1's kill condition applies: if core dataset, ethics, or
compute assumptions have no feasible path and no approved fallback, that is escalated to a human, not
planned around.

### Phase 2: Executable Contract Spine and Proposal Defense
**Goal**: The shared contracts stop being documents and become code a reviewer can run offline, and the proposal is defended on that running evidence rather than on intent.
**Depends on**: Phase 1
**Milestones**: M2, M3 · **Deadlines**: DL-0003 CITI 25 Sep 2026; DL-0004 Proposal Report 2 Oct 2026; DL-0005 Proposal Presentation 8-9 Oct 2026 (all immutable) · **Window**: 29 Aug - 9 Oct 2026
**Requirements**: AC-02, AC-03, AC-04, GOV-01, IA-01, IT-01, PD-03
**Owners**: innovation-lead, software-engineer, data-governor-engineer, documentation-agent
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. A reviewer can drive a valid synthetic Patient Journey through a versioned gateway request to a mock provider with no network access and receive a schema-valid response, while invalid, future-dated, or unauthorized evidence is refused with the correct error code and a safe audit record.
  2. The mock adapter passes all ten contract fixture cases, and any adapter added later is certified by running that identical suite unchanged.
  3. The seven-stage Innovation release ladder is accepted and recorded, its stage-1 synthetic CLI fixture and stage-2 mock-provider clickable prototype both run end to end, and the Front Door runtime choice behind them exists as an accepted Decision Log entry written before the code was.
  4. CITI evidence is recorded for all five members before 25 Sep 2026, the Proposal Report is delivered before 2 Oct 2026, and the Proposal Presentation is delivered within 8-9 Oct 2026.
  5. Every technical claim in the proposal cites an evaluation ID, a manifest, or a runnable artifact, or is written as a hypothesis, design goal, or planned work.
**Plans**: TBD
**UI hint**: yes

**Notes**: GOV-01 is a hard ordering constraint inside this phase, not a parallel task — the runtime
and framework decision must be accepted before the gateway or prototype is implemented, because a
material architecture choice requires a recorded Decision Log entry. RISK-0008 (academic writing
absorbing technical capacity) peaks here: three immutable deadlines in six weeks alongside the first
real implementation work. If the window compresses, expose it as risk and ship the minimum valid
deliverable — never move a date.

### Phase 3: Time-Valid Data Foundation and Supervised Front Door Alpha
**Goal**: A supervised user can carry a simulated case from intake to recorded human review, running on data whose patient-level splits and temporal validity have been independently audited and on a graph executor whose runs replay.
**Depends on**: Phase 2
**Milestone**: M4 · **Evidence freeze**: 20 Nov 2026 (internal, feeds DL-0006) · **Window**: 10 Oct - 20 Nov 2026
**Requirements**: RG-02, RG-03, IA-02, IA-03, IA-04, PD-01, PD-02
**Owners**: data-governor-engineer, model-architect, software-engineer, innovation-lead
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. An auditor running the data checks sees disjoint patient-level splits, `available_at_time` on every evidence and label item, preprocessing fitted on training data only, preserved missingness, and a dataset card stating population, exclusions, modality pairing, limitations, and permitted use — and any patient overlap or future evidence fails the run outright rather than being reported as a warning.
  2. A researcher can execute a typed graph, export it, replay it on the same versioned inputs and config within the declared tolerance, and trace the result to a valid manifest and artifact checksums; the fixed-path baseline pipeline and its evaluator run end to end.
  3. A supervised user can complete an intake that distinguishes known, unknown, refused, and unavailable information, sees the deterministic red-flag screen run before any learned inference, adds later evidence without rewriting history, reaches a dashboard separating urgency, pathway, information gaps, uncertainty, and critical categories, and cannot close the case without a recorded human confirm, modify, reject, request, or escalate action carrying a reason.
  4. An evaluator can swap between the mock and the baseline provider by configuration alone, and can force timeout, invalid schema, budget-exceeded, and unavailable-provider conditions and observe safe escalation with an idempotent retry path and no provider-native field reaching the client.
  5. A reviewer sees the research-prototype and human-review labels prominently, confirms that a learned low-urgency output cannot silently downgrade a deterministic red flag, finds the original model output immutable after a human override, and passes keyboard, contrast, focus, and non-colour-urgency accessibility checks.
**Plans**: TBD
**UI hint**: yes

**Notes**: This is the widest phase and the one most likely to need splitting at plan time — it carries
the first real dataset work, the first executor, and the product alpha simultaneously. RISK-0003
(leakage) is the phase-invalidating threat: a confirmed temporal or identity leak invalidates every
derivative and forces a rebuild from a new approved data version, so run `/data-audit` and
`/temporal-leakage-audit` before any evidence is frozen, not after. The unit, property, and contract
classes of IT-02 land here with the executor; the remaining classes complete in Phase 5.

### Phase 4: Frozen Evaluation and Progress Gate
**Goal**: Frozen, reproducible evidence exists for the Clinical Front Door, an executable veto can reject an unsafe candidate regardless of how complete it looks, and both are reported honestly at the December deadlines.
**Depends on**: Phase 3
**Milestones**: M5, M6 · **Deadlines**: DL-0006 Progress Report 4 Dec 2026; DL-0007 Progress Presentation 14-15 Dec 2026 (both immutable) · **Window**: 21 Nov - 15 Dec 2026
**Requirements**: AC-05, AC-06, IA-05, IA-08
**Owners**: evaluation-scientist, documentation-agent, project-manager
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. A frozen simulated case set covering multiple disease systems, urgency levels, missingness, contradiction, and provider failure is locked before any final result is inspected, and the critical-case sensitivity, under-triage, false-reassurance, pathway, next-information, calibration and abstention, timing, and human-override metrics are implemented and reported with patient-level uncertainty intervals.
  2. Independent safety and integration reviewers — neither of whom implemented the work under review — issue verdicts from the `PASS`/`CONDITIONAL_PASS`/`FAIL`/`CRITICAL_FAIL` vocabulary, and no unresolved `CRITICAL_FAIL` remains.
  3. Running the release-gate check against a candidate returns a reject verdict whenever any rejection condition is present — autonomous clinical action, unapproved real-patient external transfer, confirmed leakage, hidden red-flag suppression, a path completing without human review, rendered invalid provider output, or an unresolved `CRITICAL_FAIL` — regardless of how complete the feature set is.
  4. The Progress Report is delivered before 4 Dec 2026 and the Progress Presentation within 14-15 Dec 2026, each reporting deviations, failures, and negative results alongside successes, with every claim citing the evaluation IDs and manifests that support it.
**Plans**: TBD

**Notes**: The freeze in criterion 1 is a one-way door — question, cohort, snapshot, metric,
comparison, and exclusion are recorded before results are seen, and any later change requires an
amendment explaining why and reporting both analyses. RISK-0007 (false reassurance or critical
under-triage) is what criterion 2 exists to catch; a critical safety failure overrides aggregate
performance no matter how good the headline numbers are.

### Phase 5: Small-Model Architecture Gate and Cross-Track Integration
**Goal**: Small-scale evidence either supports or falsifies the case-adaptive hypothesis before any expensive scaling is proposed, and the team model is reachable through the same contract the mock provider uses.
**Depends on**: Phase 4
**Milestone**: M7 · **Window**: Jan - Feb 2027 (planning assumption, not an official date)
**Requirements**: RG-04, RG-05, IA-06, IT-02
**Owners**: model-architect, training-engineer, evaluation-scientist, research-lead
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. Executed graphs demonstrably vary with predeclared case, task, modality-availability, and temporal attributes beyond seed noise, with no all-node, single-route, single-operator, or unavailable-modality collapse, and without variation being driven primarily by patient, site, or file identifiers.
  2. At matched data, splits, tokens or steps, optimization opportunity, seeds, search budget, and compute, the dynamic typed DAG is compared against strong fixed-path, same-backbone fixed-path, static typed DAG, and random or shuffled-router controls, and the outcome — including a negative one — is reported with effect sizes, patient-level intervals, and documented compiler overhead.
  3. Node, edge, operator, modality, and graph-swap interventions change outputs in the predicted direction often enough to support the scoped faithfulness claim, and replay agreement meets the declared tolerance.
  4. All seven architecture test classes — unit, property, contract, intervention, robustness, performance, and integration — run and pass.
  5. An evaluator can point the Front Door at the team model by configuration alone, watch the identical ten-case fixture suite pass, read `model_version`, `contract_version`, and `graph_schema_version` in the interface, and inspect the executed typed graph in the explorer with no hidden chain-of-thought exposed.
**Plans**: TBD
**UI hint**: yes

**Notes**: This phase owns the seven kill tests, and **stopping or reframing here is a valid research
outcome** — do not scale while any kill condition persists after the predeclared remediation budget.
A negative RG-05 result reported honestly satisfies this phase; a positive result manufactured by
tuning on the final test does not. IA-06 is placed here deliberately, ahead of scaling, because early
cross-track integration is the control for RISK-0006 (contract drift) and because the gateway path
must be proven before the schedule is committed to a 27B run. Reframing the research claim requires
human approval and a Decision Log entry.

### Phase 6: Flagship 27B Authorization, Training and Release Candidate
**Goal**: Approximately 27B training is either authorized on recorded evidence with explicit human approval and carried to a release candidate, or is explicitly declined in favour of a smaller outcome reported for exactly what it is.
**Depends on**: Phase 5
**Milestone**: M8 · **Window**: Feb - Apr 2027 (planning assumption; see Open Questions — MILESTONES.md and MASTER_PLAN.md give different windows and neither has been chosen)
**Requirements**: RG-06, RG-07, RG-10
**Owners**: training-engineer, model-architect, evaluation-scientist, research-lead
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. No approximately 27B run starts until a reviewer can see the G0-G4 gates closed, a valid Tier 4 manifest, a compute/cost/storage estimate, a hardware reservation, explicit stop criteria and a rollback plan, a schedule-impact statement showing no threat to academic deliverables, data volume, quality, and license permitting the intended training and release, and a specific time-bounded human approval that no agent granted.
  2. A small-scale rehearsal of the same recipe shows stable loss, stable routing, a working checkpoint save/load/resume cycle, and a working evaluation before any full run is requested — and every run's completion record carries terminal status, hashes, actual compute, artifacts and checksums, metrics, and exclusion reasons rather than a job exit code.
  3. Base and derived checkpoints carry complete lineage and verified checksums, and every reported number traces to a manifest, an immutable data and split version, a code revision, a config hash, a seed, an environment lock, and an output artifact.
  4. Frozen medical and architecture evaluations complete with valid statistics, safety, calibration, robustness, subgroup, contamination, and limitations analyses are published, the model is servable through the stable Model API Contract, and independent integration and clinical safety verdicts carry no unresolved critical failure.
  5. If scaling is declined or fails, the resulting smaller open-weight model is reported as exactly that — the scale shortfall stated plainly, never relabelled as approximately 27B — and its validity still rests on closed G0-G4 gates, product integration, data and safety integrity, honest limitation reporting, and reproducibility.
**Plans**: TBD

**Notes**: Every Tier 3 and Tier 4 run in this phase is an approval gate, never an automatic step:
more than one GPU, any multi-node or scheduled cluster job, any expected runtime over 60 minutes, and
any material paid compute each require their own specific recorded approval, and approving one run
does not approve its successor. RISK-0004 (compute cannot support stable 27B training, now CRITICAL) is the reason
criterion 5 exists — the fallback is a planned outcome with its own success definition, not a failure
state. Routing collapse triggers graph diagnostics and a stop, never a hope that more scale resolves
it.

### Phase 7: Final Integrated Release and Demonstration
**Goal**: The project ships an authorized, reproducible public release and a rehearsed end-to-end demonstration that states its own limits out loud.
**Depends on**: Phase 6
**Milestone**: M9 · **Window**: Apr - May 2027 (planning assumption, pending official faculty dates)
**Requirements**: RG-08, IA-07
**Owners**: documentation-agent, innovation-lead, software-engineer, project-manager
**Required reviewers**: clinical-safety-reviewer, integration-auditor
**Success Criteria** (what must be TRUE):
  1. An audience watches at least one evolving patient journey run from intake through recorded human review, plus an urgent escalation, a missing-information abstention, and a provider failure, with mock, baseline, and team providers compared without a single client or interface change.
  2. The presentation states the non-deployment boundary and the evaluated limitations explicitly, and describes the system only as supporting, assisting, or suggesting for review — never as diagnosing, treating, prescribing, referring, or discharging.
  3. A primary demonstration and a network-free offline backup demonstration are both rehearsed, and a third party can reproduce the demonstrated outputs from the archived instructions, fixtures, versions, and expected outputs.
  4. `/hf-release-check` passes with no secrets, PHI, prohibited dataset content, or unlicensed derivative; usage limitations and the research-only decision-support boundary are prominent; the release version is immutable and reproducible from approved artifacts; and a human explicitly approves publishing.
**Plans**: TBD

**Notes**: Publication is an approval gate — no upload, model or data card publication, public push,
or release tag happens without a recorded approval, and changing a published artifact afterwards
requires another. RISK-0010 (license or sensitive-artifact breach) is what criterion 4 exists to
catch. The release veto from Phase 4 runs one final time here before anything leaves the repository.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Governance Baseline and Project Idea | -/TBD | Partially delivered — Project Idea submitted; G0 gate still open | - |
| 2. Executable Contract Spine and Proposal Defense | 0/TBD | Not started | - |
| 3. Time-Valid Data Foundation and Supervised Front Door Alpha | 0/TBD | Not started | - |
| 4. Frozen Evaluation and Progress Gate | 0/TBD | Not started | - |
| 5. Small-Model Architecture Gate and Cross-Track Integration | 0/TBD | Not started | - |
| 6. Flagship 27B Authorization, Training and Release Candidate | 0/TBD | Not started | - |
| 7. Final Integrated Release and Demonstration | 0/TBD | Not started | - |

## Deadline Ladder

Immutable, Asia/Bangkok. Never moved, compressed, or reinterpreted by planning.

| ID | Deliverable | Deadline | Phase | Status |
|----|-------------|----------|-------|--------|
| DL-0001 | Group Application | 14 Aug 2026, 23:55 | — | Submitted (M0 complete) |
| DL-0002 | Project Idea | 28 Aug 2026 | Phase 1 | Submitted 28 Aug 2026, advisor-signed (M1 complete) |
| DL-0003 | CITI | 25 Sep 2026 | Phase 2 | Pending |
| DL-0004 | Proposal Report | 2 Oct 2026 | Phase 2 | Pending |
| DL-0005 | Proposal Presentation | 8-9 Oct 2026 | Phase 2 | Pending |
| DL-0006 | Progress Report | 4 Dec 2026 | Phase 4 | Pending |
| DL-0007 | Progress Presentation | 14-15 Dec 2026 | Phase 4 | Pending |

Phases 5-7 carry planning-assumption windows only. They are not official faculty dates and must never
be presented as such.

## Milestone Mapping

| Milestone | Phase | Note |
|-----------|-------|------|
| M0 Group and repository control | — | Complete; DL-0001 submitted (confirmed by human owner) |
| M1 Project Idea | Phase 1 | |
| M2 Ethics and proposal foundation | Phase 2 | |
| M3 Proposal Presentation | Phase 2 | Folded with M2 — splitting would create a one-week phase |
| M4 First integrated evidence | Phase 3 | Evidence freeze 20 Nov 2026 |
| M5 Progress Report | Phase 4 | |
| M6 Progress Presentation | Phase 4 | Folded with M5 — same two-week window |
| M7 Small-model architecture gate | Phase 5 | |
| M8 Approximately 27B release candidate | Phase 6 | Window unresolved — see Open Questions |
| M9 Final integrated release | Phase 7 | |

## Open Questions

Carried forward unresolved. None blocks Phase 1. Each needs a human decision, not an agent guess.

1. **27B release-candidate window is ambiguous (WARN-03).** `docs/project_management/MILESTONES.md`
   M8 says Mar-Apr 2027; `docs/project_management/MASTER_PLAN.md` Phase 6 says Feb-Mar 2027. Both sit
   at equal precedence, so precedence cannot resolve it and **no winner has been picked**. Phase 6
   records the union (Feb-Apr 2027) so neither variant is silently discarded. Resolve before Phase 6
   planning by reconciling the two documents or confirming the overlap is intentional (scaling
   completes Feb-Mar, the RC gate closes Mar-Apr). Adjacent milestones M7 and M9 are consistent and
   need no action.
2. **Advisor identity is unrecorded (WARN-02, remaining half).** Tracked as GOV-03 in Phase 1. No
   name may be inferred or invented by any system or agent.
3. **Deadline transcription is unverified (WARN-01).** The source PDF
   (`Senior_Project 2026_sem1_activities.pdf`) is absent from `sources/` and machine state records
   `transcription_status: PENDING_VISUAL_VERIFICATION`. This is a provenance gap, not a date
   conflict — the seven dates agree across all three places they appear and remain binding. Tracked
   as GOV-02 in Phase 1.
4. **Requirement count discrepancy in the intel — RESOLVED.** `.planning/intel/SYNTHESIS.md`
   originally reported "21 requirements", but `.planning/intel/requirements.md` contains 23
   `## REQ-` entries and SYNTHESIS.md's own per-group listing sums to 23 (8 Innovation + 10
   Research + 5 product and integration). This roadmap uses 23 as the true extracted count. No
   requirement was dropped — the headline was a miscount, and it has been corrected at source in
   SYNTHESIS.md. No action outstanding.
5. **Front Door runtime is deliberately unchosen.** By the human owner's instruction, no stack has
   been assumed anywhere in these artifacts. GOV-01 schedules the decision as explicit Phase 2 work,
   ordered before any Front Door or gateway implementation.
