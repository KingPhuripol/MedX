# Dataset Access, License and Ethics Feasibility

**Owner:** Jakkapat Bunjongruxsa · **Task:** TASK-0005 · **Gate:** G0 criterion 3
**Machine record:** `project_state/dataset_feasibility.json` (validated by `scripts/verify_harness.py`)
**Schema:** `schemas/dataset-feasibility.schema.json`
**Status:** seven candidates, all `CONDITIONAL` with named conditions; no dataset is selected yet

## Why this exists

`docs/research/BENCHMARK_CONTRACT.md` forbids naming a public benchmark as selected before access
and licence evidence exists. The submitted Project Idea therefore names MIMIC-IV, MIMIC-CXR,
CheXpert, BraTS, VQA-RAD and SLAKE only as **candidates under feasibility review**; CT-RATE was added
on 2026-08-30 to cover the 3D CT modality none of the original six supplies. This file, and the machine
record beside it, is where that review is recorded. RISK-0002 is the live threat to the whole Research
Track: nothing in the architecture matters if no dataset can follow one patient across modalities.

## Rules this survey works under

1. **Documentary survey only.** No dataset is downloaded, no data is processed, no patient data is
   touched. A record here is a survey result, never an authorization to obtain data.
2. **No fact from memory.** Every dimension carries a `status` of `VERIFIED` or `UNVERIFIED`.
   `VERIFIED` requires a citation in `evidence` pointing at the provider's own current text. The
   inventory ships seeded with every dimension `UNVERIFIED` precisely so that unverified assumptions
   cannot masquerade as findings.
3. **Conservative defaults.** `credentialing_required` and `citi_required` are seeded `true` for every
   candidate. A provider that turns out not to require them is a pleasant correction; the reverse
   would be a plan built on an access route that does not exist.
4. **A negative result is a result.** Concluding that no candidate supports patient-level multimodal
   linkage is a valid outcome that closes G0, provided it is recorded honestly and a fallback is
   proposed. It is not a failure to be planned around.

## Dimensions each candidate must resolve

| Dimension | Question it must answer | Why it is decisive |
|---|---|---|
| Licence | Name, redistribution terms, derivative terms | The project plans an **open-weight release**. A licence that forbids derivatives or redistribution constrains the release, not just the training. |
| Access | Mechanism, credentialing, **CITI requirement**, whether granted | Determines whether the data is reachable at all, and by when. |
| Patient linkage | Stable patient identifier; linkable across modalities | The heart of RISK-0002 and the precondition for splitting by patient before generating examples. |
| Temporal validity | Is `available_at_time` present; if not, how derived | Without it there is no time-valid decision snapshot, and RISK-0003 cannot be controlled. |
| Modality coverage | Which of text / 2D / 3D / structured / longitudinal are genuinely present | The submitted document claims all five. Coverage must be demonstrated or the claim narrowed. |
| Obligations | Deletion duties, use restrictions, external-transfer terms | Binding under `CLAUDE.md` §Non-negotiable data rules 7 and 8. |

## The CITI coupling — this is a schedule dependency, not a formality

MIMIC-family data is obtained through PhysioNet credentialed access, and credentialing requires
completed CITI training. If that requirement holds on verification, then **TASK-0011 (CITI, immutable
DL-0003 on 25 Sep 2026) is a prerequisite for the access dimension of this survey**, not a parallel
academic errand.

The consequence is concrete: the licence, patient-linkage, temporal-validity and modality-coverage
dimensions can all be resolved from public documentation immediately and must be, because they are
what the Proposal Report needs. The access dimension cannot close before CITI does. Any candidate whose
only unresolved dimension is access should be recorded `CONDITIONAL` with that condition stated, not
left `UNDER_REVIEW` as though the work had not been done.

## Findings

All seven candidates are `CONDITIONAL`. None is rejected and none is accepted outright — every one
carries a named, closable condition. The survey produced three structural findings that matter more
than any individual verdict.

### 1. Patient-level multimodal linkage exists only inside the MIMIC family

`subject_id` denotes the same individuals in MIMIC-IV and MIMIC-CXR (v2.2 and later), so a single
patient can be followed across clinical text, structured data, longitudinal history and 2D imaging.
**No other candidate can be joined to that cohort.** CheXpert, BraTS, CT-RATE, VQA-RAD and SLAKE are
separate populations with internal identifiers only.

The consequence is concrete and must reach the Proposal: *"one patient, all five modalities"* is not
achievable from this candidate set. The achievable architecture is a **patient-linked MIMIC core plus
unlinked capability subsets** — which is exactly the mitigation RISK-0002 already prescribes, now
confirmed rather than assumed.

### 2. `available_at_time` must be derived from `storetime`, not `charttime`

In MIMIC-IV, `charttime` records when an observation was *made* (specimen collection) and `storetime`
records when the result *became available* in the system. A clinician cannot act on a lab result at
collection time. **Deriving `available_at_time` from `charttime` would inject future information into
the decision snapshot** — precisely the failure `CLAUDE.md` §Non-negotiable data rules 3 forbids and
that RISK-0003 exists to prevent.

