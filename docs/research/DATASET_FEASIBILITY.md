# Dataset Access, License and Ethics Feasibility

**Owner:** Jakkapat Bunjongruxsa · **Task:** TASK-0005 · **Gate:** G0 criterion 3
**Machine record:** `project_state/dataset_feasibility.json` (validated by `scripts/verify_harness.py`)
**Schema:** `schemas/dataset-feasibility.schema.json`
**Status:** all six candidates `UNDER_REVIEW`; no dataset is selected

## Why this exists

`docs/research/BENCHMARK_CONTRACT.md` forbids naming a public benchmark as selected before access
and licence evidence exists. The submitted Project Idea therefore names MIMIC-IV, MIMIC-CXR,
CheXpert, BraTS, VQA-RAD and SLAKE only as **candidates under feasibility review**. This file, and the
machine record beside it, is where that review is recorded. Until it concludes, RISK-0002 is the live
threat to the whole Research Track: nothing in the architecture matters if no dataset can follow one
patient across modalities.

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

## Candidates

| ID | Dataset | Claimed modalities | Verdict |
|---|---|---|---|
| DS-0001 | MIMIC-IV | clinical text, structured, longitudinal | UNDER_REVIEW |
| DS-0002 | MIMIC-CXR | clinical text, 2D image | UNDER_REVIEW |
| DS-0003 | CheXpert | 2D image | UNDER_REVIEW |
| DS-0004 | BraTS | 3D volume | UNDER_REVIEW |
| DS-0005 | VQA-RAD | clinical text, 2D image | UNDER_REVIEW |
| DS-0006 | SLAKE | clinical text, 2D image | UNDER_REVIEW |

The modality column records what the project *expects* from each candidate. It is a claim to be
checked, not a finding — like every other seeded field, it carries no verified evidence yet.

## Definition of done

TASK-0005 closes when every candidate has a verdict that is not `UNDER_REVIEW`, every `VERIFIED`
dimension cites its source, every `CONDITIONAL` verdict names its unmet condition, and the result is
reflected in RISK-0002 and in `BENCHMARK_CONTRACT.md`. Partial completion is reported as partial —
`project_status.py` and the harness both read the machine record, so an unfinished survey cannot
present itself as a finished one.
