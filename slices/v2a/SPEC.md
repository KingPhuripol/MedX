# V2A — Ambient intake mode for the voice session API (backend only)

Planner: innovation-lead (2026-09-30). Branch: `factory/v2a`. Gantt owner: ภูริณัฐ (Voice Agent, PROPOSAL row 16).
Direction: `docs/DECISIONS.md` 2026-09-30 "V2 voice direction: ambient scribe in a separate mobile PWA".
Source of truth: `docs/PROPOSAL.md` §1.3.1 ("ถามเพิ่มเฉพาะข้อมูลที่ยังขาด"), §3.1, §3.5, Table 3.2. The proposal wins on any conflict.
Research prototype, synthetic data only. The nurse is present and in charge. The system suggests; it never speaks, diagnoses or triages.

## 1. Problem and user

A nurse records an ordinary Thai nurse–patient conversation on one phone mic. There is no diarization, so every segment arrives as `speaker:"unknown"`. The backend must:
- extract intake facts from the patient's answers, and never from the nurse's questions;
- show the nurse which required fields are still missing, with a suggested question taken from the allowlist. The suggestion is shown on screen and never spoken;
- keep red-flag and nurse-attention cues above everything else.

v2c (mobile UI) and v2d (review and handoff) build against this API in parallel, so the contracts in §3 are **locked**.

## 2. Scope

In scope, all under `backend/app/voice/`, its tests, fixtures and eval, plus the minimal changes listed below:
1. Session `mode` (`guided` default | `ambient`), stored on the session and immutable.
2. The `speaker:"unknown"` enum value on `/turns`, and on the stored transcript type (`casegraph.data.Turn.speaker`; an additive enum change only).
3. A deterministic Thai **nurse-question intent classifier**: a new module `backend/app/voice/intent_th.py`, stdlib `re` only, with no model.
4. An ambient ask-window: which field a following answer is extracted against.
5. Ambient `next_action` (`prompt_nurse` / `complete` / `handoff`), with the AI never speaking.
6. The DEF-E1R-001 fix, parts (a) and (b), in **both** modes.
7. 15 ambient fixtures, an ambient replay simulator, the ambient eval (`make eval-voice-ambient`) and tests.

Out of scope:
- audio, STT/ASR, LiveKit and any network or vendor SDK;
- any `web/` or `mobile/` UI;
- nurse confirmation and handoff to triage (v2d);
- external providers;
- diarization;
- DEF-E1R-001 part (c): focal deficit coerced to `fatigue`. This needs a chief-complaint vocabulary decision shared with S4 (see §8);
- changing the red-flag phrase list or the allowlist wording (D4, clinical sign-off pending);
- changing what the Case Graph readers accept (`casegraph/reader_text.py` and `voice/symptoms.py` still read `patient` turns only; see §8 D-V2A-3).

## 3. Contracts (LOCKED)

### 3.1 Start session
`POST /api/voice/sessions` body: `{patient_ref, data_class:"synthetic", mode?: "guided"|"ambient"}`.
- The default is `"guided"`. Any other value returns 422.
- `session.mode` is returned in every session payload (start, turns, GET, finish).
- `mode` is immutable. Add it to the fixed-column trigger (SQLite and PG).
- The DB column is added idempotently to existing SQLite and PG databases (`ALTER TABLE … ADD COLUMN` guarded). An existing row without a mode reads as `guided`.

### 3.2 Add turn
`POST /api/voice/sessions/{id}/turns`: `speaker ∈ {patient, relative, nurse, unknown}`.
- Ambient clients send `source:"asr"`, `asr_model`, `speaker:"unknown"`. The existing `asr_model` iff `source=="asr"` rule is unchanged.
- `unknown` is accepted in both modes. In guided mode it is treated like a patient turn (no classifier).

### 3.3 Ambient `next_action`
Exact key set (no other keys):

```json
{"kind": "prompt_nurse" | "complete" | "handoff",
 "field": "<ASK_ORDER field>" | null,
 "suggested_question_id": "ask.<field>" | "reask.<field>" | null,
 "suggested_question_th": "<UTTERANCES_TH[suggested_question_id]>" | null,
 "reason": null | "complete" | "nurse_attention_phrase" | "extraction_unavailable",
 "missing_fields": ["<field>", ...]}
```

