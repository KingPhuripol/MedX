# V2A — Ambient intake mode for the voice session API (backend only)

Planner: innovation-lead. Revision 2 (2026-09-30), which resolves checker SP-1 and SP-2 on 211d1a1. Branch: `factory/v2a`. Gantt owner: ภูริณัฐ (Voice Agent, PROPOSAL row 16).
Sources: `docs/PROPOSAL.md` §1.3.1 ("ถามเพิ่มเฉพาะข้อมูลที่ยังขาด"), §3.1, §3.5, Table 3.2; `docs/DECISIONS.md` 2026-09-30 (V2 ambient scribe direction). The proposal wins on any conflict.
This is a research prototype that uses synthetic data only. The nurse is present and in charge. The system suggests. It never speaks, diagnoses or triages.

## 1. Problem and user

A nurse records an ordinary Thai nurse–patient conversation on one phone mic. There is no diarization, so every segment arrives as `speaker:"unknown"`. The backend must do three things:
- extract intake facts from patient speech, and **never from any question**, whether it has field intent or not;
- tell the nurse which required fields are still missing, with a suggested question from the allowlist (shown on screen, never spoken);
- keep red-flag and nurse-attention cues above everything else.

## 2. Scope

**In scope.** Changes under `backend/app/voice/`, its tests, fixtures and eval. They cover:
- session `mode`;
- `speaker:"unknown"`, which also means an additive enum value on `casegraph.data.Turn.speaker`;
- the deterministic classifier `intent_th.py`, using stdlib `re` only;
- the ambient ask window;
- the ambient `next_action`;
- the DEF-E1R-001 fix, parts (a) and (b), in **both** modes;
- 15 ambient fixtures, the replay and `make eval-voice-ambient`.

**Out of scope.**
- audio, STT/ASR, LiveKit, OpenAI or any network/vendor SDK;
- `web/` or `mobile/` UI;
- nurse confirmation and triage handoff (v2d);
- external providers;
- diarization;
- DEF-E1R-001 part (c) (chief-complaint vocabulary, shared with S4);
- changes to the red-flag phrase list or allowlist wording (D4);
- changes to what `casegraph/reader_text.py` and `voice/symptoms.py` read (D-V2A-3).

## 3. Contracts — LOCKED by the orchestrator

Contracts 1–3 are fixed by the orchestrator. v2c (mobile UI) and v2d (review/handoff) build against them in parallel. Do not change names or shapes.

1. **Start session.** `POST /api/voice/sessions` takes `{patient_ref, data_class:"synthetic", mode?: "guided"|"ambient"}`.
   - The default is `"guided"`. Any other value returns 422.
   - `session.mode` appears in every session payload.
   - The mode is immutable: add it to the fixed-column trigger in SQLite and PG.
   - The column is added idempotently. A pre-v2a row reads as `guided`.
2. **Add turn.** `POST /api/voice/sessions/{id}/turns` accepts `speaker ∈ {patient, relative, nurse, unknown}`.
   - Ambient clients send `source:"asr"`, `asr_model` and `speaker:"unknown"`.
   - `unknown` is accepted in both modes. Guided mode treats it like `patient`.
3. **Ambient `next_action`.** It has exactly these keys: `{kind, field, suggested_question_id, suggested_question_th, reason, missing_fields}`.

   | `kind` | When | Other keys |
   |---|---|---|
   | `prompt_nurse` | An `ASK_ORDER` field is still MISSING | `field` is the first MISSING field in `ASK_ORDER`. `suggested_question_id` is `ask.<field>` if the field was never asked, else `reask.<field>`. `suggested_question_th` is `UTTERANCES_TH[id]` only; an unknown id raises. There is no ask limit. `reason` is null |
   | `complete` | No `ASK_ORDER` field is MISSING. KNOWN, UNKNOWN and REFUSED all count as captured | `reason:"complete"`; `field` and the suggestion are null; `missing_fields:[]` |
   | `handoff` | Sticky. Preempts `prompt_nurse` and `complete` | `reason:"nurse_attention_phrase"` if any turn hit nurse attention, else `"extraction_unavailable"` after any gateway, schema or grounding failure |

   - The ambient action has no `utterance_th` or `action` key.
   - An ambient session never writes an `agent` turn.
   - Guided `next_action` keeps exactly its 6 existing keys, and guided behaviour is unchanged.

