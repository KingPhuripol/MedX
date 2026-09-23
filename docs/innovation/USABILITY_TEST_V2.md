# MedX Prototype V2 — Moderated usability test (Round 2)

**Status:** instrument ready; developer walkthrough done 2026-09-23; **no participant results yet**
**Stimulus:** the running MedX app (`/nurse` + `/platform`), offline mock provider, synthetic cases only
**Participants:** 3–5 ED/OPD physicians and triage nurses, 30–40 min each, 24–28 Sep 2026
**Feeds:** Decision Gate 2 (30 Sep 2026) — test evidence and the revise/retain decision
**Parent plan:** `USER_RESEARCH_PLAN.md` Round 2, adapted: speech is off in the pilot build, so the voice task is dropped.

This is a workflow and usability test of a research prototype. It does not measure clinical accuracy. The mock provider only reshapes what staff type; it does no clinical reasoning.

## 1. Questions this round must answer (predeclared)

| ID | Question | Evidence that answers it |
|---|---|---|
| Q1 | Can a nurse get from new case to a confirmed handoff draft without help? | Task success and time for N1–N4 |
| Q2 | Do staff tell apart an assistant proposal, a confirmed fact and a draft? | Think-aloud at N2 and P1, plus debrief question D1 |
| Q3 | Does the physician over-trust the urgency floor? The screen checks only *which kinds* of data exist, never how severe they are. | P1 answer for card A, plus debrief question D2 |
| Q4 | Can the physician act on the draft (confirm, request information, escalate) and find who changed what? | P2–P4 success |
| Q5 | What do they use today, and what would make them switch? | Debrief questions D3–D5, for DG2 switching behaviour |

**Decision rule, fixed before any session:**
- Revise a screen when either of these happens:
  - a critical task is completed by fewer than 80% of participants without help, or
  - at least two participants hit the same safety or integrity issue (over-trust, wrong revision, treating an unconfirmed item as a fact).
- Retain otherwise.
- Record every rule outcome, including the ones that do not trigger.

## 2. Setup (facilitator, before each session)

1. Start the offline pilot server with the `front-door-pilot` preview config in `.claude/launch.json`:
   - `127.0.0.1:8138`
   - `FRONT_DOOR_AUTH_MODE=none`, mock provider, every external URL empty
   - data persisted in `artifacts/pilot/pilot.sqlite3`, which git ignores
2. Check `/v2/capabilities`. It must show `"provider":"mock-v2"` and `"validation":"MOCK_ONLY"`.
3. Delete `artifacts/pilot/pilot.sqlite3` between participants. Every participant starts empty.
4. Record the code revision (`git rev-parse --short HEAD`) and the date in the session log.
5. Open two tabs: `/nurse` and `/platform`. Use a laptop, and a tablet if one is available.
6. Hand over the paper scenario card. Do not explain where buttons are.

Stop the session immediately in any of these cases:
- real identifying data is typed
- an unconfirmed item appears as a confirmed fact
- a stale draft can be confirmed
- an audit event is missing

## 3. Scenario cards (synthetic)

**How to type into the assistant (mock limitation — print this on every card):**
- Start each message with one prefix: `อาการ:`, `ประวัติ:`, `ยา:`, `แพ้ยา:` or `รายงาน:`.
- Enter vital signs with **"เพิ่มข้อมูลด้วยตัวเอง" → สัญญาณชีพ**.

### Card A — Chest pain (checks Q3: over-trust)
- Case ID `A-<participant code>`, fictional age 58.
- `อาการ: เจ็บแน่นหน้าอกร้าวไปแขนซ้าย 30 นาที เหงื่อแตก (ข้อมูลสังเคราะห์)`
- `ประวัติ: ความดันโลหิตสูง 10 ปี (ข้อมูลสังเคราะห์)`
- Vital signs: ชีพจร 112 bpm
- **What to watch:**
  - Once the vital signs are in, the screen reads "ระดับความเร่งด่วนอย่างน้อย: ข้อมูลยังไม่พอสรุป". That is by design: the screen does not read symptom text.
  - Does the physician still escalate?

### Card B — Breathlessness, vital signs missing (checks missing information and Q4)
- Case ID `B-<code>`, age 67.
- `อาการ: หอบเหนื่อยมากขึ้น 2 วัน (ข้อมูลสังเคราะห์)`
- `ยา: salbutamol inhaler (ข้อมูลสังเคราะห์)`
- Do **not** enter vital signs.
- **Expected:**
  - the floor shows "ต้องให้แพทย์ดูโดยเร็ว", with the missing required information listed
  - the physician uses "ขอข้อมูลเพิ่มเติม" (request more information)

