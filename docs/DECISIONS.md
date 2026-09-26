# Decisions

Dated approvals and material decisions. Old log (DEC-0001..0022) is in tag `archive/pre-factory-2026-09-26`.

## 2026-09-26 — Reset to Proposal v8
- **What:** removed old code and docs; `docs/PROPOSAL.md` is the single source of truth; four-role loop factory.
- **Approved by:** project owner (chat, 2026-09-26), including deletion and agent/config changes.
- **Rollback:** tags `archive/pre-factory-2026-09-26`, `archive/opd-2026-09-26`, `archive/agent-worktree-2026-09-26`; `../_archive/pre-factory-2026-09-26.tar.gz`.

## 2026-09-26 — Formulary licence decision (slice s5, Pharma Agent)
- **What:** which drug terminology the offline formulary (`backend/app/pharma/data/formulary.json`) may contain. Checked against primary sources on 2026-09-26 (planner), applied by the s5 builder.
- **RxNorm names + RXCUI (SAB=RXNORM): use.** NLM-created content is public domain; acknowledgement requested; the full release contains proprietary sources needing a UMLS licence — https://www.nlm.nih.gov/research/umls/rxnorm/docs/termsofservice.html. Current Prescribable Content is "No license required; public domain" — https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html. Only RXNORM ingredient names and RXCUIs are committed; no non-RXNORM SAB strings.
- **RxNav / RxClass APIs: curation time only.** Free, no licence (SNOMED CT exception), ≤20 req/s, NLM statement must be displayed — https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html, https://lhncbc.nlm.nih.gov/RxNav/applications/RxClassIntro.html. All 54 ingredient RXCUIs were verified via RxNav `/REST/rxcui.json` on 2026-09-26 (all TTY=IN); class names were cross-checked against RxClass FDASPL `has_epc`. No SNOMED CT-derived class data is committed.
- **Drug classes: FDA EPC names** (US federal work). One team grouping (`anticoagulant_group`) is recorded as team-authored. MED-RT is not used; the MED-RT UMLS restriction-level page (https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/MED-RT/index.html) returned HTTP 502 on 2026-09-26 and must be re-checked by the curator before any MED-RT use.
- **WHO ATC/DDD: do not commit.** "Copying and distribution for commercial purposes is not allowed. Changing or manipulating the material is not allowed." — https://www.whocc.no/copyright_disclaimer/. Proposal 3.2.4 allows RxClass or ATC; EPC satisfies it. Revisit only by human decision.
- **Thai Medicines Terminology (TMT): do not commit.** Release files are login-gated (https://this.or.th/service/tmt/download/) and the site is all-rights-reserved with no public redistribution licence (https://this.or.th/service/tmt/). `tmt_id` is reserved as `null`; Thai brand / Thai-script aliases are team-authored with `alias_source` recorded. Using TMT needs written permission from THIS plus a new entry here.
- **Attribution (shown on `/pharmacist/reconcile` and stored in formulary metadata):** "This product uses publicly available data from the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product."
- **Enforced by:** `test_formulary_licence_and_coverage` (0 ATC-pattern and 0 TMT-pattern codes).
- **Approved by:** planner decision in `slices/s5/SPEC.md`; pending human confirmation. Clinical sign-off of `cross_reactivity.json` and of `duplication_relevant` / `allergy_group` flags by a pharmacist is required before any non-synthetic use.