**Additive fields (planner, both modes):**
- `chief_complaint_conflict: bool`, at top level and in `session`;
- `held_facts` on GET session: `{turn_id, field, state, value, span_turn_ids, reason}`, with no transcript text;
- a nullable `held_json` column on `voice_extractions`, append-only and added idempotently.

**Gateway request.** It is unchanged: `task="voice.intake_extract"`, `inputs` keys exactly `{"turns","last_asked_field"}`, `data_class="synthetic"`. There is no Model API Contract change.

## 4. Behaviour

### B1. Clauses, questions and extraction text

This resolves SP-1. Ambient mode applies it to every non-agent turn. Guided mode applies it only to `speaker=="nurse"` turns, and there it uses only field questions: field-less nurse turns keep the pre-v2a path, the extractor's nurse guard.

1. **Clauses.** Split the turn into clauses at whitespace, `?` and a glued question-particle boundary. A clause that is a question particle alone joins the clause before it. For example, "เจ็บหน้าอก ไหมคะ" is one clause.
2. **Question clause.** A clause is a question clause iff it ends in a question form: a final particle ไหม/มั้ย/หรือเปล่า/รึเปล่า/หรือไม่/หรือยัง/ใช่ไหม/เท่าไร/เท่าไหร่/อะไร/ไหน/เมื่อไร/กี่…, then an optional tail and polite particle, or `?`. Two restrictions apply:
   - **บ้าง** is a question form only if a wh-word (อะไร, ไหน, ใคร, ยังไง, อย่างไร, เท่าไร, เท่าไหร่, กี่…, เมื่อไร) occurs earlier in the same clause, or if `?` follows. Otherwise it is the quantifier "some/sometimes" and the clause is an answer. Examples: "ไอบ้างค่ะ" is an answer; "กินยาอะไรอยู่บ้างคะ" is a question.
   - A question form governed by a patient non-answer (`UNKNOWN_PHRASES`/`REFUSED_PHRASES` before it) or by a leading negation is **not** a question. The exception is a confirmation tag (ใช่ไหม…): "ไม่แพ้ยาใช่ไหมคะ" is a leading question.
3. **Question field.** Each question clause has field F if a field-intent pattern matches; the intent that ends last wins. Otherwise it is a **field-less question**: a screening question ("มีไข้ไหมคะ"), a patient request ("ขอไปเข้าห้องน้ำก่อนได้ไหมครับ") or a question to the nurse.
4. **Extraction text.** This is the turn text with every question clause removed, of any field or none, and with particle-only residue dropped. **No question clause ever reaches the gateway, and no question clause ever produces a fact.**
5. **Per-turn outcome.** Every non-agent turn writes exactly one `voice_extractions` row.

   | Extraction text | Gateway | `voice_extractions` | Facts |
   |---|---|---|---|
   | empty | 0 calls | `status:"skipped"`, `reason:"nurse_question"` | 0 |
   | non-empty | exactly 1 call; the current turn's text in `inputs.turns` is the extraction text | `status:"ok"` or `"error"` | 0 or more, from the extraction text only |

   A residue such as "วันนี้" in "เป็นอะไรมาคะวันนี้" is non-empty. It makes 1 call and usually yields 0 facts. This is accepted (see L-1).
6. **Stored and audited.**
   - `voice_turns.field` is the field of the turn's last field question clause, or null.
   - The `voice.turn.add` audit has `mode`, `question: bool` (true iff the turn has at least one question clause) and `question_field` (that field, or null). It never contains text.
   - `times_asked[F]` in ambient mode counts turns whose `question_field == F`.
7. **Merged turns.** Allergy stays guarded:
   - "แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ" gives allergy none, UNKNOWN or no fact. It is never `present`.
   - "แพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ" keeps the sulfa allergy.

### B2. Ask window (ambient)

`last_asked_field` for a piece of extraction text is set as follows.
- **Text before the turn's first question clause**, and every text of a turn with no question clause: the window in effect before the turn.
- **Text after a question clause**: that clause's field F, or None if the clause is field-less.
- **After the turn**, the window is set by the turn's **last** question clause:
  - a field question opens window F;
  - a **field-less question resets it to None**. The next answer belongs to a question that has no field, so it is never attached to an earlier field.