Kinds:
- `prompt_nurse`: `field` is the first field in `ASK_ORDER` whose status is `MISSING`.
  - `suggested_question_id` is `ask.<field>` if the field was never asked (classified question count 0), otherwise `reask.<field>`.
  - The text comes **only** from `utterances_th.UTTERANCES_TH`. There is no free-text path; an unknown id raises.
  - There is no ask limit, so prompting continues while the field is MISSING. `attempts_exhausted` is never used in ambient mode.
- `complete`: no `ASK_ORDER` field is MISSING (KNOWN, UNKNOWN and REFUSED all count as captured). `reason:"complete"`, `field` and the suggestion are null, `missing_fields: []`.
- `handoff`: `reason:"nurse_attention_phrase"` whenever any turn in the session hit nurse attention; else `reason:"extraction_unavailable"` after any gateway, schema or grounding failure.
  - Both are sticky for the session (same as guided) and **preempt** `prompt_nurse` and `complete`.
  - `missing_fields` lists the fields still MISSING.
- The ambient next action has **no** `utterance_th` and no `action` key, so it cannot be fed to a speaking client.
- Ambient sessions never write `speaker:"agent"` turns: not at start, not per turn, not at finish.

### 3.4 Guided mode
Guided mode is byte-compatible:
- `next_action` keeps exactly `{action, field, utterance_id, utterance_th, reason, missing_fields}`;
- the ask/reask/handoff policy and `/live` are unchanged.

### 3.5 Model Gateway request
The gateway request is unchanged in both modes:
- `task="voice.intake_extract"`, `inputs` keys exactly `{"turns","last_asked_field"}`, `data_class="synthetic"`;
- there is no Model API Contract change.

### 3.6 New response fields (both modes, additive)
- `chief_complaint_conflict: bool`, top level and in `session`.
- `held_facts` on GET session: every held item of the session, `{turn_id, field, state, value, span_turn_ids, reason}`, with no transcript text.
- Held items are stored append-only: a new nullable `held_json` column on `voice_extractions`, added idempotently.

## 4. Behaviour

### B1. Question classification (ambient: every non-agent turn; guided: `speaker=="nurse"` turns only)

`classify(text) -> field | None`. A turn is a nurse question for field F iff both hold:
1. It carries a question form: a final question particle (ไหม/มั้ย/หรือเปล่า/รึเปล่า/ใช่ไหม/บ้าง/เท่าไร/เท่าไหร่/กี่…/อะไร + optional ค่ะ/คะ/ครับ), or `?`.
2. It matches a field-intent pattern for F.

A turn is **never** a question if the question form is governed by a patient non-answer or denial:
- `UNKNOWN_PHRASES` / `REFUSED_PHRASES` before it, e.g. "ไม่แน่ใจว่าแม่เคยแพ้ยาอะไรหรือเปล่า";
- or a leading negation, e.g. "ไม่แพ้ยาอะไรค่ะ".

If several intents match, the one ending last wins.

A classified question turn:
- is stored with `voice_turns.field = F`;
- makes **no gateway call** and yields **zero facts**;
- writes a `voice_extractions` row `status:"skipped"`, `reason:"nurse_question"`. `_extraction_error` counts only `error`;
- is audited in `voice.turn.add` with `question_field: F` (the field name only, never the text).

It still runs the nurse-attention check (B5). `times_asked[F]` counts classified question turns in ambient mode.

**Merged segment.** ASR may join a question and its answer, e.g. "แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ".
- If a question clause for F is followed by further text in the same turn, the turn sets the window to F. The answer part is extracted against F.
- The question clause itself must never produce a fact. Allowed outcomes: KNOWN none from "ไม่แพ้ค่ะ", UNKNOWN, or no fact. **Never** `present`.

### B2. Ask window (ambient)

`last_asked_field` sent to the gateway is the field of the latest classified question turn. It is reset to `None` when any of these happen:
- (i) a later nurse-attention turn;
- (ii) `AMBIENT_ASK_WINDOW = 2` non-question turns have been posted after the question;
- (iii) for scalar fields (`chief_complaint`, `onset_duration`, `severity`, `allergy_status`), a fact for F was written from a turn inside the window.

List fields (`current_medications`, `relevant_history`) keep the window until (i) or (ii), so a list can continue over 2 turns. Only turns ended at or before the current turn's `ended_at` are used.

Volunteered facts (window `None`) are extracted wherever the existing rules allow, e.g. "เจ็บคอ ไอด้วยค่ะ เป็นมาสองวันแล้ว" → chief complaint + duration.

### B3. Allergy guard

`reconcile_allergy` is unchanged and runs in both modes. Missing, uncertain, hedged, questioned or merged-segment allergy is never `none`. A recorded allergy is never weakened.

