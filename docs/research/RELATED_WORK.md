# Related Work, Novelty and Baseline Feasibility

**Owner:** Thanapol Popit · **Task:** TASK-0004 · **Sign-off:** TASK-0026 (not yet done)
**Machine record:** `project_state/literature.json` (validated by `scripts/verify_harness.py`)
**Schema:** `schemas/literature.schema.json` · **Online re-check:** `make citations-online`
**Status as of 2026-09-02:** six searches run, 58 references recorded — 40 `ACCEPTED`, 17 `CONDITIONAL`,
1 `UNDER_REVIEW`. Every identifier was re-verified by the main session against Crossref, the arXiv API
or PubMed E-utilities. **No baseline family is resolved and nothing is signed off** — `reviewed_by` is
null on every record by design.

> ## The finding, stated first
>
> **The project's core computational pattern is not novel.** As of March 2026 the per-case dynamic
> workflow graph is a *named, surveyed research area* with an accepted vocabulary (LIT-0031). Typed
> DAG execution with schema validation, determinism and full auditability is shipped engineering
> practice (LIT-0035). Per-input graph generation is peer-reviewed prior art (LIT-0033). Per-case
> adaptation in medicine is demonstrated in clinical intake (LIT-0037) and medical decision-making
> (LIT-0038). One preprint asserts all three of the project's headline axes in a single sentence
> (LIT-0032).
>
> **Any Proposal sentence of the form "we are the first to compile a per-case typed DAG" would be
> false as written.** What survives is a *composite claim plus an evaluation contribution in a domain
> the dynamic-workflow literature has not entered* — see §Novelty threats and §What survives.
>
> Reframing the contribution is a human decision requiring a Decision Log entry
> (`RESEARCH_SPEC.md`: "Stopping or reframing is a valid research outcome").

## Why this exists

TASK-0004's blocker states it plainly: *"the novelty matrix, the documented search protocol and the
baseline shortlist do not exist and are all required for DL-0004."* The project has had citations
since 2026-08-26. What it has never had is a **reproducible protocol**, a **matrix** saying how the
proposal differs from its nearest prior work, and a **named baseline shortlist**.

TASK-0004 blocks TASK-0009 and TASK-0010, which block TASK-0012. DL-0004 (Proposal Report,
2 Oct 2026) is immutable.

## Rules this survey works under

1. **No citation from memory.** Every `ACCEPTED` record names the primary source it was checked
   against and the date. The harness refuses `ACCEPTED` without `verification.status: VERIFIED`.
2. **The formatted string is generated, never retyped.** `citation.apa7` is generated from the
   Crossref or arXiv fields. The harness asserts the recorded year and DOI appear inside it.
3. **A disagreement with the source is a `CONFLICT`, and a `CONFLICT` may not be `ACCEPTED`.**
   Applied five times below, starting on day one with LIT-0008.
4. **`NOT_REPORTED` is not `ABSENT`.** Only the source itself can put a cell at `ABSENT`. Six cells
   in the matrix are `ABSENT` and each quotes the source denying the capability.
5. **Rejected and conditional records stay in the file.** The excluded-candidate list is part of the
   deliverable.
6. **A negative result is a result.** The headline above is the survey's main finding and it is
   adverse to the project. It is reported first rather than buried.
7. **Recording is not deciding.** Naming a baseline, adopting a triage taxonomy, choosing a base
   model and rewording a claim are all human decisions. See §What remains for the owner.

## The date window, and what it cost

The owner set a **strict 2022–2026 window**. Work outside it is recorded as `REJECTED` with
`excluded_reason: "outside owner-mandated window 2022-2026"` — recorded, not omitted.

**The feared cost did not materialise.** The worry was that rejecting Jacovi & Goldberg (2020) would
leave RQ3 with no citable definition of faithfulness. SRCH-0004 found an in-window, peer-reviewed
definition in *Computational Linguistics* (**LIT-0040**), with a formal *graded* co-anchor
(**LIT-0041**) whose gradedness is what licenses a threshold claim at gate G4 rather than a binary
one. **The project does not need to declare its own working definition.** In-window replacements were
also found for Futoma et al. 2020 (**LIT-0047**) and Wong et al. 2021 (**LIT-0046** — and the
replacement is a better fit, being an emergency-department validation rather than an inpatient one).