An open window F closes (becomes None) on any of these:
- (i) a later nurse-attention turn;
- (ii) `AMBIENT_ASK_WINDOW = 2` turns with non-empty extraction text. A merged question + answer turn counts as the first of the two;
- (iii) for the scalar fields `chief_complaint`, `onset_duration`, `severity` and `allergy_status`: a fact for F written inside the window.

List fields (`current_medications`, `relevant_history`) close only by (i), (ii) or a field-less question. Only turns with `ended_at` ≤ the current turn's `ended_at` are used.

Volunteered facts (window None) are extracted wherever the existing rules allow.

### B3. Allergy guard

`reconcile_allergy` is unchanged and runs in both modes. Missing, uncertain, hedged, questioned or merged allergy is never `none`. A recorded allergy is never weakened.

### B4. DEF-E1R-001 (both modes)

- **(a)** After a nurse-attention handoff, `last_asked_field` resets to None.
  - Guided: the handoff agent turn has field null.
  - Ambient: B2(i).
- **(b)** A KNOWN `chief_complaint` whose value differs from the current KNOWN one is **held**, not written:
  - it is stored in `held_json` with `reason:"chief_complaint_conflict"`, returned in `held_facts`, and sets `chief_complaint_conflict:true`;
  - the earlier chief complaint stays the latest fact;
  - it is audited without `value_text`;
  - the same value is deduplicated.

### B5. Red flag

`nurse_attention_hit` runs on the full text of every non-agent turn, in both modes, before extraction. This includes question clauses. It is never suppressed or downgraded (D-V2A-2). The attention turn itself is extracted with the window in effect before it.

### B6. Finish

An ambient `finish()` returns valid `VoiceIntakeFacts` + `IntakeTranscript`:
- `unknown` speakers are preserved;
- there are no agent turns;
- `handoff_reason` is the ambient `reason`, or `finished_by_nurse` if the kind is `prompt_nurse`.

## 5. Fixtures and evaluation

**Fixtures.** `backend/tests/voice/fixtures/ambient/th_ambient_{01..15}.json` are converted from `th_intake_NN`:
- `speaker:"unknown"`;
- `turn_id`s and timestamps are unchanged;
- agent turns are rewritten as natural nurse questions;
- other turn texts are kept.

Added keys: `mode`, `source_dialogue_id`, `source_sha256` and `gold_question_turns {turn_id: field}`. `gold_facts`, `answers_by_field` and `gold_nurse_attention` are byte-identical to the source.

**Held out.**
- 11–15 are tagged `heldout`.
- Each field has at least one held-out question wording that is absent from dev.
- The fixture commit (97e7dbc) is an ancestor of the first `intent_th.py` commit.
- Held-out results must never motivate a rule change. Every eval run is appended to `slices/v2a/eval/runs.jsonl` with a one-line cause, including failed runs. The revision-2 changes (บ้าง restriction, field-less window reset) come from reviewer/checker probe phrases, not held-out fixtures. Record that cause.

**Replay and eval.**
- `simulate_ambient` posts every fixture turn in order (`source:"asr"`, `asr_model:"fixture-text"`, fake clock), then finishes.
- `make eval-voice-ambient` writes `slices/v2a/eval/ambient_intake_eval.json`, labelled "system evaluation — mock rules, synthetic ambient text dialogues (no audio/ASR), not clinical performance".
- It uses the S3 scorer: 2,000-resample dialogue bootstrap, seed 0.
- Contents:
  - dev/held-out per field;
  - `micro_gated` over `chief_complaint, onset_duration, severity, allergy_status, allergens, current_medications`;
  - reported `relevant_history`/`micro_overall`;
  - `allergy_false_none`;
  - the classifier block, where a "flagged answer" is an answer turn with any question clause;
  - `final_action`;
  - `attention_on_question_turns`;
  - `latency_ms`;
  - `inputs_sha256`.

## 6. Acceptance