### B4. DEF-E1R-001 fix (both modes)

- **(a)** After a nurse-attention handoff, `last_asked_field` does not stay at the old field.
  - Guided: the handoff agent turn (field null) resets it to `None`. Later nurse question turns (B1) set it again.
  - Ambient: B2(i) applies.
- **(b)** A KNOWN `chief_complaint` whose value differs from the current KNOWN chief complaint is **not** written as a superseding fact.
  - It is held: `reason:"chief_complaint_conflict"`, stored in `held_json`, returned in `held_facts`, and `chief_complaint_conflict:true`.
  - The earlier chief complaint stays the latest fact. The held payload is audited without `value_text`.
  - The same value is deduplicated as today.
  - This also applies to spoken corrections of the chief complaint. The nurse resolves them in v2d.

### B5. Red flag

`nurse_attention_hit` runs on every non-agent turn in both modes, including classified question turns, before extraction.
- It is not suppressed and not downgraded: a question that contains a listed phrase still fires. This is conservative, and the false-alarm cost is recorded (§8 D-V2A-2).
- The attention turn itself is extracted with the pre-attention window.

### B6. Finish

`finish()` on an ambient session:
- returns valid `VoiceIntakeFacts` + `IntakeTranscript` evidence, with `unknown` speakers preserved and no agent turns;
- sets `handoff_reason` = the ambient `reason`, or `finished_by_nurse` when the kind is `prompt_nurse`.

## 5. Fixtures and evaluation

Location: `backend/tests/voice/fixtures/ambient/th_ambient_{01..15}.json`. This is a subdirectory, so the S3 `th_intake_*.json` glob and S3-A03 are unaffected.

Each fixture is converted from `th_intake_NN`:
- `speaker:"unknown"` on every turn;
- `turn_id`s and timestamps are unchanged;
- each former `agent` turn is rewritten as a natural nurse question (e.g. มาด้วยอาการอะไรคะ / เป็นมากี่วันแล้วคะ / ปวดกี่คะแนนคะ / แพ้ยาอะไรไหมคะ / ทานยาอะไรประจำไหมคะ / มีโรคประจำตัวไหมคะ);
- former patient, relative and nurse turns keep their text.

Added keys:
- `mode:"ambient"`;
- `source_dialogue_id`;
- `source_sha256` (sha256 of the source file bytes);
- `gold_question_turns: {turn_id: field}`.

Unchanged: `gold_facts`, `answers_by_field` and `gold_nurse_attention` are byte-identical to the source.

Held out:
- 11–15 are tagged `heldout`.
- For every field, at least one held-out question wording does not appear verbatim in any dev fixture.
- **All 15 ambient fixtures are committed in a commit that is an ancestor of the first commit that adds `intent_th.py`.** Held-out results must not be used to change rules. Every ambient eval run is reported, including failed ones.

Replay: `simulate_ambient(ctx, fixture)` starts an ambient session and posts **every** fixture turn in order (speaker unknown, `source:"asr"`, `asr_model:"fixture-text"`) with a fake clock. It then finishes. There is no policy-driven skipping.

Eval: `make eval-voice-ambient` → `slices/v2a/eval/ambient_intake_eval.json`.
- Label: "system evaluation — mock rules, synthetic ambient text dialogues (no audio/ASR), not clinical performance".
- Reuses the S3 scorer (`field_counts`, `prf`, 2,000-resample dialogue-level bootstrap, seed 0).
- Contents:
  - dev/held-out per field;
  - **gated micro** over `chief_complaint, onset_duration, severity, allergy_status, allergens, current_medications`;
  - reported `relevant_history` and `micro_overall`;
  - `allergy_false_none`;
  - classifier confusion on `gold_question_turns`;
  - per-turn latency p50/p95;
  - `inputs_sha256`.