### Card C — Low-risk fever, then a correction (checks revision safety and audit)
- Case ID `C-<code>`, age 24.
- `อาการ: ไข้ต่ำ ๆ 1 วัน ไม่มีอาการอื่น (ข้อมูลสังเคราะห์)`
- `แพ้ยา: ไม่มี (ข้อมูลสังเคราะห์)`
- Vital signs: อุณหภูมิ 37.8 °C
- **Steps:**
  1. The physician confirms the draft.
  2. The nurse then corrects the temperature to 38.6 °C.
- **Expected:**
  - the confirmed draft becomes "ต้องตรวจใหม่" (needs re-review)
  - the old value stays in the history

## 4. Tasks by role

| # | Role | Task | Card |
|---|---|---|---|
| N1 | Nurse | Create the synthetic case and complete the no-identifying-data attestation | A, B, C |
| N2 | Nurse | Send the intake messages, then explain whether the proposal is already a fact | A |
| N3 | Nurse | Accept the proposals, and add vital signs by hand | A, C |
| N4 | Nurse | Prepare the handoff draft | A, B, C |
| N5 | Nurse | Correct a confirmed fact and show where the earlier value still appears | C |
| N6 | Nurse | Reload the page with an unsent message in the box, and recover the message | any |
| P1 | Physician | Read the draft aloud: urgency floor, missing information, limitations. Say "what the system checked and what it did not." | A |
| P2 | Physician | Escalate with a reason ("ส่งต่อให้ทบทวน") | A |
| P3 | Physician | Request more information ("ขอข้อมูลเพิ่มเติม") | B |
| P4 | Physician | Confirm, then after the correction explain why the draft needs re-review. Open the audit trail and say who changed what. | C |

With one participant per role, run the N tasks and then the P tasks on the same cases.

## 5. Session script

1. **Intro, 3 minutes.** Tell the participant:
   - This is a research prototype that uses synthetic data only.
   - We are testing the system, not them.
   - Please think aloud.
   - Ask for verbal consent to take notes, and to record the screen if they agree. No names are recorded.
2. **Tasks, 20–25 minutes.**
   - Use the order in section 4.
   - After each task, ask for an SEQ rating: "How easy was this task, 1–7?"
3. **Debrief, 8–10 minutes.**
   - D1: "What is the difference between the assistant's proposal, confirmed data, and the draft?"
   - D2: "The system shows 'ข้อมูลยังไม่พอสรุป' for card A. What does that mean to you? Would it change what you do?"
   - D3: "Today, how do you record intake and hand over to the doctor? (paper, HIS, triage form, LINE, verbally)"
   - D4: "What would have to be true for you to switch to this? What would stop you?"
   - D5: "Which part would you drop or change first?"

## 6. Observation record (one row per participant × task)

Keep these records outside the app database. Use participant codes only (P01…).

| Participant | Role | Device | Task | Outcome (complete / with help / incomplete / stopped) | Time (s) | SEQ 1–7 | Misunderstanding | Help given | Safety/integrity issue | Quote (de-identified) |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

## 7. Pre-test developer walkthrough, 2026-09-23 (not user evidence)

One developer ran card A end to end, from `/nurse` to `/platform` to ESCALATE:
- The ESCALATE review was stored with reviewer, reason code `UNSAFE_TO_CONFIRM`, reason text and timestamp.
- The console had no application errors.

The walkthrough found these issues:

| ID | Finding | Status |
|---|---|---|
| W1 | The draft summary showed vital signs as raw JSON (`{"name":"ชีพจร",...}`) | Fixed: now shows "ชีพจร 112 bpm" (`innovation/v2/providers.py`, test in `tests/test_v2.py`) |
| W2 | The limitations list showed one screen limitation twice | Fixed: de-duplicated in `innovation/workspace/src/shared/clinical.tsx` |
| W3 | The platform sidebar link to MedX Intake was white text on a white background | Fixed in `innovation/workspace/src/shared/medx.css` |
| W4 | Sidebar identity text and pilot label failed axe colour contrast | Fixed in `medx.css`; e2e axe checks pass |
| O1 | The assistant placeholder suggests free text ("ผู้ป่วยไอมา 2 วัน มีไข้ต่ำ"), but the mock only reads prefixed text | Open: handled by the printed prefix rule on each card. Watch whether participants follow the placeholder instead. |
| O2 | In card A, adding vital signs lowers the floor from "ต้องให้แพทย์ดูโดยเร็ว" to "ข้อมูลยังไม่พอสรุป", even though the text describes possible ACS | By design: the screen does not read free text and says so. This is the Q3 over-trust question and **must not be changed without a clinical rule decision** (`SAFETY_SPEC.md`). |
| O3 | Limitation strings are in English inside a Thai UI | Open: record whether participants read them |

## 8. Results

*None yet. Fill in after the sessions on 24–28 Sep. Report:*
- participant count and role mix
- task outcomes and help given
- SEQ median per task
- the outcome of each decision rule
- the switching answers from D3 and D4

*Keep usability results separate from model quality. This round makes no claim of clinical usefulness.*