`<base>` = `git merge-base HEAD main`.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| V2A-A01 | Guided mode and existing tests are unchanged | `make test` exits 0. No existing test file is modified, except `tests/e1r/test_syne0196_replay.py` per D-V2A-1. The guided `next_action` key set is exactly the 6 keys. `make eval-voice` guided `tp/fp/fn` per field and `allergy_false_none` equal `<base>`'s `slices/s3/eval/voice_intake_eval.json` (dev 57/1/0, held-out 30/0/0, false-none 0) | `make test`; `test_guided_next_action_keys_unchanged`; `test_guided_eval_counts_unchanged` |
| V2A-A02 | Ambient gated micro-F1 | dev 1–10 **≥ 0.90**; held-out 11–15 **≥ 0.80** | `splits.{dev,heldout}.micro_gated.f1`; `test_ambient_eval_thresholds` (fresh-or-rerun on `inputs_sha256`) |
| V2A-A03 | No allergy false-none | 0 on all 15 fixtures, and 0 in every allergy unit case of §7 (merged, leading, field-less window reset) | eval `allergy_false_none`; §7 allergy tests |
| V2A-A04 | Questions produce zero patient facts | Every §7 question phrase: `question:true`, correct `question_field` (null for field-less), 0 facts, 0 gateway calls. Every §7 answer phrase: `question:false`. Fixtures: dev question detection 52/52 with the correct field and 0 flagged answer turns; held-out correct-field rate ≥ 0.80 (reported) | `test_intent_th.py` (parametrised over §7); `test_question_turn_no_facts_no_gateway`; eval `classifier` |
| V2A-A05 | `prompt_nurse` only for missing fields, only with allowlisted text | Across every response of the 15 replays: `kind=="prompt_nurse"` ⇒ the field is MISSING, `suggested_question_th == UTTERANCES_TH[suggested_question_id]` and the id is `ask.`/`reask.`+field. A field is never prompted after it leaves MISSING. The final kind matches gold on dev 10/10 and held-out ≥ 4/5. The action has exactly the §3 keys | `test_ambient_prompt_only_missing`, `test_ambient_prompt_allowlist`, `test_ambient_next_action_keys`, `test_ambient_final_action_matches_gold` |
| V2A-A06 | Red flag preempts in ambient mode | Fixtures 06, 09 and 12: from the attention turn onward, every response is `handoff`/`nurse_attention_phrase` with `nurse_attention:true`. A unit test with MISSING fields and "เมื่อกี้ลูกชักด้วยค่ะ" gives handoff. A question clause containing a listed phrase still fires. A gateway error gives `handoff`/`extraction_unavailable` with 0 facts | `test_ambient_attention_preempts`, `test_ambient_question_with_red_flag_still_fires`, `test_ambient_gateway_failure_fails_safe` |
| V2A-A07 | DEF-E1R-001 (a)+(b) | Guided and ambient: after `nurse_attention_phrase`, the next gateway request has `last_asked_field` None, or the field of a later question. A different later chief complaint is held (`chief_complaint_conflict:true`, present in `held_facts`, the earlier one is still latest, and there is no superseding `voice_facts` row). SYNE-0196 shape (red flag → drug-reaction question → "แพ้ยาแก้ปวดข้อกลุ่มเอ็นเสดค่ะ"): the chief complaint is not changed to `joint_pain`. The frozen e1 artifacts are byte-unchanged | `test_def_e1r_001_last_asked_reset`, `test_def_e1r_001_cc_conflict_held`, `test_def_e1r_001_syne0196_shape`; `git diff <base> -- eval/results eval/manifests eval/ledger eval/posthoc` is empty |
| V2A-A08 | Every extraction call goes through the gateway and is audited (restated for B1) | For each of the 15 ambient replays, three counts are equal: gateway audit rows (`invoke_audited`), turns with non-empty extraction text, and `voice_extractions` rows with status ok/error. There is exactly one `voice_extractions` row per non-agent turn. Turns with empty extraction text have status `skipped`/`nurse_question` and 0 gateway rows. Every turn's `voice.turn.add` audit has `mode`, `question` and `question_field`. No audit row contains transcript text. Gateway `inputs` keys are exactly `{"turns","last_asked_field"}`, and no question clause text appears in `inputs.turns[-1].text` | `test_ambient_gateway_audit_counts`, `test_ambient_audit_no_transcript_text`, `test_ambient_gateway_inputs_unchanged`, `test_question_clause_never_sent` |
| V2A-A09 | Per-turn latency (mock provider, in process) | p95 ≤ **500 ms** over all ambient fixture turns (n ≥ 150) | eval `latency_ms`; `test_ambient_eval_thresholds` |
| V2A-A10 | No new dependency or provider coupling | `requirements.in`, `requirements.lock`, `pyproject.toml` and `web/package.json` are unchanged vs `<base>`. No `livekit`/`openai`/network import under `backend/app/voice/`. The existing isolation tests pass unmodified | `git diff --stat`; `test_voice_provider_isolation`, `test_provider_isolation` |
| V2A-A11 | Mode contract | Default `guided`; `mode:"x"` returns 422; `mode` is in every payload; an UPDATE of `mode` is rejected (SQLite; PG in `make test-pg`); an ambient session has 0 `agent` turns; the column add is idempotent on a pre-v2a DB | `test_mode_default_and_validation`, `test_mode_immutable`, `test_ambient_no_agent_turns`, `test_voice_schema_upgrade_idempotent` |
| V2A-A12 | Ambient finish yields valid typed evidence | All 15 replays validate. Every fact's `available_at_time` equals the max `ended_at` of its span turns. `GET …/facts?as_of=T` returns no fact with `available_at_time > T` | `test_ambient_finish_evidence`, `test_ambient_facts_as_of` |
| V2A-A13 | Fixture discipline | The schema is valid. Gold keys are byte-equal to the source and `source_sha256` matches. There is no `agent` speaker. Held-out wording novelty holds. `runs.jsonl` has one row per eval run with its cause | `test_ambient_fixtures_schema_and_source`; `git merge-base --is-ancestor 97e7dbc <first intent_th.py commit>` |
| V2A-A14 | RBAC unchanged | Non-nurse roles get 403 on all `/api/voice` routes in both modes | `test_voice_auth_matrix` + ambient parametrisation |
| V2A-A15 | บ้าง answers keep their facts (SP-2) | Each §7 บ้าง answer: `question:false`, 1 gateway call. After "มาด้วยอาการอะไรคะ", "ไอบ้างค่ะ" makes `chief_complaint` KNOWN. After "มีโรคประจำตัวไหมคะ", "เป็นเบาหวานกับความดันบ้างค่ะ" makes `relevant_history` contain both เบาหวาน and ความดัน | `test_bang_answers_not_questions`, `test_bang_answer_extracted_in_window` |