There is a known caveat: a non-trivial share of `chartevents` rows carry `charttime > storetime`. The
derivation therefore needs an explicit, documented rule for inconsistent pairs rather than silently
taking one column.

Only the MIMIC family carries a usable timeline at all. BraTS, CT-RATE, VQA-RAD and SLAKE have none,
so they can support capability and evaluation but never a time-valid decision snapshot.

### 3. The licences constrain the open-weight release, not just the training

| Dataset | Licence | Commercial | Redistribution | Open-weight compatible |
|---|---|---|---|---|
| MIMIC-IV / MIMIC-CXR | PhysioNet Credentialed 1.5.0 | No — research only | Forbidden | **Undetermined** |
| CheXpert | Stanford Research Use Agreement | No | Forbidden | Unknown |
| BraTS | Challenge data-use agreement | No — academic only | Unknown | Unknown |
| CT-RATE | CC BY-NC-SA 4.0 | No | ShareAlike | **No** |
| VQA-RAD | CC0 1.0 | Yes | Yes | Yes |
| SLAKE | Ambiguous: CC BY-SA vs CC BY-NC-SA | Unresolved | Unresolved | Unresolved |

**Every candidate except VQA-RAD is non-commercial.** The submitted Project Idea promises an
*open-weight* model, which normally implies weights others may freely use. On this evidence the
realistic outcome is weights released for **non-commercial research use only**, and possibly under
ShareAlike terms if CT-RATE is used.

Two questions are open and neither may be assumed away:

- **The PhysioNet licence governs the data, not model weights derived from it.** It forbids sharing
  access to the data; it says nothing explicit about trained weights. This must be settled with
  PhysioNet in writing before any release. It is recorded `UNKNOWN`, not optimistically `YES`.
- **CT-RATE is ShareAlike.** If it trains the released model, the ShareAlike term plausibly reaches
  the derivative. This must be reconciled with the release plan before CT-RATE is relied upon.

RISK-0010 is raised on the strength of these findings.

### What CT-RATE was added to fix

The submitted document claims 3D volumes from **CT and MRI**. The original six candidates contained no
CT dataset at all — BraTS is brain MRI. CT-RATE (chest CT, 25,692 volumes, 21,304 patients) is the
dataset behind Hamamci et al. (2026), which the submitted document already cites in its bibliography.
Adding it as DS-0007 closes the gap between what the document claims and what the candidate list can
deliver. It carries the licence cost described above.

## Candidates

| ID | Dataset | Claimed modalities | Verdict |
|---|---|---|---|
| DS-0001 | MIMIC-IV | clinical text, structured, longitudinal | CONDITIONAL — CITI + credentialing + signed DUA |
| DS-0002 | MIMIC-CXR | clinical text, 2D image | CONDITIONAL — same as DS-0001; links to it by `subject_id` |
| DS-0003 | CheXpert | 2D image | CONDITIONAL — read the RUA at registration; unlinked subset |
| DS-0004 | BraTS | 3D MRI (brain) | CONDITIONAL — unlinked, no timeline; **does not satisfy the 3D CT claim** |
| DS-0005 | VQA-RAD | clinical text, 2D image | CONDITIONAL — confirm CC0 at OSF; evaluation benchmark only |
| DS-0006 | SLAKE | clinical text, 2D image | CONDITIONAL — **resolve licence ambiguity first** |
| DS-0007 | **CT-RATE** | clinical text, 3D CT | CONDITIONAL — CC-BY-NC-SA constrains the release; unlinked, no timeline |

Added 2026-08-30: DS-0007. Every verdict above cites its evidence in
`project_state/dataset_feasibility.json`. Dimensions marked `VERIFIED` were read at the provider's own
page; dimensions resolved only from secondary sources remain `UNVERIFIED` and say so, rather than being
upgraded because several second-hand summaries agreed with each other.

`scripts/verify_harness.py` enforces the rule that no dimension may claim `VERIFIED` and no dataset may
carry a verdict without at least one evidence entry.

## Definition of done

TASK-0005 closes when every candidate has a verdict that is not `UNDER_REVIEW`, every `VERIFIED`
dimension cites its source, every `CONDITIONAL` verdict names its unmet condition, and the result is
reflected in RISK-0002 and in `BENCHMARK_CONTRACT.md`. All four now hold, so the task sits at `REVIEW`.

**It is not `DONE`, and the difference is deliberate.** Gathering evidence is work that can be done on
the owner's behalf; accepting it is not. `reviewed_by` is `null` on every record until Jakkapat signs
off. What remains for the owner:

1. Confirm the `UNVERIFIED` dimensions at their providers — CheXpert's RUA, BraTS's year-specific DUA,
   VQA-RAD's CC0 declaration, SLAKE's licence, and MIMIC-CXR's timestamp columns.
2. Decide whether the non-commercial ceiling on the release is acceptable, or whether the candidate set
   should narrow to preserve a freer release.
3. Put the PhysioNet model-weights question to PhysioNet in writing.
