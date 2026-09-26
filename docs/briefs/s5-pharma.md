# S5 brief — drug terminology and med-rec evaluation (scout, 2026-09-26)

## What a student project can use offline
| Resource | Use | Constraint |
|---|---|---|
| RxNorm Current Prescribable Content (RRF, 08-Sep-2026) | offline normalizer (RXCUI ingredient/SCD/brand) | **no license**; show NLM disclaimer, state data currency |
| RxNorm Full Release / RxNav-in-a-Box | full sources, offline RxClass | free **UMLS license** needed |
| RxNav REST (RxNorm, RxClass) | online lookups | no license, 20 req/s, not reproducible offline → cache once, pin date |
| RxClass: ATC, MED-RT, FDA EPC, VA | duplication / allergy classes | SNOMED-sourced classes: hold until license confirmed (Thailand is a SNOMED member) |
| WHO ATC/DDD | codes | attribution; no redistribution/manipulation; research use unclear → don't redistribute tables |
| Thai Medicines Terminology (TMT, TMTRF20260921) | Thai names | login required; no visible license; ask THIS in writing before redistributing derived tables |
| TMT→RxNorm (THIRAWAT, HIR 2026 32(2):156) | baseline mapper | CC BY-NC; Hits@1 0.868 — baseline, not gold |
| MIMIC-IV-ED `medrecon.etccode` | ready duplication class in MIMIC | PhysioNet DUA |

No open machine-readable allergy cross-reactivity table exists → hand-curate a small R1 side-chain table cited to the 2022 drug-allergy practice parameter (JACI 150(6):1333, doi 10.1016/j.jaci.2022.08.028).

## Taxonomy and evaluation precedent
Almanasreh 2016 (BJCP, doi 10.1111/bcp.13017); MedTax 2019 (12 types/28 subtypes); AHRQ MARQUIS. Leapfrog CPOE test (Co et al., JAMIA Open 2026): fictitious patients, per-category alert rate — closest method precedent. Li et al. 2015 (doi 10.1186/s12911-015-0160-8) discrepancy P/R/F 88.6/82.5/85.5. No published paper injects synthetic errors into real med lists with per-type P/R — our design is novel in that narrow sense.

## Recommendation
1. Normalizer = no-license RxNorm Prescribable RRF; duplication = ATC4/EPC (+ `etccode` on MIMIC); pin versions.
2. Skip SNOMED-sourced classes for now.
3. TMT: request THIS research terms; map via SUBS/VTM ingredient names; pharmacist spot-check; don't redistribute.
4. Allergy v1: exact ingredient → same ATC4/MED-RT class → cited R1 side-chain table; label "suggests for review".
5. Freeze 5 injection operators (omit, duplicate-ingredient, duplicate-class, dose×k/frequency, allergy-conflict) before results; inject into test-split patients only; no-injection nuisance set for precision; patient-level bootstrap CI.

## Owner decisions
UMLS license for a team member? · contact THIS about TMT terms · record frozen injection operators in `docs/DECISIONS.md`.