## 7. Required test phrases

These are the minimum set, all dev-only. The builder may add more, but never from held-out fixtures.

**Field questions: `question:true`, field as listed, 0 facts, 0 gateway calls.**

| Field | Phrases |
|---|---|
| chief_complaint | มาด้วยอาการอะไรคะ · วันนี้เป็นอะไรมาคะ · ไม่สบายตรงไหนคะ · มีอาการอะไรบ้างคะ |
| onset_duration | เป็นมากี่วันแล้วคะ · เริ่มเป็นตั้งแต่เมื่อไหร่คะ · เป็นมาสามวันแล้วใช่ไหมคะ (leading) · เป็นมากี่วันแล้ว? |
| severity | ปวดกี่คะแนนคะ · ถ้าเต็มสิบให้เท่าไหร่คะ · เจ็บมากไหมคะ |
| allergy_status | แพ้ยาอะไรไหมคะ · มีประวัติแพ้ยาไหมคะ · ไม่แพ้ยาใช่ไหมคะ (leading) · แพ้ยาอะไรไหม |
| current_medications | ทานยาอะไรประจำไหมคะ · ตอนนี้กินยาอะไรอยู่บ้างคะ · ใช้ยาอะไรอยู่ไหม |
| relevant_history | มีโรคประจำตัวไหมคะ · เคยป่วยเป็นโรคอะไรมาก่อนไหมคะ · ไม่มีโรคประจำตัวใช่ไหมคะ (leading) |

**Field-less questions: `question:true`, `question_field:null`, 0 facts, 0 gateway calls, window None after the turn.**
- มีไข้ไหมคะ
- เจ็บหน้าอกไหมคะ
- เจ็บหน้าอก ไหมคะ
- ไอบ้างไหมคะ
- ขอไปเข้าห้องน้ำก่อนได้ไหมครับ

As the first turn of a session, each of these leaves `chief_complaint` MISSING.

**Answers: `question:false`.**
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
- บ้าง answers (SP-2):
  - ไอบ้างค่ะ
  - ไข้ขึ้นบ้างลงบ้างค่ะ
  - มีน้ำมูกบ้างค่ะ
  - ปวดหัวบ้างครับ
  - เป็นเบาหวานกับความดันบ้างค่ะ

**Mixed and merged turns.**
- "แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ": allergy none, UNKNOWN or no fact; never `present`.
- "เป็นมากี่วันแล้วคะ สองวันค่ะ": P2D.
- "แพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ": allergy `present`, sulfa; the window becomes `current_medications`.
- "อ้อ แพ้เพนิซิลลินด้วย จะเป็นอะไรไหมคะ": penicillin kept; allergy never none.