**What the window does still cost:** Andreas et al. (2016) *Neural Module Networks* and Hu et al.
(2017) *End-to-End Module Networks* are the true method ancestors of the Case Graph Compiler — a
layout policy predicting a per-instance network assembled from typed modules, nine years earlier.
Two independent searches raised them unprompted. Both are rejected on date alone. *"We did not cite
it because it is from 2017"* is a weaker position at a defence than citing it and stating the
difference. **A narrow, recorded exception for method-ancestry citation is on the owner's list.**

## Search protocol

Six searches, each recorded in `project_state/literature.json` under `searches[]` with its exact
question, the queries actually run, sources consulted, window, criteria, run date, executor and the
number of candidates screened. SRCH-0001…0005 ran in parallel on 2026-09-02; SRCH-0006 is pending.

| ID | Question | Screened | Yielded | Status |
|---|---|---|---|---|
| SRCH-0000 | *(reconstructed)* Which primary sources support each pillar of the Project Idea argument? | 19 | 13 | Complete; `RECONSTRUCTED` — its queries were never written down |
| SRCH-0001 | Which medical multimodal generalist models 2022–2026 report weights, scale, modality set and evaluation, and which handle longitudinal or 3D evidence? | 34 | 10 | Complete |
| SRCH-0002 | What is the state of conditional and sparse computation, and what evidence exists **at matched compute**? | 58 | 7 | Complete |
| SRCH-0003 | Does prior work compile a **per-case, typed, dynamic DAG**? | 95 | 9 | Complete — **the decisive search** |
| SRCH-0004 | What evidence exists that an exported graph is or is not causally faithful, and what intervention protocols are established in-window? | 95 | 8 | Complete |
| SRCH-0005 | What are the established triage taxonomies and their licence terms, and what evidence quantifies under-triage, false reassurance and calibration failure? | 95 | 11 | **PARTIAL** — hit its turn limit; see §Gaps |
| SRCH-0006 | For each of the six comparison families, which named systems have public weights, runnable code, a research-compatible licence and a reproducible published evaluation at a matchable scale? | — | — | **Not yet run** |

**SRCH-0000 is recorded `RECONSTRUCTED`.** Its selection policy, verification provenance and cut list
survive in `PROJECT_IDEA_CLAIMS.md`, but its queries were never written down and cannot be
reconstructed. The registry says so rather than inventing them; the harness requires a
`RECONSTRUCTED` record to explain itself and forbids a `RECORDED` one from using the same escape.

## Novelty matrix

Nine axes as rows; the seven closest systems as columns. The last column is **claimed, not
demonstrated** — `RESEARCH_SPEC.md` §Contribution boundaries permits nothing else.

**D** = DEMONSTRATED · **P** = PARTIAL · **A** = ABSENT (the source denies it) · **NR** = NOT_REPORTED
(the source is silent — *not* evidence of absence).

| Axis | MedGemma 1.5 `LIT-0014` | Med-PaLM M `LIT-0016` | Flex-MoE `LIT-0025` | Multimodal Routing `LIT-0036` | MaAS `LIT-0033` | GraphBit `LIT-0035` | Aegle `LIT-0037` | **This project (claimed)** |
|---|---|---|---|---|---|---|---|---|
| Medical multimodal breadth | **D** | **D** | P | **D** | NR | NR | P | claimed |
| Longitudinal / 3D | **D** | NR | P | P | NR | NR | NR | claimed |
| Conditional / sparse computation | NR | NR | **D** | **D** | **D** | NR | **D** | claimed |
| **Dynamic graph topology** | NR | NR | P | **A** | **D** | **A** | P | claimed |
| **Typed operators** | NR | NR | NR | NR | NR | **D** | NR | claimed |
| **Graph export / replay / intervention** | NR | NR | NR | P | NR | **D** | NR | claimed |
| Case-level adaptation | NR | NR | **D** | **D** | **D** | **A** | **D** | claimed |
| Equal-compute evidence | P | P | NR | **A** | P | NR | P | claimed |
| Clinical Front Door use | P | NR | NR | NR | NR | NR | **D** | claimed |

Every cell resolves to a `basis` string in `novelty.positions` naming where it was read. The six
`ABSENT` cells each quote the source: Multimodal Routing routes weight over a fixed enumeration of ten
routes and reports no compute parity; GraphBit's DAG is authored by a user before execution, not
generated per input.