## 6. Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| V2A-A01 | Guided mode and every existing test are unchanged | `make test` exits 0. No existing test file is modified, except `tests/e1r/test_syne0196_replay.py` per A07. Guided `next_action` key set is exactly the 6 existing keys. `make eval-voice` guided dev and held-out `tp/fp/fn` per field and `allergy_false_none` equal the committed pre-v2a `slices/s3/eval/voice_intake_eval.json` values (dev micro 57/1/0, held-out 30/0/0, false-none 0) | `make test`; `test_guided_next_action_keys_unchanged`; `test_guided_eval_counts_unchanged` compares the re-run with the values read from the pre-v2a commit (`git show <base>:slices/s3/eval/voice_intake_eval.json`) |
| V2A-A02 | Ambient field micro-F1 on the gated fields (chief complaint, duration, severity, allergy status + allergens, medications) | dev 1–10 **≥ 0.90**; held-out 11–15 **≥ 0.80** | `ambient_intake_eval.json` `splits.dev.micro_gated.f1`, `splits.heldout.micro_gated.f1`; `test_ambient_eval_thresholds` (fresh-or-rerun on `inputs_sha256`, as S3) |
| V2A-A03 | No allergy false-none | `allergy_false_none == 0` on all 15 ambient fixtures, and 0 in the merged-segment and leading-question unit cases | eval JSON; `test_ambient_eval_thresholds`; `test_merged_segment_allergy_never_present_or_false_none`; `test_leading_question_no_facts` |
| V2A-A04 | Nurse-question turns produce zero patient facts | For each of the 6 fields, ≥ 3 question phrasings (§7 list), including one leading question and one ASR-style variant without a particle or with `?`: classified with the correct field, 0 facts, 0 gateway calls. The ≥ 12 answer phrasings in §7 are **not** classified as questions. Classifier on the ambient fixtures: dev question detection 100% with the correct field and 0 answer turns flagged; held-out correct-field rate ≥ 0.80 (reported) | `test_intent_th.py` (parametrised); `test_question_turn_no_facts_no_gateway`; eval JSON `classifier` block |
| V2A-A05 | `prompt_nurse` is only for missing fields and only with allowlisted text | Across every response of the 15 ambient replays: `kind=="prompt_nurse"` ⇒ `field_statuses[field].status=="MISSING"`, `suggested_question_th == UTTERANCES_TH[suggested_question_id]` and the id is `ask.`/`reask.` + field. A field is never prompted after it leaves MISSING. The final kind matches gold: `complete` iff gold covers all 6 ASK_ORDER fields and there is no attention, else `prompt_nurse` for the first gold-missing field. Dev 10/10, held-out ≥ 4/5. The ambient next action has exactly the §3.3 keys, with no `utterance_th`/`action` | `test_ambient_prompt_only_missing`, `test_ambient_prompt_allowlist`, `test_ambient_next_action_keys`, `test_ambient_final_action_matches_gold` |
| V2A-A06 | Red flag preempts in ambient mode | Ambient fixtures 06, 09, 12: the response to the attention turn and every later response has `kind:"handoff"`, `reason:"nurse_attention_phrase"` and `nurse_attention:true`, never `prompt_nurse`/`complete`. Unit test: MISSING fields + "เมื่อกี้ลูกชักด้วยค่ะ" → handoff. A classified question containing a listed phrase still fires. A gateway error in ambient → `handoff/extraction_unavailable`, 0 facts from that call | `test_ambient_attention_preempts`, `test_ambient_question_with_red_flag_still_fires`, `test_ambient_gateway_failure_fails_safe` |
| V2A-A07 | DEF-E1R-001 (a)+(b) fixed | Guided: after `handoff.nurse_attention_phrase`, the next patient turn's gateway request has `last_asked_field` None (or the field of a later classified nurse question). A later different chief complaint is held (`chief_complaint_conflict:true`, `held_facts` contains it, the earlier chief complaint is still the latest fact, `voice_facts` has no superseding chief-complaint row). The same in ambient. SYNE-0196-shaped synthetic regression (red-flag turn 1 → nurse drug-reaction question → "แพ้ยาแก้ปวดข้อกลุ่มเอ็นเสดค่ะ"): chief complaint is not silently changed to `joint_pain`. `tests/e1r/test_syne0196_replay.py` is re-scoped per §8 D-V2A-1; the frozen artifacts are byte-unchanged | `test_def_e1r_001_last_asked_reset` (guided + ambient), `test_def_e1r_001_cc_conflict_held`, `test_def_e1r_001_syne0196_shape`; `git diff <base> -- eval/results eval/manifests eval/ledger eval/posthoc` is empty |
| V2A-A08 | Every extraction call goes through the gateway and is audited | For an ambient replay: number of gateway audit rows (`invoke_audited`) == number of non-question turns == number of `voice_extractions` rows with status ok/error. Question turns have 0 gateway rows and a `voice.turn.add` audit with `question_field` and `mode:"ambient"`. No audit row contains transcript text (existing `test_voice_audit_no_transcript_text` extended to ambient). Gateway `inputs` keys are exactly `{"turns","last_asked_field"}` | `test_ambient_gateway_audit_counts`, `test_ambient_audit_no_transcript_text`, `test_ambient_gateway_inputs_unchanged` |
| V2A-A09 | Per-turn latency (mock provider, in process, local) | p95 ≤ **500 ms** over all ambient fixture turns (n ≥ 150) | eval JSON `latency_ms`; asserted in `test_ambient_eval_thresholds` |
| V2A-A10 | No new dependency or provider coupling | `requirements.in`, `requirements.lock`, `pyproject.toml` and `web/package.json` are unchanged vs base. No `livekit`/`openai`/network import under `backend/app/voice/`. The existing `test_voice_provider_isolation` and `test_provider_isolation` pass unmodified | `git diff --stat <base> -- requirements.* pyproject.toml web/package.json` is empty; existing isolation tests |
| V2A-A11 | Mode contract | Default `guided`; `mode:"x"` → 422; `mode` is in every session payload; an UPDATE of `mode` is rejected by the trigger (SQLite, and PG in `make test-pg`); an ambient session has 0 `agent` turns after start + all turns + finish; idempotent column add on a pre-v2a SQLite DB | `test_mode_default_and_validation`, `test_mode_immutable`, `test_ambient_no_agent_turns`, `test_voice_schema_upgrade_idempotent` |
| V2A-A12 | Ambient finish yields valid typed evidence | `finish()` of all 15 ambient replays returns `IntakeTranscript` (speakers `unknown`) + `VoiceIntakeFacts`, and validates. Every fact `available_at_time` = max `ended_at` of its span turns. `GET …/facts?as_of=T` returns no fact with `available_at_time > T` | `test_ambient_finish_evidence`, `test_ambient_facts_as_of` |
| V2A-A13 | Fixture discipline | 15 ambient fixtures validate (schema test). `gold_facts`, `answers_by_field` and `gold_nurse_attention` are byte-equal to the source; `source_sha256` matches. No `agent` speaker. The held-out wording-novelty rule holds. The fixture commit is an ancestor of the first `intent_th.py` commit | `test_ambient_fixtures_schema_and_source`; checker runs `git merge-base --is-ancestor <fixture-commit> <first-intent-commit>` and records it |
| V2A-A14 | RBAC unchanged | Non-nurse roles get 403 on all `/api/voice` routes in both modes | existing `test_voice_auth_matrix` + ambient parametrisation |

