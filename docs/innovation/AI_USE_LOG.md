# AI Use Log

Repository-side record of generative-AI assistance that materially influenced research, analysis,
prototyping or decisions on this project. It mirrors the AI Use Log sheet in the CPE494 Product
Discovery portfolio and closes the gap that RISK-0011 records: single-author documents shipping
without an independent account of how they were produced.

**Scope rule.** Log work that changed an artefact or a decision. Do not log routine editing.
AI may analyse evidence; it cannot create user evidence. No entry below produced a finding about a
real patient, and no real, identifiable or linkable patient data was sent to any external service
(DEC-0006, CLAUDE.md data rule 7).

**Standing provenance.** Git history is the primary record: commits carrying
`Co-Authored-By: Claude Opus 5` were produced in an assisted session with a human author.
Agent roles, skills and approval hooks live in `.claude/`; the human authority boundary is
`docs/shared/HUMAN_APPROVAL_POLICY.md`.

| Task | Tool | What it produced | What was rejected or corrected | How it was verified | Human decision | Data handling |
|---|---|---|---|---|---|---|
| Concept consolidation for the portfolio | Claude (Claude Code) | Mapping of five concepts to three testable sketches; CONCEPT 5 reclassified as a cross-cutting constraint | First proposal collapsed to two sketches, which would have dropped escalation — a safety-relevant behaviour — from testing | Each concept's user and moment re-read against the original text before merging | Team kept three sketches; recorded as D05 in the portfolio Decision Log | Team-authored text only; no patient data |
| Literature retrieval for unsupported claims | Claude with PubMed and Consensus | Four verified citations: PMID 40314952, 33443582, 39496090, 40772775 | The first PubMed queries AND-ed every term and returned off-topic work (haemolytic disease, social prescribing); discarded and re-run with shorter queries | Abstracts and reported figures read before citing; PMID and DOI resolved for each | Only on-topic papers used, each marked as indirect evidence for the pain, not for the solution | Public bibliographic databases; no patient data |
| Interoperability feasibility check | Claude with a public FHIR R4 sandbox and the ICD-10 database | Confirmed that FHIR `Observation` separates `effectiveDateTime` (clinical time) from `issued` (availability time), and that vital signs carry LOINC codes | Results from CMS Coverage, NPI Registry and ClinicalTrials were discarded as US-specific and inapplicable to the Thai setting | Live structure read from the sandbox and compared against the project's `available_at_time` rule | Recorded in Market & Adoption with the explicit limit that the ICD-10 set checked is US CM, while Thailand uses ICD-10-TM | HAPI FHIR public test server, synthetic test data only; nothing sent |
| Prototype V1 build | Claude with the Figma MCP and the artifact canvas | The eight redesign screens (TASK-0036), then their recomposition into one publishable page (DEC-0019) | Plan to build every frame in Figma was abandoned at the Starter-plan quota; two screens moved to the canvas | Screens opened and inter-screen links checked; research-prototype labelling confirmed on every screen | Approved for publication as APR-0003 | Synthetic demo cases authored by the team |
| Test Card drafting | Claude (Claude Code) | The assumption → method → signal → threshold structure, and the choice of which measures get numeric bars | First draft included clinical-accuracy thresholds (sensitivity, under-triage rate); removed — six participants on synthetic cases cannot support a clinical claim, and EVAL-0001's statistics plan reserves those thresholds | Each threshold traced to a source; the +2-minute bar comes from I01's own words | Thresholds frozen before data collection; the reason for having no clinical threshold written into the sheet | Team research plan only; no patient data |
| Portfolio consistency pass | Claude (Claude Code) | Evidence ID column making E03–E13 resolvable; filled concept rows; two new sheets; a list of internal contradictions | AI was not permitted to alter the team's confidence ratings or judgements. It changed only statuses that contradicted their own confidence numbers (E21, E22, E27), and every change is itemised in the portfolio | Original workbook diffed cell by cell against the new one to confirm nothing filled was dropped | Original file kept as the comparison copy; change list reviewed before submission | Team's own portfolio file; no patient data |

## Limits of this log

It covers the work recorded above and the standing provenance in git. It is not a reconstruction of
every assisted session since the project began; earlier sessions are traceable only through commit
trailers. Nothing in this log substitutes for user evidence — every claim about clinical usefulness
still depends on TASK-0037.
