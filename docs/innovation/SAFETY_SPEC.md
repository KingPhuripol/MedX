# Clinical Safety Specification

**Owner:** Thanrada Tungweerapornpong  
**Reviewer role:** independent and read-only for verdicts  
**Safety posture:** conservative research prototype with mandatory human review

## Safety goals

1. Avoid delaying review of potentially critical cases.
2. Avoid false reassurance and unsupported certainty.
3. Make missing information, uncertainty, provider failure, and scope limitations visible.
4. Prevent unauthorized data disclosure.
5. Preserve human authority, correction, and an auditable record.

## Prohibited behavior

- autonomous diagnosis, treatment, prescription, test order, referral, discharge, or patient instruction;
- presenting a differential or pathway as confirmed fact;
- hiding a red flag because model confidence is low or another score is reassuring;
- producing a recommendation from invalid, future, unauthorized, or missing-required evidence;
- sending real/linkable patient information to an external API without approval;
- exposing hidden chain-of-thought as an explanation;
- silently changing urgency/pathway taxonomy or safety thresholds;
- using the prototype for actual care without separate authorization.

## Safety controls

### Input controls

Schema/version validation, authorization, evidence availability check, units/ranges, missingness, contradictory/implausible value flags, modality support, and minimum-required-information policy.

### Deterministic controls

Versioned red-flag rules and conservative escalation run independently of the model. A model cannot override them downward. Changes require clinical review, tests, and a Decision Log entry.

### Model controls

Calibrated uncertainty where feasible, abstention, out-of-distribution/unsupported detection, constrained outputs, evidence references, and no free-form autonomous instruction.

### Interface controls

Prominent `RESEARCH PROTOTYPE - HUMAN REVIEW REQUIRED`, urgency not encoded only by color, known/missing evidence timeline, limitation text, review action before completion, and immutable original output after override.

### Operational controls

Provider timeout/circuit breaker, synthetic offline demo, access control in approved environments, minimum retention, no secrets in logs, monitoring of failures/overrides, and a disable switch.

## Hazard log baseline

| Hazard | Example cause | Potential harm | Control | Verification |
|---|---|---|---|---|
| under-triage | model misses critical evidence | delayed review | red-flag rule, conservative thresholds, human confirmation | critical sensitivity and under-triage tests |
| over-triage / alarm fatigue | screen escalates without discriminating | reviewers stop reading escalations; the control that carries safety decays | over-triage rate reported beside under-triage; a case set that contains genuinely routine presentations | over-triage rate and escalation rate, reported together and never alone |
| false reassurance | confident low-risk text | user trusts unsafe output | uncertainty, limitation, no patient-facing autonomous use | false reassurance review |
| future leakage | discharge diagnosis in input | inflated evidence and unsafe expectations | availability audit and temporal block | leakage tests |
| wrong pathway | taxonomy/data mismatch | inappropriate destination | ranked pathways, wrong-cost metric, human override | pathway strata and override review |
| missing modality hallucination | absent image treated as negative | false certainty | explicit missingness and evidence references | missing-modality tests |
| provider drift | external model version changes | unstable output | version pin/log, contract/safety regression | adapter certification |
| privacy disclosure | raw patient text sent externally | confidentiality breach | synthetic default and approval gate | payload and audit review |
| automation bias | UI overstates authority | clinician over-reliance | decision-support language and reasoned override | usability/human-factors review |
| graph misinterpretation | DAG shown as clinical rationale | false trust | label executed computation, faithfulness evidence | UI wording and intervention results |

## Safety evaluation gates

No release/demo candidate passes with:

- unresolved confirmed temporal/patient leakage;
- critical red flag suppressed by model output;
- invalid provider output rendered as valid;
- a path that completes without human review;
- real patient payload sent externally without approval;
- false autonomous diagnosis/treatment claims;
- missing provenance/model/provider/contract version;
- unresolved `CRITICAL_FAIL` safety verdict.

Quantitative thresholds are frozen per task after clinical and sample-size review in the Evaluation Contract. Until then, do not invent universal numerical safety thresholds.

Every safety claim is bounded by the named care setting (DEC-0016). Input from outside it — paediatric age, trauma mechanism, prehospital origin — is an out-of-distribution condition and abstains or escalates; it is never scored as though it were in setting.

**Any under-triage figure must carry its operational definition or it means nothing.** Two peer-reviewed emergency-department sources disagree threefold and in opposite directions — LIT-0048 reports 3.3% under- and 28.9% over-triage over 5.3 million encounters, LIT-0056 reports 10.7% under- and 6.2% over-triage across six studies — and the disagreement is almost certainly definitional rather than factual. It is unresolved. The only numerical under-triage target found anywhere in the surveyed literature, the 5% goal in LIT-0049, is **specific to prehospital trauma field triage**, a setting this project explicitly excludes, and must never be imported here as a threshold.

**`false_reassurance_rate` is a project-defined construct.** SRCH-0005 found no study that operationalises it. It must be labelled as project-defined wherever it is reported, and never presented as a metric with a literature baseline.

**Human confirmation is a requirement whose effectiveness is itself an open evaluation question, not a demonstrated mitigation.** LIT-0050, LIT-0051 and LIT-0052 together report that a confident wrong AI suggestion drops expert accuracy from about 82% to about 46%, and that human-AI combination can underperform the better party alone on decision tasks. The requirement stands; the claim that it works does not.

## Verdict rubric

- `PASS`: all applicable controls and evidence pass; no unresolved material issue.
- `CONDITIONAL_PASS`: no critical issue; bounded gaps have owners, deadlines, and do not invalidate the current use.
- `FAIL`: material control/evidence failure; block release or milestone claim until remediated and independently re-reviewed.
- `CRITICAL_FAIL`: credible risk of unauthorized data disclosure, unsafe autonomous action, hidden critical under-triage, or invalid evidence represented as valid. Stop affected use immediately and escalate.

The reviewer never edits the implementation under review. They produce findings with severity, evidence, affected requirement, reproduction, and required remediation.

## Incident response

Stop affected workflow, preserve logs without expanding exposure, classify the incident, notify the human project/safety owners, contain provider/data access, identify affected experiments/demos, record a risk/decision, remediate, and require independent re-review. Do not delete audit evidence to make the failure disappear.