**Read the matrix down the columns, not across.** No single system holds more than three of the four
graph axes, but **no axis is unoccupied**. The differentiation is a *combination*, and a combination
claim is weaker than a mechanism claim.

The axes map onto the comparison families deliberately, so the novelty argument and the experiment
plan are the same argument: conditional/sparse ↔ family 5; dynamic graph topology ↔ families 3 and 4;
case-level adaptation ↔ family 2; equal-compute evidence ↔ the matching rule in
`BENCHMARK_CONTRACT.md` §Freeze protocol.

## Novelty threats

Each row is a specific way an examiner says *"this already exists."*

| # | Prior work already does this | What the project would still be claiming | What would settle it | Severity |
|---|---|---|---|---|
| T1 | **LIT-0014 — MedGemma 1.5** is an open-weight medical multimodal family at **27B**, already handling 3D CT/MRI, prior-image comparison and EHR as of Jan 2026 | Nothing on breadth, scale, or open weights. **Those are no longer differentiators.** The claim must move onto the four graph axes | Nothing to test. Rewrite the positioning | **CRITICAL** |
| T2 | **LIT-0031** — the pattern is a *named, surveyed research area*; **LIT-0032** asserts all three headline axes in one sentence | That the compiler is a *trained component of a multimodal model* conditioned on time-valid clinical evidence, not an LLM emitting a plan | An arm where the compiler is replaced by an LLM-emitted plan at matched compute. If the LLM planner matches it, the architectural claim is dead | **CRITICAL** |
| T3 | **LIT-0034 — Equifinality in MoE**: hash, random-fixed and top-1 routing degrade only 1.1–2.2 PPL across 62 controlled runs | That learned case-conditional structure beats random/matched structure — the exact hypothesis this paper falsifies in the LM setting | **Baseline family 4 (random/shuffled routing) is now the load-bearing experiment of the project**, not a sanity check. Predeclare the effect size that counts as success | **CRITICAL** |
| T4 | **LIT-0026 — Mixture of Parrots**: at fixed active parameters, memorisation improves while **reasoning saturates** | A quality win at matched compute on clinical reasoning | Predeclare the efficiency/calibration branch of G4 as primary and quality as non-inferiority, **before** Stage C produces a number | **HIGH** |
| T5 | **LIT-0036 — Multimodal Routing** does per-patient sparse routing on **MIMIC-IV + notes + CXR**, the project's own intended cohort, with auditability and missing-modality ablation | That topology varies, not just route weights; typed operators; `available_at_time`; export/replay | Beat a fixed-route-set conditional model at matched compute on MIMIC. If a 10-route weighting matches a compiled DAG, the topology claim collapses to a routing claim | **HIGH** |
| T6 | **LIT-0025 — Flex-MoE** routes by *observed modality combination* on ADNI and MIMIC-IV, with public code | Typed clinical operators rather than anonymous experts; topology rather than expert identity | Same as T5. State all four distinctions explicitly or the contribution reads as an increment on Flex-MoE | **HIGH** |
| T7 | **LIT-0035 — GraphBit** ships typed DAGs with schema validation, determinism, checkpointing and auditability | **Nothing.** Graph export and replay are *engineering prior art* | None needed. Present export/replay as a **prerequisite** — which is where `SUCCESS_CRITERIA.md` already puts it, at G2 — never as a contribution | **HIGH** |
| T8 | **LIT-0037 — Aegle** does per-case specialist activation for **clinical intake**, beating static multi-agent baselines on real patients | Multimodal, time-valid, replayable. Aegle is text-only with no typed operators, no export/replay, no compute matching | Any Front Door claim must be positioned against Aegle explicitly | **HIGH** |
| T9 | **LIT-0042 — Azzolin et al.**: for injective *regular* architectures, perfectly faithful explanations are **completely uninformative** | That a **modular** architecture escapes this — which the paper itself says it does | Nothing to disprove. This is simultaneously the sharpest threat to C-10 **and the strongest external justification for the typed-operator DAG**. Make it load-bearing in the architecture rationale | **HIGH** |
| T10 | **LIT-0039 — MedVerse (ACL 2026)** reformulates medical reasoning as a DAG | That the project's DAG is over *typed computation operators with evidence-authorization edges*, not over generated reasoning text for decoding parallelism | Distinction is real and must be stated. **Also a naming collision** — `RESEARCH_SPEC.md` already permits changing the `Medical-DAG-*` working names | MEDIUM |
| T11 | **LIT-0038 — MDAgents** conditions collaboration structure on assessed case complexity, in medicine, at a top venue | Model-internal computation rather than external LLM calls; a compiled graph rather than a menu of three templates | Never phrase the contribution in a way MDAgents also satisfies | MEDIUM |
| T12 | **LIT-0051 / LIT-0052 / LIT-0050** — human–AI combination underperforms the better party alone on decision tasks; mandated oversight gives "a false sense of security"; a confident wrong AI suggestion drops expert accuracy from ~82% to ~46% | That mandatory human confirmation is a *control* | **Stop calling human confirmation a mitigation.** It is a requirement whose effectiveness is itself an open evaluation question | **HIGH (safety)** |