## 7. Required test phrases (minimum; the builder may add more, dev-only)

**Questions → field, 0 facts:**

| Field | Phrases |
|---|---|
| chief_complaint | มาด้วยอาการอะไรคะ · วันนี้เป็นอะไรมาคะ · ไม่สบายตรงไหนคะ |
| onset_duration | เป็นมากี่วันแล้วคะ · เริ่มเป็นตั้งแต่เมื่อไหร่คะ · เป็นมาสามวันแล้วใช่ไหมคะ (leading) · เป็นมากี่วันแล้ว? |
| severity | ปวดกี่คะแนนคะ · ถ้าเต็มสิบให้เท่าไหร่คะ · เจ็บมากไหมคะ |
| allergy_status | แพ้ยาอะไรไหมคะ · มีประวัติแพ้ยาไหมคะ · ไม่แพ้ยาใช่ไหมคะ (leading) · แพ้ยาอะไรไหม |
| current_medications | ทานยาอะไรประจำไหมคะ · ตอนนี้กินยาอะไรอยู่บ้างคะ · ใช้ยาอะไรอยู่ไหม |
| relevant_history | มีโรคประจำตัวไหมคะ · เคยป่วยเป็นโรคอะไรมาก่อนไหมคะ · ไม่มีโรคประจำตัวใช่ไหมคะ (leading) |

**Answers → never questions:**
- ไม่แพ้ยาอะไรค่ะ
- ไม่ได้แพ้อะไรเลยครับ
- จำไม่ได้ว่าแพ้ยาอะไร
- อันนี้จำไม่ได้ค่ะ ไม่แน่ใจว่าแม่เคยแพ้ยาอะไรหรือเปล่า
- ไม่ได้กินยาอะไรเลยค่ะ
- เป็นมาสามวันแล้วค่ะ
- ปวดประมาณเจ็ดคะแนนค่ะ
- มาด้วยอาการไข้ค่ะ
- ไม่มีโรคประจำตัวค่ะ
- กินยาความดันประจำค่ะ
- เรื่องนี้ไม่ขอตอบครับ
- ขอไปเข้าห้องน้ำก่อนได้ไหมครับ (a question without field intent: not a field question)

