# Clinical Front Door — User Research and Usability Plan

**Status:** ready to recruit; no participant results recorded yet. Round 2 instrument for Prototype V2: `USABILITY_TEST_V2.md`  
**Product stage:** hospital-pilot concept using synthetic cases only  
**Participants:** 5–8 supervised emergency-department staff across triage/intake nursing and physician review roles

## Research objectives

1. Understand the real first-contact intake and handoff workflow, vocabulary, device constraints and interruption patterns.
2. Verify that staff distinguish raw transcript, assistant proposal, confirmed fact and conflicting evidence.
3. Test whether urgency, red flags, missing information, uncertainty and model limitations are understood without facilitator coaching.
4. Identify automation-bias, privacy, accessibility and wrong-revision risks before any hospital pilot proposal.

This study evaluates workflow and usability. It does not evaluate clinical accuracy, authorize real patient data or support real care decisions.

## Round 1 — Contextual interviews

- Recruit 3–5 triage/intake nurses and 2–3 physicians where possible. Record role and experience band, not participant names, in the product database.
- Run 45–50 minute sessions: warm-up (5), current workflow (10), deep dive (20), concept reaction (10), wrap-up (5).
- Ask participants to walk through a recent representative workflow without sharing identifiable patient information.

### Interview guide

**Warm-up**

- What is your role at the first-contact point, and what decisions are you responsible for?
- Which device and workspace do you normally use during intake?

**Current workflow**

- From arrival to physician review, what information appears first and what usually arrives later?
- What must be present before you can hand a case over? What commonly remains unknown?
- Where are corrections, contradictions and verbal information recorded today?

**Risks and interruptions**

- What signals make you stop the normal workflow and request immediate review?
- Which omissions or interface misunderstandings would be most dangerous?
- When interrupted, what context must remain visible so you can resume safely?

**Concept reaction**

- Show the staff-assisted Voice intake, fact review, safety snapshot and physician handoff in that order.
- Ask the participant to explain what is confirmed, what is only suggested, and who remains responsible for the decision.
- Ask which labels, care-pathway terms or handoff fields do not match local practice.

**Wrap-up**

- What would prevent you from using this during a supervised synthetic pilot?
- What did we fail to ask about the actual workflow?

## Round 2 — Moderated usability test

Use synthetic scenario cards only. Do not explain button locations. Ask each participant to think aloud and complete:

1. Sign in and identify the mock/unvalidated capability state.
2. Open or create a synthetic adult case.
3. Record a short staff-assisted voice note, edit the transcript and explicitly send it.
4. Explain whether the transcript and assistant proposals are confirmed clinical facts.
5. Edit and accept selected proposals; leave one proposal unconfirmed.
6. Correct an existing fact and find its earlier revision.
7. Read the safety snapshot and state the urgency floor, red flags, missing information and limitations.
8. Create a T0 handoff draft, inspect evidence, pathways, uncertainty and next-information candidates.
9. Add a synthetic lab or report, create a T1 draft and compare it with T0.
10. As a physician, request information or modify the draft with a structured reason, then confirm the new version.
11. Open the audit trail and identify who changed what and when.

Stop immediately if real identifying data is entered, another workspace is visible, an unconfirmed item becomes a fact, a stale draft can be confirmed, or an audit event is missing.

## Observation record

Create one record per participant outside the application database:

| Field | Allowed value |
|---|---|
| Participant code | anonymous study code |
| Role | intake nurse / physician / evaluator |
| Device | desktop / tablet / mobile |
| Task | 1–11 |
| Outcome | complete / complete with help / incomplete / stopped |
| Time | elapsed seconds |
| Misunderstanding | concise observation, no patient data |
| Assistance | facilitator prompt given |
| Safety or integrity issue | none / privacy / automation bias / wrong revision / missing audit / other |
| Accessibility barrier | concise observation |
| Quote | optional, consented and de-identified |

## Synthesis and prioritisation

- Affinity-map observations under intake, review, safety comprehension, handoff, audit, voice and accessibility.
- Produce a journey map from first contact through T0 handoff and T1 reassessment.
- Write jobs-to-be-done in the form: “When…, staff need…, so they can…”.
- Prioritise each finding by `safety impact × workflow impact × frequency`, then record implementation effort separately.
- Critical/high findings affecting privacy, confirmation boundaries, stale versions, red-flag comprehension or audit integrity block the next round until fixed and independently retested.

## Reporting rules

- Report participant count, role mix, task outcomes, assistance and observed failure modes.
- Keep usability findings separate from model quality and clinical accuracy.
- Do not claim hospital readiness, clinical usefulness or validated Thai ASR unless that capability was directly tested and reviewed.
- Preserve negative findings and limitations; do not convert mock-provider behavior into a clinical score.