### What survives

Across every system positioned, **none** combines: five medical modalities including 3D and
longitudinal journeys; `available_at_time` decision-time semantics inside the compiler; per-case
compiled typed topology; equal-compute controlled arms *including random/shuffled routing*; and
graph-intervention faithfulness testing. The workflow survey (LIT-0031) confirms **zero clinical
applications** in the entire dynamic-workflow-optimisation literature it reviews, and it names
**structural credit assignment** — whether gains come from edges, verifiers, prompts, or simply more
compute — as an *open problem*.

**That is the defensible claim: a composite plus an evaluation contribution in a domain the field has
not entered.** It is weaker than "we invented a new mechanism". It is what the evidence supports.

Note also, across all systems screened by SRCH-0001, **not one scored `DEMONSTRATED` on
equal-compute evidence**. That is cheap ground to occupy at the 300–700M small-model scale and it is
the claim least likely to be scooped.

## The C-02 verdict

C-02 — *"existing systems process every patient with the same fixed computation path"* — is the
project's stated differentiation premise. SRCH-0002 was commissioned to source it.

**It is not supportable as written, and the evidence contradicts it in the medical multimodal domain
specifically — the very domain the project claims differentiation in.** Flex-MoE (LIT-0025) routes by
observed modality combination; Multimodal Routing (LIT-0036) activates per-patient routes on MIMIC-IV;
Aegle (LIT-0037) activates specialists per case; MDAgents (LIT-0038) adapts structure to case
complexity; MARM (LIT-0030) selects reasoning mode per query.

**Restoring Han et al. (2022) — LIT-0002 — would have made it worse, not better.** A TPAMI *survey*
of dynamic neural networks exists because the field is large and mature. Citing it after "existing
systems use one fixed path" invites the reader to open it and find hundreds of methods that do not.
The claims map assigns LIT-0002 a role it cannot perform, and that mis-assignment should be corrected
regardless of what wording replaces C-02.

**What the literature does support** comes from inside the conditional-computation literature itself.
Raposo et al. (**LIT-0024**), in the paper's own words: *"this simple procedure uses a **static
computation graph** with known tensor sizes, unlike other conditional computation techniques."* The
field varies *which parameters* run, and deliberately keeps the *graph* fixed, because a static graph
is what makes batched training tractable. That is a real, citable mechanism gap.

Three replacement wordings, ordered by defensibility. **The choice is the owner's** — changing C-02
is a claim change under `CLAUDE.md` §Claim boundary.

- **Option A — mechanism gap (recommended).** *"Conditional computation is established (LIT-0002) and
  has reached medical multimodal models as modality- and token-level expert routing (LIT-0025,
  LIT-0036). What varies is which parameters process a fixed sequence of operations; the computation
  graph itself is fixed in advance (LIT-0024) and is not typed, exported, replayed or intervened on.
  This project targets that gap."*
- **Option B — scoped negative.** *"We are not aware of a medical multimodal system that compiles a
  per-case, typed, exportable and replayable computation graph over time-valid evidence at the
  architecture level."* Honest, checkable, asserts no universal negative.
- **Option C — internal-spec.** Restrict "existing systems" to the project's own declared baselines.
  C-02 becomes `internal-spec`, needs no external source, and cannot be attacked.