**Merged segments:**
- "แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ" → allergy none or UNKNOWN or no fact, never present.
- "เป็นมากี่วันแล้วคะ สองวันค่ะ" → P2D.

**Stale window:**
- After "มีโรคประจำตัวไหมคะ", "เบาหวานค่ะ", then "เดี๋ยววัดความดันนะคะ": `relevant_history` = ["เบาหวาน"] only. The window closes by B2(ii) or keeps the list; the builder documents which, and the test asserts "ความดัน" is **not** added.

## 8. Clinical risks, mitigations and decisions

| Risk | Mitigation |
|---|---|
| A nurse's question or read-back is extracted as a patient fact (no diarization) | B1 classifier + B2 window. A leading question is never an answer. Residual: a nurse **statement** ("คุณลุงมาด้วยเจ็บหน้าอกค่ะ") is extracted like a patient statement. The v2d nurse review is the control. Disclosed in the eval notes |
| A patient answer is misclassified as a question → fact lost | The field stays MISSING and the nurse is prompted again (fail-visible, never a fabricated negative). Measured by A04 |
| Allergy false-none from a merged or hedged segment | B3 + A03 unit cases |
| A stale window attaches unrelated speech to a field | B2 reset rules; stale-window test |
| The chief complaint is silently replaced (DEF-E1R-001 b) | B4(b) hold + flag. Cost: genuine chief-complaint corrections are also held for the nurse |
| Red-flag false alarms from nurse screening questions end ambient prompting (sticky) | Accepted as conservative for now. Counted in the eval JSON (`attention_on_question_turns`). D-V2A-2 |
| Mock-rule results read as clinical accuracy | The eval label says system evaluation on synthetic text with no ASR. Same author for fixtures and rules (disclosed). Held-out is reported separately. v2e measures audio end-to-end |
| Transcript text leaks into the audit | A08 extends the existing no-text audit test to ambient |

Decisions required (the builder proceeds as stated; the reviewer or owner confirms):

**D-V2A-1:** `tests/e1r/test_syne0196_replay.py` asserts the **pre-fix** DEF-E1R-001 behaviour through the live service. Once the defect is fixed, that assertion can never hold again.

Proposed re-scope, in a separate commit:
- keep every check that the frozen constant equals the committed `POSTHOC_FINDINGS.json` trace;
- add a docstring line stating that the live-replay equality was last verified at the pre-v2a base commit;
- replace the live-replay equality with `test_replay_after_def_e1r_001_fix`, which asserts the fixed behaviour on the same dev case.

Rules:
- The frozen artifacts (`eval/results/**`, `eval/manifests/**`, `eval/ledger/**`, `eval/posthoc/e1_findings.py` constant) must not change.
- If any other e1/e1r/i2 test fails because of the fix, **stop and report**. Do not edit frozen artifacts or weaken the test.

**D-V2A-2** (clinical-safety-reviewer / D4): should a listed red-flag phrase inside a classified nurse question still trigger sticky nurse attention? The default is yes; that is not a downgrade.

**D-V2A-3** (v2d owner): `casegraph/reader_text.py` and `voice/symptoms.py` read `patient` turns only, so ambient `unknown` turns reach no downstream symptom or Case Graph text reader. v2d must decide before triage handoff. v2a changes only the `Turn.speaker` enum, additively.

**D-V2A-4** (shared-contract note to Research): the additive `"unknown"` value in `casegraph.data.Turn.speaker`.

## 9. Run commands (from the worktree root)

```bash
make test                                                   # A01, all pytest + web vitest
.venv/bin/python -m pytest -q backend/tests/voice           # voice suite incl. new ambient tests
.venv/bin/python -m pytest -q tests/e1r eval/adapters/tests # e1 guards (A07, D-V2A-1)
make eval-voice            # guided S3 eval re-run -> slices/s3/eval/voice_intake_eval.json (A01 counts unchanged)
make eval-voice-ambient    # -> slices/v2a/eval/ambient_intake_eval.json (A02, A03, A04, A09)
make test-pg               # optional; PG trigger + mode immutability (skips without Docker)
git diff --stat $(git merge-base HEAD main) -- requirements.in requirements.lock pyproject.toml web/package.json eval/results eval/manifests eval/ledger eval/posthoc   # A07/A10: expect empty
```

The builder's evidence must contain: the commit order for A13, every ambient eval run (including failures), the `make test` tail, both eval JSON summaries, and the D-V2A-1 diff.
