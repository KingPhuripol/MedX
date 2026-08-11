# Risk Register

Machine state: `project_state/risks.json`. Probability and impact use `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. Review weekly and on every trigger.

| ID | Risk | P | I | Owner | Trigger | Mitigation | Fallback | Status |
|---|---|---:|---:|---|---|---|---|---|
| RISK-0001 | Group Application may be unsubmitted close to deadline | HIGH | CRITICAL | Phurinat | No receipt/confirmation by 12 Aug | Verify immediately; parallel advisor and form preparation | Escalate to course staff/advisor before deadline | CLOSED |
| RISK-0002 | No dataset supports all desired modalities linked at patient level | HIGH | HIGH | Jakkapat | Feasibility inventory finds incompatible access/linkage/license | Modular dataset mixture with explicit capability subsets; contract shared fields | Narrow evaluated combinations while retaining interfaces and honest limitation | OPEN |
| RISK-0003 | Temporal or patient-identity leakage invalidates results | MEDIUM | CRITICAL | Jakkapat | Overlap, missing timestamps, future-derived field, post-split transforms | Split first, availability ledger, automated audit, blinded test | Rebuild affected data and rerun all dependent experiments | OPEN |
| RISK-0004 | Compute cannot support stable approximately 4B training | HIGH | HIGH | Phurinat | No approved budget/hardware plan by 4B gate | Estimate early; parameter-efficient and staged recipe; checkpoint/recovery tests | Deliver strongest valid smaller model and explicitly report scale limitation | OPEN |
| RISK-0005 | Dynamic routing collapses or offers no controlled benefit | MEDIUM | HIGH | Thanapol | Graphs converge, all nodes active, or lose to static under equal budget | Entropy/load constraints, curriculum, operator ablations, kill tests | Reframe contribution to validated adaptive sparse/soft graph only through decision | OPEN |
| RISK-0006 | Research and Innovation contracts drift | MEDIUM | HIGH | Supreeya | Adapter-specific fields or failing shared fixture | Versioned schemas, contract tests, gateway boundary, integration audit | Freeze last compatible contract and add explicit migration | OPEN |
| RISK-0007 | Prototype gives false reassurance or under-triages critical cases | MEDIUM | CRITICAL | Thanrada | Critical sensitivity/under-triage gate fails | Red-flag override, abstention, conservative escalation, human confirmation | Restrict demonstration scope and disable unsafe pathway output | OPEN |
| RISK-0008 | Academic writing absorbs technical critical-path capacity | HIGH | HIGH | Phurinat | Deliverable enters T-7 with missing sections/evidence | Draft from live SOT, evidence inventory, protected review buffers | Cut P3/P4 technical scope, not validation/safety | OPEN |
| RISK-0009 | External API causes privacy, cost, or provider lock-in | MEDIUM | CRITICAL | Supreeya | Real data request, uncapped usage, provider objects in client | Synthetic fixtures, approval gate, budgets, stable gateway | Disable external adapter and use mock/local baseline | OPEN |
| RISK-0010 | Public release violates data/model license or contains sensitive artifacts | LOW | CRITICAL | Jakkapat | Unresolved license/provenance or release scan finding | Release manifest, license matrix, secret/PHI scan, human approval | Release code/evaluation only; withhold weights/data | OPEN |

## Escalate immediately

- Official deliverable is inside T-5 without an advisor-ready version.
- A critical dataset, advisor approval, ethics requirement, or compute path becomes unavailable.
- Temporal leakage or patient overlap touches reported results.
- Safety testing shows false reassurance, critical under-triage, or missing human approval.
- A Tier 4 run is proposed without valid gates and explicit approval.
- One member owns more than 40% of active P0/P1 tasks without recovery support.