**Do not keep any wording of the form "existing systems process every patient with the same fixed
computation path."** LIT-0036 alone refutes it, on the project's own intended cohort.

## Baseline shortlist

All six families remain `DEFERRED`. **SRCH-0006 has not run**, and naming a baseline in
`BENCHMARK_CONTRACT.md` materially changes public benchmark rules — a human approval gate.

| Family | Expected shape | Candidates on record |
|---|---|---|
| 1 Fixed-path medical/open | External candidate | LIT-0015 (MedGemma, `CONDITIONAL` — weights gated behind terms a human must accept); LIT-0019 (BiomedGPT, `CONFLICT` — see below); LIT-0004 (LLaVA-Med, licence prohibits clinical-decision-support use); LIT-0018 (RadFM, licence unread) |
| 2 Same-backbone fixed path | **Internal control** — blocked on the undecided backbone | — |
| 3 Static typed DAG | **Internal control** | Method precedent now exists: LIT-0035 is the typed-DAG execution substrate; LIT-0031 surveys static-vs-dynamic |
| 4 Random / shuffled router | **Internal control** — **now the load-bearing experiment** (T3) | Method precedent: LIT-0034 establishes hash/random-fixed routing as the standard control and reports it nearly matches learned routing |
| 5 Sparse / MoE routing | Likely **internal control**, not a checkpoint | LIT-0003 (Mixtral) makes **no equal-compute claim** and at 13B active cannot be matched to a 300–700M model. LIT-0028 (Artetxe) and LIT-0024 carry the matched-compute evidence Mixtral does not |
| 6 Proposed dynamic typed DAG | **Internal control** — the method under test | — |

**Two additions to `BENCHMARK_CONTRACT.md` are recommended by the evidence and require owner
approval:** (a) an **LLM-orchestrated agentic planner** arm over the same operator vocabulary (T2), and
(b) a **fixed-route-set conditional model** arm (T5). Without them the two sharpest threats are
untested.

**Fixed boundaries regardless of what SRCH-0006 finds.** LIT-0016 (Med-PaLM M) and Med-Gemini are
matrix *columns, not baselines* — SRCH-0001 read at ar5iv the sentence *"We will not be able to open
source the large language models (LLMs) used in this study"*, and `BENCHMARK_CONTRACT.md` forbids
relying on a proprietary baseline whose evaluation cannot be reproduced. Any dataset in a
`benchmark_or_dataset` record must cross-link to a `DS-` id already surveyed under TASK-0005.

## Conflicts on record

Five records carry `verification.status: CONFLICT` and therefore **cannot be `ACCEPTED`**. Each is a
thing a prose bibliography would have carried forward unnoticed.

| Record | The conflict |
|---|---|
| **LIT-0008** Bedi et al. (2025) | The APA string prints pages **319–328**. Crossref REST, DOI content negotiation and PubMed E-utilities all return first page **319 and no end page**. Read the published PDF's last page before using a range |
| **LIT-0019** BiomedGPT | Repository licence states **Apache-2.0**; README states academic research only with **commercial and clinical uses strictly prohibited**. Both cannot govern. A clinical-use prohibition bites directly on this project |
| **LIT-0032** BatchDAG | arXiv id `2607.*` encodes July 2026; the arXiv API returns a v1 date of **2026-04-17**. Independently flagged by SRCH-0003 and confirmed by the main session |
| **LIT-0035** GraphBit | arXiv id `2605.*` encodes May 2026; the API returns **2026-03-08** |
| **LIT-0056** Abdelrazek et al. (2026) | Reports ESI under-triage **10.7%** / over-triage **6.2%**; LIT-0048 reports **3.3%** / **28.9%** over 5.3M encounters. Almost certainly definitional — which is itself the finding: **any under-triage number entering `SAFETY_SPEC.md` must carry its operational definition or it is meaningless** |
| **LIT-0058** Sax et al. (2025) | Two copies of the article attached the per-condition delay figures to *opposite* conditions. The 36.7% overall under-triage figure was consistent and is recorded; the per-condition minutes are **not** recorded and must not be quoted |

## Reference register

Verified metadata lives in `project_state/literature.json`; formatted citations are generated from
`citation.apa7` so there is exactly one copy to keep correct.

