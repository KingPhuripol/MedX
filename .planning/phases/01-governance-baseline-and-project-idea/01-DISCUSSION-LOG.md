# Phase 1: Governance Baseline and Project Idea - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-11
**Phase:** 1-Governance Baseline and Project Idea
**Areas discussed:** Project Idea evidence standard, Shared contract versioning, Dataset feasibility inventory format, GOV-02 resolution path

---

## Project Idea evidence standard

### How to enforce claim traceability

| Option | Description | Selected |
|--------|-------------|----------|
| Claims table + inline citation | Normal academic citations plus a table mapping every claim to a source or a `hypothesis`/`planned work` label; checkable without writing code | ✓ |
| Inline citation only | Standard academic practice, lightest and fastest to write, but checking for unlabelled claims means reading the whole document | |
| Machine-readable claims via harness | JSON claims file + schema + validator in `verify_harness.py`, rendered into the document; best fit for the repo pattern but the heaviest build inside 17 days | |

**User's choice:** Claims table + inline citation
**Notes:** Chosen over the machine-readable option on schedule grounds — DL-0002 is 17 days out.

### Where the claims table lives, given the 2-4 page + references format

| Option | Description | Selected |
|--------|-------------|----------|
| Separate repo artifact | Submitted document stays 2-4 pages per the faculty format; the claims table sits in `docs/` with a pointer from the document | ✓ |
| Inside the references section | Counts as references rather than body, but risks being read as a format violation | |
| Both | Full table in the repo, abridged version in references; more work for author and reviewer | |

**User's choice:** Separate repo artifact
**Notes:** Raised because the faculty format caps the body at 2-4 pages and an appendix table would eat that budget.

### Pre-submission review

| Option | Description | Selected |
|--------|-------------|----------|
| Internal reviewer who did not write it | A second team member signs off before submission; fits `TEAM_OWNERSHIP.md` and spreads load away from Phurinat at 56% | ✓ |
| Advisor only | Skip internal review and go straight to the advisor — faster, but advisor identity is still unrecorded (GOV-03) | |
| No gate | Author self-checks and submits — fastest, highest risk to document quality | |

**User's choice:** Internal reviewer who did not write it
**Notes:** Captured in CONTEXT.md as role-based, not name-based, so planning does not hard-code a reviewer.

---

## Shared contract versioning

**Findings presented before the questions:** four of five contracts carry `**Version:** 1.0.0` in a
markdown header; `HUMAN_APPROVAL_POLICY.md` carries none. Schemas pin
`"contract_version": {"const": "1.0.0"}`. No registry ties the two together — they agree by
coincidence, not by enforcement.

### Independent versions or one set version

| Option | Description | Selected |
|--------|-------------|----------|
| Semver per contract file | Each contract bumps on its own change; matches the already-split schema files | ✓ |
| Single lockstep set version | All five move together as a contract set; simpler to explain but bumps files that did not change | |
| You decide | Defer to Claude | |

**User's choice:** Semver per contract file

### Authoritative source of version truth

| Option | Description | Selected |
|--------|-------------|----------|
| Registry JSON + harness check | `project_state/contract_versions.json` is authoritative; `verify_harness.py` asserts registry, doc header, schema const, and fixtures all agree | ✓ |
| Markdown header only | Keep current shape, just add the missing header; least work, but doc-vs-schema drift stays undetectable | |
| Schema const only | Treat schemas as truth and headers as commentary; fails because `HUMAN_APPROVAL_POLICY.md` has no schema, so it cannot cover all five | |

**User's choice:** Registry JSON + harness check

---

## Dataset feasibility inventory format

**Findings presented before the questions:** `docs/shared/DATA_CONTRACT.md` §"dataset version
record" already defines the full field vocabulary (source/license/citation, access date, governance,
population, inclusion/exclusion, modalities and pairing, counts by split, availability mapping,
preprocessing, duplicate audit, quality/missingness, known bias, permitted use, retention/deletion,
checksums). The feasibility inventory is a pre-flight form of that record and should not invent
parallel vocabulary.

### Storage format

| Option | Description | Selected |
|--------|-------------|----------|
| JSON + schema + validator | Matches the repo's schema/fixture/validator pattern; harness can check completeness | ✓ |
| Markdown only | Fast to write and easy to paste into the proposal, but the harness cannot verify completeness | |
| JSON as truth, rendered to markdown | Both benefits, at the cost of writing a renderer | |

**User's choice:** JSON + schema + validator

### Does the inventory reach a verdict

| Option | Description | Selected |
|--------|-------------|----------|
| Verdict per modality combination | Coverage matrix concluding `FEASIBLE` / `FALLBACK_REQUIRED` / `INFEASIBLE`; a fallback verdict closes the gate honestly | ✓ |
| Collect data only | Record dataset facts and defer the judgement to a later phase; leaves the gate unclosable | |
| You decide | Defer to Claude | |

**User's choice:** Verdict per modality combination
**Notes:** Directly determines whether RISK-0002 can ever be resolved rather than staying open indefinitely.

---

## GOV-02 resolution path

**Framing given:** the requirement accepts either a transcription verified against a restored source
under `sources/`, or the unverified status carried as an owned open risk with a named owner. Which
applies depends on a fact, not a preference.

### Can the source PDF be restored

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, available or obtainable | Restore, verify visually, flip `transcription_status` to `VISUALLY_VERIFIED` — genuinely closes GOV-02 | |
| No or uncertain | Carry unverified status as an owned open risk; requirement permits this without the PDF | ✓ |
| Plan both branches | Set an internal deadline to find it; verify if found, otherwise convert to owned risk automatically | |

**User's choice:** No or uncertain

### Risk owner if the status stays unverified

| Option | Description | Selected |
|--------|-------------|----------|
| Phurinat (PM lead) | Owns the PM workstream and owned RISK-0001; consistent, though already at 56% workload | ✓ |
| Another team member | Spread load away from Phurinat | |
| Leave unassigned | Let the planner decide; would leave GOV-02 unclosable since the requirement demands a named owner | |

**User's choice:** Phurinat (PM lead)

**Notes:** Flagged to the user before writing CONTEXT.md — closing GOV-02 this way satisfies the
requirement as written but does not reduce the real risk. All seven immutable deadlines rest on a
source nobody can check, and the three places the dates appear all descend from the same
transcription, so their agreement is not independent corroboration. Recorded in CONTEXT.md so the
planner sees it.

---

## Claude's Discretion

None. Every area presented was decided by the owner.

## Deferred Ideas

- **GOV-01 — Front Door runtime and framework choice.** Deliberately undecided; already scheduled as Phase 2 work.
- **Obtaining the official schedule from course staff or a classmate.** Not required to close GOV-02, but the only action that actually reduces the deadline-provenance risk.
- **Rebalancing workload away from Phurinat.** 56% P0/P1 concentration against a documented 40% threshold; an owner-map question, not a Phase 1 deliverable.