**Windows.**
- Field-less reset (allergy): "แพ้ยาอะไรไหมคะ" → "มีไข้ไหมคะ" → "ไม่มีค่ะ". `allergy_status` stays MISSING, never none.
- Stale list: "มีโรคประจำตัวไหมคะ" → "เบาหวานค่ะ" → "เดี๋ยววัดความดันนะคะ". `relevant_history` is ["เบาหวาน"] only.
- Merged stale list: "มีโรคประจำตัวไหมคะ เบาหวานค่ะ" → "เดี๋ยววัดความดันนะคะ". "ความดัน" is not added.

## 8. Clinical risks, limitations and decisions

| Risk | Mitigation |
|---|---|
| A question (field or screening) becomes a patient fact | B1: every question clause is removed before the gateway, and A04/A08 test it. Residuals: a nurse **statement** ("คุณลุงมาด้วยเจ็บหน้าอกค่ะ") is extracted like patient speech, and a nurse question phrased "ไอบ้างคะ" (no wh-word, no `?`) is read as an answer. The v2d nurse review is the control, and both are disclosed in the eval notes |
| A patient answer is misread as a question and the fact is lost | This fails visibly: the field stays MISSING and the nurse is re-prompted. The บ้าง restriction removes the known case (A15) |
| Allergy false-none | B3, the field-less window reset, A03 |
| A stale window attaches unrelated speech | B2 closing rules and the §7 window tests |
| The chief complaint is silently replaced | B4(b) hold + flag. Cost: genuine corrections are also held for the nurse |
| Red-flag false alarms from screening questions end prompting (sticky) | Accepted as conservative and counted (`attention_on_question_turns`). D-V2A-2 |
| Mock results are read as clinical accuracy | The eval label, the same-author disclosure and the separate held-out split. v2e measures audio end to end |

**L-1 (known limitation, accepted).** A question followed by a trailing adverb ("เป็นอะไรมาคะวันนี้", held-out fixture 12 t01) leaves non-empty extraction text. That text makes 1 gateway call with 0 facts and uses one window turn. It is not changed in v2a, because the observation comes from a held-out fixture. A08 counts it by the extraction-text rule.

**Decisions** (the builder proceeds as stated; the reviewer or owner confirms):
- **D-V2A-1:** `tests/e1r/test_syne0196_replay.py` asserts pre-fix behaviour. Re-scope it in a separate commit:
  - keep the frozen-constant == `POSTHOC_FINDINGS.json` checks;
  - replace the live-replay equality with `test_replay_after_def_e1r_001_fix`;
  - leave frozen artifacts untouched.
  If any other e1/e1r/i2 test fails, stop and report.
- **D-V2A-2** (clinical-safety-reviewer / D4): a listed red-flag phrase inside a question still triggers sticky attention. The default is yes.
- **D-V2A-3** (v2d owner): Case Graph and symptom readers take `patient` turns only, so ambient `unknown` turns reach none of them. v2d must decide this before triage handoff.
- **D-V2A-4** (Research, shared contract): the additive `"unknown"` value in `casegraph.data.Turn.speaker`.
- **D-V2A-5** (this revision, SP-2): บ้าง-final answers are answers. The recall loss seen at 211d1a1 is **rejected**, not accepted.

## 9. Run commands (worktree root)

```bash
make test                                                   # A01 and all unit tests
.venv/bin/python -m pytest -q backend/tests/voice           # voice suite incl. ambient, intent, §7
.venv/bin/python -m pytest -q tests/e1r eval/adapters/tests # A07, D-V2A-1
make eval-voice            # A01 guided counts unchanged
make eval-voice-ambient    # A02, A03, A04, A09 -> slices/v2a/eval/ambient_intake_eval.json
make test-pg               # optional, A11 on PG (skips without Docker)
git diff --stat $(git merge-base HEAD main) -- requirements.in requirements.lock pyproject.toml web/package.json eval/results eval/manifests eval/ledger eval/posthoc   # expect empty
```

The builder's evidence must include:
- the A13 ancestor check;
- every `runs.jsonl` row, including the revision-2 run and its cause;
- the `make test` tail;
- both eval summaries;
- the D-V2A-1 diff.