**Back-filled from the 2026-08-26 round (SRCH-0000), re-verified 2026-09-02:**
LIT-0001 Moor et al. (2023) *Nature* · LIT-0002 Han et al. (2022) *IEEE TPAMI* · LIT-0003 Jiang et al.
(2024) Mixtral · LIT-0004 Li et al. (2023) LLaVA-Med · LIT-0005 Turpin et al. (2023) · LIT-0006
Hamamci et al. (2026) CT-RATE (→ DS-0007) · LIT-0007 Kapoor & Narayanan (2023) · **LIT-0008 Bedi et al.
(2025) — CONDITIONAL, see Conflicts** · LIT-0009 Acosta et al. (2022) · LIT-0010 Wornow et al. (2023) ·
LIT-0011 Banerji et al. (2023) · LIT-0012 Goh et al. (2024) · LIT-0013 Vasey et al. (2022) DECIDE-AI.

**Medical multimodal (SRCH-0001):** LIT-0014 MedGemma 1.5 · LIT-0015 MedGemma (CONDITIONAL) ·
LIT-0016 Med-PaLM M · LIT-0017 BiomedCLIP — *the "Zhang et al. (2025)" the claims map records as
owed back* · LIT-0018 RadFM (CONDITIONAL) · LIT-0019 BiomedGPT (CONDITIONAL, CONFLICT) · LIT-0020
MedVersa (CONDITIONAL) · LIT-0021 multimodal AMIE · LIT-0022 GSCo/MedDr · LIT-0023 Almarie et al.
(2025) — *FDA device concentration, the only quantitative support found for C-01*.

**Conditional and sparse computation (SRCH-0002):** LIT-0024 Mixture-of-Depths — *the static-graph
quotation* · LIT-0025 Flex-MoE · LIT-0026 Mixture of Parrots · LIT-0027 MoE under strictly equal
resource · LIT-0028 Artetxe et al. (2022) · LIT-0029 *Scaling medical AI across clinical contexts*
(UNDER_REVIEW — text unreachable) · LIT-0030 MARM (CONDITIONAL).

**Per-case typed DAG (SRCH-0003):** LIT-0031 *From Static Templates to Dynamic Runtime Graphs* —
**the survey that names the field** · LIT-0032 BatchDAG (CONDITIONAL, CONFLICT) · LIT-0033 MaAS ·
LIT-0034 Equifinality in MoE (CONDITIONAL) · LIT-0035 GraphBit (CONDITIONAL, CONFLICT) · LIT-0036
Multimodal Routing (CONDITIONAL) · LIT-0037 Aegle (CONDITIONAL) · LIT-0038 MDAgents · LIT-0039
MedVerse (ACL 2026).

**Faithfulness (SRCH-0004):** LIT-0040 Lyu et al. (2024) — **the in-window definition** · LIT-0041
Geiger et al., causal abstraction and *graded* faithfulness (CONDITIONAL) · LIT-0042 Azzolin et al.
(CONDITIONAL) — *the impossibility result whose escape route is modularity* · LIT-0043 Bilodeau et al.
(2024) PNAS · LIT-0044 Paul et al. (2024) causal mediation · LIT-0045 Mondorf et al. (2025) circuit
compositions · LIT-0046 Ostermayer et al. (2024) Epic sepsis external validation · LIT-0047 Varoquaux
& Cheplygina (2022).

**Triage, safety and calibration (SRCH-0005):** LIT-0048 Sax et al. (2023) — *the operational
definition of under-triage* · LIT-0049 Lupton et al. (2023) — *the only numeric target in the
literature, and it is trauma-specific* · LIT-0050 Dratsch et al. (2023) automation bias · LIT-0051
Vaccaro et al. (2024) (CONDITIONAL) · LIT-0052 Green (2022) (CONDITIONAL) · LIT-0053 Van Calster et al.
(2025) · LIT-0054 Savage et al. (2025) · LIT-0055 Schmieding et al. (2022) symptom checkers ·
LIT-0056 Abdelrazek et al. (2026) (CONDITIONAL, CONFLICT) · LIT-0057 CTAS Guidelines 2025
(CONDITIONAL) · LIT-0058 Sax et al. (2025) (CONDITIONAL, CONFLICT).

## Triage taxonomies — licence terms, read at source

Recorded as evidence for a decision, **not as an adoption**. SRCH-0005 read each term at source and
reproduced none of the scoring tables.

