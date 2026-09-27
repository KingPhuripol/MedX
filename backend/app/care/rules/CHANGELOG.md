# Care rules changelog

Mock baseline rules for the deterministic mock provider (`care_rules_v1.json`). Research prototype; not calibrated;
not expert-reviewed (D1). Every change cites the train/dev decision points that motivated it (never the v1 test
split, never the held-out set) and at least one source in `data_factory/templates/references.json`. Red-flag rules,
alerts, screening and escalation are computed before the provider and are not changed by any entry here.

## care-rules-1.1.0 (slice s6r)

### R1 — Sepsis screening ranks before the generic NEWS review when both fire

- Change: new `pathway_priority` = `CP-SEPSIS-SCREEN`, `CP-NEWS-URGENT-REVIEW`. Listed pathways are ranked first in
  that order (stable); unlisted pathways keep their previous order after them. Next-information order, alerts and
  screening are unchanged.
- Why: when qSOFA and a NEWS rule co-fire, 1.0.0 put the generic NEWS urgent-review pathway first because the NEWS
  alert happened to be listed first. The specific sepsis screening pathway (lactate, blood cultures) is the more
  specific next step, and the NEWS escalation itself is unaffected (the red-flag alerts and clinician escalation are
  computed before the provider).
- Decision points: SYNE-0011:T1, SYNE-0011:T2 (dev; pathway top-1 miss, engine CP-NEWS-URGENT-REVIEW, reference
  CP-SEPSIS-SCREEN).
- Sources: PMID-34599691 (Surviving Sepsis Campaign 2021: screening for sepsis in acutely ill, high-risk adults;
  lactate and blood cultures), RCP-NEWS-2012 (NEWS triggers urgent clinical review, not a specific pathway).

### R2 — Community-acquired pneumonia: glucose and haemoglobin for the severity rule

- Change: `T-FEVER-COUGH` next information `NI-IMG-CXR` → `NI-IMG-CXR`, `NI-LAB-GLU`, `NI-LAB-HGB` (appended after
  chest imaging, so the imaging item keeps its rank).
- Why: the ATS/IDSA 2019 CAP guideline recommends a validated prognostic rule, preferably the Pneumonia Severity
  Index, alongside clinical judgement for the site-of-care decision; PSI uses glucose and haematocrit (haemoglobin
  is the closest item in the closed vocabulary). This also explains part of the low ordered-after-T proxy: gold
  `ordered_after_T` is mostly routine labs that 1.0.0 never suggested.
- Decision points: SYNE-0139:T1 (dev; fever with cough, ordered after T: CREAT, GLU, HBA1C, HGB, WBC; 1.0.0 suggested
  chest imaging only).
- Sources: PMID-31573350 (Metlay JP et al., ATS/IDSA CAP guideline 2019).

### Explained, not changed

- Ordered-after-T proxy hit@3 stays low: most dev decision points with a gold `ordered_after_T` are complaints with
  no sourced work-up (for example SYNE-0007:T1, SYNE-0073:T1, SYNE-0097:T1), where the gold orders routine
  CREAT/HGB/WBC. No guideline in `references.json` supports suggesting routine labs for those complaints, so no rule
  was added (a proxy-only rule is not allowed).