| Instrument | Licence position | Software implementation |
|---|---|---|
| **ESI** (ENA, © 2023) | *"No part of the material protected by this copyright may be reproduced or utilized in any form, electronic or mechanical … without written permission"* | **No, without written ENA permission** |
| **CTAS** (CAEP) | Restricts *copying* and *educational course instruction* without permission; does not name software | **Unresolved** — needs written confirmation from CAEP |
| **MTS** (ALSG/Wiley) | Licensing administered by Wiley; named developer categories exist | **Yes, under an explicit registered licence.** SRCH-0005 read that *no* software company currently holds MTS accreditation |
| **ATS** (ACEM P06 V5, 2023) | *"All rights reserved"* | **Not without ACEM permission** |
| **ACS Field Triage** | Content may not be incorporated into third-party applications without written authorisation, **explicitly including AI and machine learning** | **Explicitly no.** The strictest term found |
| **NEWS2** (RCP) | *"there is no copyright restriction"*, with attribution; charts must not be modified | **Yes** — but it is a deterioration score, **not** a triage taxonomy |

**A licence collision worth recording now:** the PhysioNet derivative corpora that encode ESI decision
points distribute under the PhysioNet Credentialed licence, and whether ENA permission was obtained is
not stated on the dataset pages SRCH-0005 read. That is a Data Contract risk, unresolved.

## Gaps in this survey

Stated so they are not mistaken for coverage.

1. **SRCH-0006 has not run.** No baseline family can leave `DEFERRED` until it does.
2. **SRCH-0005 is PARTIAL** — it hit its turn limit. Not reached: KTAS, JTAS, the South African
   Triage Scale, START/SALT, and **the Thai national ED triage scale**, whose relevance to this
   project's eventual clinical context is high. Also unreached: in-window MTS and CTAS reliability
   evidence, and MC-BEC (a multimodal emergency-care benchmark).
3. **`false_reassurance_rate` has no literature definition.** SRCH-0005 found no study that
   operationalises it. It is a project-defined construct and must be labelled as one wherever it is
   reported.
4. **Several records rest on scout reads the main session has not repeated.** Every bibliographic
   record was independently verified; the *claims about what each paper says* were verified only for
   the quotations recorded in `quoted_figures`. Records at `CONDITIONAL` are the ones where this
   matters most.
5. **Novelty-matrix positions on the thirteen back-filled records are empty.** They were carried over
   from the project's own pillar table, not a fresh reading, and a cell asserted without reading the
   source is the failure this survey exists to prevent.

## What remains for the owner

Agent work stops at evidence. Each item below is carried by TASK-0026.

1. **Reframe the contribution claim** (T1, T2). Breadth, scale and open weights are no longer
   differentiators. This is a material change to how the project positions itself and needs a
   Decision Log entry.
2. **Choose the C-02 wording** — Options A, B or C above. A claim change under §Claim boundary.
3. **Predeclare which branch of G4 is primary** — quality at matched compute, or
   efficiency/calibration/auditability. The literature (T3, T4) supports the second. Deciding this
   *after* seeing results would be metric selection after the fact, which `CLAUDE.md` §Research gates
   prohibits.
4. **Approve or reject two new comparison arms** in `BENCHMARK_CONTRACT.md`: an LLM-orchestrated
   agentic planner, and a fixed-route-set conditional model.
5. **Rule on the window exception** for the module-network method ancestry (Andreas 2016, Hu 2017).
6. **Adopt or decline a triage taxonomy** — this changes what `urgency` *means* and may require a
   `MODEL_API_CONTRACT.md` version bump. Several instruments are copyrighted; one forbids AI use
   outright.
7. **Reframe human confirmation** in the `SAFETY_SPEC.md` hazard log from a *control* to a
   *requirement of unproven reliability* (T12). A safety-claim change; the safety owner's call.
8. **Decide whether `graph_export_replay_intervention` remains a contribution** or is demoted to a
   prerequisite, given LIT-0035.
9. **Consider renaming the `Medical-DAG-*` family** given LIT-0039.
10. **Choose the base model family** — baseline family 2 cannot resolve until this is settled.
11. **Resolve the five conflicts** listed above.
12. **Whether to accept the HAI-DEF terms** to obtain MedGemma weights — a Human Approval Policy gate,
    not an engineering step.
