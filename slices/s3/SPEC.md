# Slice s3 — Voice Agent: Thai intake (text cascade first)

- Owner (Gantt): ภูริณัฐ ("พัฒนา Voice Agent", Gantt rows 16)
- Source of truth: `docs/PROPOSAL.md` (v8)
  - 1.3.1: the Voice Agent takes a Thai history with a nurse present, extracts key facts (chief complaint, duration, drug allergy), asks only for what is still missing, and hands the facts on for nurse confirmation. Cascade is primary.
  - 1.3.2: evaluation uses synthetic scripted Thai dialogues, not MIMIC.
  - 2.1.6: cascade is ASR → LLM → TTS. Each stage can be swapped and its text inspected. Evaluation focuses on correctness of the extracted key facts [24].
  - 3.1: the Voice Agent is a module separate from the Case Graph. It controls the dialogue and picks the next question. It calls the LLM through the Model Gateway. Output is the transcript plus extracted facts, recorded as `ClinicalText`.
  - 3.5: the nurse starts the conversation and measures vitals.
  - 3.6 / Table 3.2: metrics are key-fact correctness, response time and total time, each with a 95% patient-level bootstrap CI. Without expert review, results are reported as a System Evaluation, not clinical performance.
- Depends on: s0 (auth/roles, Model Gateway, append-only audit, `casegraph.EvidenceItem`). Does **not** depend on s1 (dataset) or s2 (shared casegraph types, Compiler/Executor).
- Status: PLAN. Written by the planner.

## Scope

1. **Module `backend/app/voice/`** (own package, own router, own tables)
   - Local Pydantic v2 models, all `extra="forbid"`:
     - `Turn {turn_id, session_id, seq, speaker: agent|patient|relative|nurse, text, started_at, ended_at}`
     - `IntakeFact {fact_id, session_id, field, state: KNOWN|UNKNOWN|REFUSED, value, value_text, span_turn_ids[], event_time, available_at_time, extractor, provider, model_version, request_sha256, supersedes_fact_id|null}`
     - `FieldStatus {field, status: MISSING|KNOWN|UNKNOWN|REFUSED, times_asked}`
     - `NextAction {action: ask|handoff, field|null, utterance_id, utterance_th, reason|null}`
     - `IntakeEvidence` (ClinicalText-like; see item 6)
   - Required fields, in the fixed ask order:
     1. `chief_complaint`: a closed local **symptom** vocabulary (~15 codes, e.g. `fever`, `cough`, `abdominal_pain`, `chest_pain`, `headache`, `dyspnea`, `diarrhea`, `rash`, `dizziness`, ...) plus the verbatim `value_text`. These are symptom categories, not diagnoses.
     2. `onset_duration`: an ISO-8601 duration (`PT5H`, `P3D`, `P2W`). Thai numerals and number words are normalized (`3 วัน`, `สามวัน`, `ตั้งแต่เมื่อวาน` → `P1D`).
     3. `severity`: NRS 0–10 integer, or `mild|moderate|severe` from Thai descriptors.
     4. `allergy_status`: KNOWN with value `none`, KNOWN with value `present`, UNKNOWN, or REFUSED. `allergens[]` is a separate list fact.
     5. `current_medications`: a list of names exactly as the patient reported them, with no mapping and no dose inference. The empty list is a KNOWN value ("takes none").
     6. `relevant_history`: a list of conditions the patient reported, as free-text items.
   - A field with no fact is `MISSING`. MISSING is **never** turned into a negative. In particular, a missing allergy is never shown as "no allergy".
   - Thai semantics the rules must honour (all covered by tests):
     - `ปฏิเสธแพ้ยา` / `ไม่แพ้ยา` → allergy KNOWN `none`. In Thai clinical usage "ปฏิเสธ" means *denies*; it does not mean refused.
     - `จำไม่ได้` / `ไม่แน่ใจ` → UNKNOWN.
     - `ไม่ขอตอบ` / `ไม่อยากบอก` → REFUSED.
     - Hedged (`มั้ง`, `น่าจะ`, `คิดว่า`), asked-back (`ใช่ไหม`, `หรือเปล่า`) or non-answer (`ไม่มีข้อมูล`, `ไม่เคยตรวจ`, `ไม่เคยสังเกต`) negatives → UNKNOWN, never KNOWN `none`/`[]`. A bare denial counts only as a whole short utterance for the field just asked; `ไม่แพ้` never answers medications or history. A nurse's question turn yields no facts.
     - `แพ้ยา… จำไม่ได้ว่ายาอะไร` → KNOWN `present` with allergens UNKNOWN. `ไม่แพ้ยาอะไรนอกจาก X` / `ยกเว้น X` / `แพ้แต่ X` → KNOWN `present` with X. `ไม่แพ้ยาอื่น` is never `none`.
     - **Allergy guard (service, extractor-independent):** once a drug allergy is KNOWN `present` (or allergens are known), no later `none`/UNKNOWN/REFUSED allergy status or UNKNOWN/REFUSED allergens fact is written. It is held, returned as `held_facts`, audited, and the session shows `allergy_conflict=true` for nurse review. Named allergens always imply status `present`.
2. **Cascade pipeline (text first)**
   - `add_turn` works in this order:
     1. Persist the turn (append-only).
     2. If the speaker is patient, relative or nurse, call the gateway in process with `task="voice.intake_extract"` and `data_class="synthetic"`. The inputs are only the session turns with `ended_at <= this turn's ended_at`, plus the field last asked.
     3. Validate the output against a local schema.
     4. Run the grounding checks: every span turn id exists in the session, is not an `agent` turn, and is not in the future.
     5. Append the new or superseding facts.
     6. Compute the `NextAction`.
   - Agent turns (questions) are recorded as turns but never extracted from.
   - A correction ("เมื่อวาน เอ้ย สองวันแล้ว") appends a new fact version with `supersedes_fact_id`. The old version is kept.
   - **Fail-safe:** in each of these cases no fact is written from the call, the session gets `extraction_error=true`, and the next action is `handoff(reason=extraction_unavailable)`:
     - gateway `status` is `error` or `rejected`
     - schema-invalid output
     - a span referencing an unknown, agent or future turn
     - an unknown field or state
3. **Model Gateway usage (s0 integration, backward compatible)**
   - Factor the body of `POST /api/gateway/invoke` into a service function, e.g. `app.gateway.invoke_audited(engine, provider, request, actor)`. The route and the voice module both call it, so **every** model call writes exactly one `gateway.invoke` audit row. The gateway contract (`0.1.0`) is unchanged.
   - `MockProvider` gains a task-handler registry exposed through the public `app.gateway` API (e.g. `register_mock_task(task, fn)`):
     - The voice module registers `voice.intake_extract`, which is rule-based Thai extraction (stdlib `re` only; no new NLP dependency). It lives in `backend/app/voice/mock_rules.py`.
     - The handler must be a pure, deterministic function of the request.
     - Output always carries `label: "MOCK — not clinical"`.
     - Unregistered tasks keep the s0 hash-placeholder behaviour, so all s0 tests stay green.
     - Nothing outside `app/gateway/` imports `gateway.adapters`.
4. **Next-question policy** (`backend/app/voice/policy.py`, deterministic, no model)
   - Asks only fields whose status is `MISSING`, in the fixed order.
   - Never re-asks KNOWN, UNKNOWN or REFUSED fields.
   - Asks a MISSING field at most 2 times. After that the field stays `MISSING` and the policy moves on (flagged `not_elicited`).
   - Emits `handoff(reason=complete)` only when no field is MISSING, or `handoff(reason=attempts_exhausted)` with the remaining MISSING list.
   - **Nurse-attention interrupt:** a deterministic phrase list (e.g. เจ็บหน้าอก+หายใจไม่ออก, หมดสติ, ชัก, เลือดออกมาก, อยากตาย/ฆ่าตัวตาย) is checked on every non-agent turn **before** extraction and independent of the gateway. A hit gives `handoff(reason=nurse_attention_phrase)` immediately. The interrupt assigns no urgency level, triage category or department. The list is a placeholder pending clinical sign-off (see Decisions).
   - Patient-facing utterances come **only** from a fixed, reviewed template allowlist (`backend/app/voice/utterances_th.py`: one question per field, one re-ask per field, and neutral handoff lines such as "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อสักครู่นะคะ"). Model output is never spoken or rendered as an agent utterance.
5. **API** (router `/api/voice`, nurse role only; physician and pharmacist get 403, unauthenticated gets 401)
   - `POST /api/voice/sessions` with `{patient_ref, data_class}`:
     - `patient_ref` must match `^SYN-`. `data_class` must be `synthetic`; anything else gives 422.
     - Returns the session and the first `NextAction`.
   - `POST /api/voice/sessions/{id}/turns` with `{speaker, text, started_at, ended_at}` (UTC ISO-8601):
     - Returns 422 if `ended_at < started_at`, if `started_at` is earlier than the previous turn's `ended_at`, or if `ended_at` is more than 5 s ahead of server time.
     - Returns 409 after finish.
     - Returns the new facts, the field statuses and the `NextAction`.
   - `GET /api/voice/sessions/{id}` returns the session, turns, field statuses and current `NextAction`.
   - `GET /api/voice/sessions/{id}/facts?as_of=<ISO>` returns only facts with `available_at_time <= as_of`, latest version per field. With no `as_of`, it returns the latest facts.
   - `POST /api/voice/sessions/{id}/finish`:
     - The nurse may finish at any time.
     - The response lists every still-MISSING field explicitly and gives the handoff reason.
     - Returns the `IntakeEvidence` bundle.
   - Session start, each turn and finish each write one audit row with the actor id and role. Audit rows hold ids and hashes, never transcript text.
   - There are no PUT, PATCH or DELETE routes.
6. **Evidence output.** `IntakeEvidence` items use the `casegraph.EvidenceItem` field names and must validate against that s0 base class:
   - `data_type="ClinicalText"`
   - `patient_ref`
   - `event_time`: the turn start
   - `available_at_time`: the `ended_at` of the latest turn in the fact's span. For the transcript item it is the end of the last turn.
   - `source="voice_agent.cascade"`
   - `provenance`: a string reference: `voice_session/<id>/turns/<ids>;gw/<request_sha256>;extractor/<version>`
   - `version`
   - Payload: the transcript and the facts.

   Handing this to the Case Graph and department suggestion is out of scope.
7. **Storage.** New tables `voice_sessions`, `voice_turns` and `voice_facts`, created by the voice module on the same engine. `voice_turns` and `voice_facts` have append-only triggers on SQLite and PostgreSQL, using the same pattern as `audit_events`. Session status changes are recorded as audit events. The only mutable column is `voice_sessions.status`.
8. **Audio interface (local only)** in `backend/app/voice/audio.py`:
   - `ASRProvider.transcribe(audio: bytes, lang="th") -> ASRResult` and `TTSProvider.synthesize(text_th) -> bytes`.
   - The only implementations are `LocalStubASR`, which returns `status=not_configured` with no transcript and never fabricates text, and `LocalStubTTS`, which returns deterministic silence.
   - An ASR transcript must become the same `Turn` type as typed text.
   - There are no speech SDKs, no Whisper and no LiveKit. Those come in a later step, behind the same interface.
9. **Nurse web page** at `/nurse/intake`, reusing the s0 `RoleGuard` (nurse only) and existing `web/` styles with semantic markup. The MedX theme is being built in parallel, so the page uses no custom design tokens.
   - The nurse enters a synthetic patient ref and starts the session.
   - The current agent question is shown in a `role="status"` live region.
   - A turn form has a speaker select (patient, relative or nurse) and a text box. Enter submits.
   - A facts table shows field, state, value, the source turn(s) as links to the transcript rows, and `available_at_time`.
   - A MISSING-fields list is shown.
   - A handoff/attention banner appears when the next action is handoff.
   - A Finish button leads to a summary.
   - The disclaimer is visible. The page contains no advice text.
10. **Fixtures:** 15 hand-written synthetic Thai dialogues in `backend/tests/voice/fixtures/th_intake_{01..15}.json`.
    - Each file has `{dialogue_id, synthetic: true, author, scenario_tags[], patient_ref: "SYN-S3-xx", turns[], gold_facts[{field, state, value, items, span_turn_ids}], answers_by_field{field: [turn_ids]}, gold_nurse_attention: bool}`.
    - Required coverage, each tag in at least 1 dialogue:
      - allergy none using `ปฏิเสธแพ้ยา`
      - allergy present with 1–2 allergens
      - allergy UNKNOWN
      - allergy REFUSED
      - no current medications
      - 2 or more medications, including an English/Thai code-switched name (e.g. "พารา", "metformin")
      - a relative speaking for the patient
      - a correction or superseded value
      - Thai number words
      - a field volunteered before it was asked
      - a field never answered, so it stays MISSING
      - nurse-attention phrases (at least 2 dialogues)
    - The fixtures are committed in a **separate commit before** `mock_rules.py` exists. This anti-overfitting evidence is checked from git history.
    - Dialogues 11–15 are tagged `heldout` and are reported separately.
11. **Evaluation script** `backend/app/voice/eval.py`, run via `make eval-voice`. It writes `slices/s3/eval/voice_intake_eval.json`.
    - Per-field TP/FP/FN/P/R/F1, micro-averaged over dialogues.
    - 95% percentile bootstrap CI: 2,000 resamples at dialogue (patient) level, seed 0.
    - Dev and held-out breakdown.
    - Per-turn latency p50/p95.
    - The allergy-safety count (A02).
    - The label `"system evaluation — mock rules, synthetic dialogues, not clinical performance"`.
12. **Ports.** `make dev` accepts `API_PORT` / `WEB_PORT` (defaults stay 8000/3000) and passes `API_ORIGIN` to Next. This slice runs on **8103/3103**. Playwright reads `BASE_URL` / `WEB_PORT`.

### Metric definition (field-level P/R/F1)

This is the standard slot/field-level micro P/R/F1 used for clinical information extraction. See, for example, the 2018 n2c2 medication-extraction track (Henry et al., JAMIA 2020) and ASR+LLM structured nursing documentation (Su et al., JMIR Nursing 2026, proposal ref [24]).

The evaluation uses the final fact per field at finish, with a `MISSING` prediction treated as "no prediction".

- **Scalar fields** (`chief_complaint`, `onset_duration`, `severity`, `allergy_status`), per dialogue:
  - TP: the predicted state equals the gold state and, for KNOWN, the normalized values are equal (chief complaint by code, duration by ISO value, severity by NRS or category).
  - A wrong prediction counts as 1 FP and 1 FN.
  - A prediction where the gold is absent is an FP.
  - A missing prediction where the gold is present is an FN.
- **List fields** (`allergens`, `current_medications`, `relevant_history`): each normalized item is matched as a set (case-folded, whitespace-stripped, with a local alias table for Thai/English drug names). A KNOWN empty list counts as one item `none`.
- P = TP/(TP+FP), R = TP/(TP+FN), F1 = 2PR/(P+R). If a denominator is 0, the value is reported as `n/a`, not 0 or 1.

## Out of scope

- Real audio. There is no Whisper, LiveKit, WebRTC or realtime speech-to-speech in this slice, and no external speech or LLM calls. The external adapter stays disabled.
- Department suggestion, the Case Graph Compiler/Executor, red-flag triage levels, care suggestions and the Pharma Agent. These are s2 and later.
- Medication normalization to RxNorm or TMT, and dose or frequency extraction (Pharma Agent).
- Vitals capture (the nurse measures vitals, but vitals entry belongs to the dashboard slice).
- Using s1's dataset, or shared casegraph types beyond the s0 `EvidenceItem`.
- Any real, MIMIC or hospital data. Clinical-performance claims.
- The total-time comparison against form filling, which needs a human-factors study later.
- The MedX visual theme.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S3-A01 | Field-level extraction quality on the 15 fixture dialogues (mock rules via gateway) | F1 ≥ 0.80 for **each** of `chief_complaint`, `onset_duration`, `allergy_status`. P/R/F1 and 95% bootstrap CI are **reported** (no threshold) for `severity`, `allergens`, `current_medications`, `relevant_history`, micro-overall, and the dev/held-out split | `make eval-voice` → `slices/s3/eval/voice_intake_eval.json`. pytest `test_eval_thresholds` reads the JSON and asserts the thresholds and that every field and CI key is present |
| S3-A02 | Missing or uncertain allergy is never shown as "no allergy" | 0/15 dialogues where the gold allergy is `present`, UNKNOWN, REFUSED or MISSING but the prediction is KNOWN `none`. 4/4 unit phrases map correctly: ปฏิเสธแพ้ยา→KNOWN none, แพ้เพนิซิลลิน→KNOWN present+allergen, จำไม่ได้→UNKNOWN, ไม่ขอตอบ→REFUSED. A session with no allergy turn finishes with allergy status MISSING | `test_eval_thresholds` (allergy_false_none == 0), `test_allergy_semantics[4]`, `test_missing_allergy_stays_missing`, phrase/guard regressions in `test_negative_safety.py`. The 0/15 count covers the fixtures only, not the general property |
| S3-A03 | The fixture set is valid and was committed before the rules | 15 files. Each validates against the fixture schema and has `synthetic: true` and a `SYN-` patient ref. Every required coverage tag appears ≥ 1 time (nurse-attention ≥ 2). Every gold fact has a non-empty span of existing non-agent turns. The git commit that adds the fixtures is an ancestor of the first commit that adds `mock_rules.py` | `test_fixtures_schema_and_coverage`, plus a git-log check recorded in the builder's evidence |
| S3-A04 | The next-question policy never asks for a field that is already answered | 0 `ask` actions for a field whose status is KNOWN, UNKNOWN or REFUSED, checked across simulated runs of all 15 fixtures (scripted-patient simulator driven by `answers_by_field`) and ≥ 500 generated field-state combinations | `test_policy_never_asks_answered_field` (simulation + parametrized/property test) |
| S3-A05 | Every missing required field is asked before a normal finish | In 15/15 simulated runs, each field MISSING at start is asked ≥ 1 time before `handoff(complete|attempts_exhausted)`, unless a nurse-attention interrupt occurred. At `handoff(complete)` 0 fields are MISSING. No field is asked more than 2 times. When the nurse finishes early, the response lists exactly the true MISSING set | `test_policy_asks_all_missing_before_finish`, `test_policy_max_two_asks`, `test_finish_early_lists_missing` |
| S3-A06 | Every fact carries provenance | 100% of facts from the 15 fixture runs have: a non-empty `span_turn_ids` of existing non-agent turns in the same session; `available_at_time == max(ended_at of span turns)`; `event_time`; and `extractor`, `provider`, `model_version` and `request_sha256` matching a gateway audit row. 100% of KNOWN mock facts have their matched surface text present in a cited turn | `test_fact_provenance_complete`, `test_fact_grounded_in_span` |
| S3-A07 | Time validity is enforced | `GET facts?as_of=T` returns 0 facts with `available_at_time > T`, checked at every turn boundary of 3 fixtures. The gateway input for turn k contains 0 turns with `ended_at > ended_at(k)`. Out-of-order, reversed or future-dated turns give 422 (3/3) | `test_facts_as_of`, `test_extraction_sees_no_future_turns`, `test_turn_time_validation[3]` |
| S3-A08 | No patient-facing medical advice | 0 matches of the forbidden-pattern list across: the utterance template file; every agent utterance emitted in the 15 simulated runs; and `web/app/nurse/intake/**` and its components. Thai patterns: ควรกิน, ให้กินยา, ทานยา, แนะนำให้, ไม่เป็นอันตราย, ไม่ต้องกังวล, น่าจะเป็นโรค, วินิจฉัย. English patterns: you should, take (a|this|your) medic, diagnos, prescrib, treat. 100% of emitted agent utterances are members of the template allowlist. An injection test where the mock returns advice text in every output field puts 0 of that text into any utterance or API agent-text field | `test_no_patient_facing_advice_scan`, `test_utterances_from_allowlist_only`, `test_model_text_never_spoken` |
| S3-A09 | Every model call is audited through the gateway | For the 15 fixture runs, the number of `gateway.invoke` audit rows equals the number of extraction calls made, exactly. Each row has `provider, model_version, contract_version, data_class=synthetic, request_sha256, status, latency_ms`. A transcript sentinel appears in 0 audit rows. `app/voice/**` has 0 imports of `httpx`, `requests`, `socket` or any `gateway.adapters`/provider SDK (AST scan) | `test_voice_gateway_audit_rows`, `test_voice_audit_no_transcript_text`, `test_voice_provider_isolation` |
| S3-A10 | Failures fail safe | For gateway `error`, gateway `rejected`, schema-invalid output, a span pointing to an unknown/agent/future turn, and an unknown state (5/5 cases): 0 facts written from that call, `extraction_error=true`, and next action `handoff(extraction_unavailable)`. 0 HTTP 5xx | `test_extraction_fail_safe[5]` |
| S3-A11 | The nurse-attention interrupt works deterministically | On 100% of turns containing a listed phrase (the ≥ 2 fixtures plus unit cases), the next action is `handoff(nurse_attention_phrase)` in the **same** turn, including when the gateway is forced to return `error`. The response contains no urgency level, triage category or department field | `test_nurse_attention_interrupt`, `test_interrupt_independent_of_gateway` |
| S3-A12 | API authorization and audit of human actions | For 5 endpoints × {nurse 2xx, physician 403, pharmacist 403, unauthenticated 401}, all 20 cells are correct. A non-synthetic `data_class` or a non-`SYN-` ref gives 422. A turn after finish gives 409. Start, turn and finish each write exactly 1 audit row with actor id and role | `test_voice_auth_matrix`, `test_voice_start_validation`, `test_turn_after_finish_409`, `test_voice_human_action_audit` |
| S3-A13 | Turns and facts are append-only | `UPDATE` and `DELETE` on `voice_turns` and `voice_facts` raise on SQLite (4/4), and on PG when Docker is available (otherwise SKIPPED). A correction creates a new fact with `supersedes_fact_id` and the prior fact is still readable. 0 PUT/PATCH/DELETE routes under `/api/voice` | `test_voice_append_only_sqlite`, `test_correction_supersedes`, `test_no_voice_mutation_routes`; `make test-pg` |
| S3-A14 | Output is ClinicalText-like evidence | 100% of `IntakeEvidence` items from finish validate as `casegraph.EvidenceItem`, have `data_type == "ClinicalText"`, and have `available_at_time` equal to the end of the last contributing turn | `test_intake_evidence_validates_as_evidence_item` |
| S3-A15 | The audio interface is local-only | The ASR/TTS protocols plus local stubs exist. Stub ASR returns `not_configured` with no transcript. 0 imports of whisper, livekit, openai, google.cloud.speech, azure or boto3 in the repo. 0 network attempts (the suite runs socket-blocked) | `test_audio_stubs_local_only`, `test_voice_provider_isolation` |
| S3-A16 | s0 behaviour is preserved | All s0 tests pass unchanged, including S0-A08 mock determinism for unregistered tasks and the S0-A10 isolation scan. Mock voice output carries `MOCK — not clinical`. Gateway contract version is still `0.1.0` | the full `make test` run; `test_mock_task_registry_backcompat` |
| S3-A17 | `make test` is green | Exit code 0, 0 failed, 0 errors. Skips only for the documented Docker-dependent tests. Covers backend, casegraph and web unit tests, including the new voice tests and `web/tests/voice-intake.test.tsx` | `make test` output recorded by the checker |
| S3-A18 | The nurse page works end to end in a browser | Playwright on web 3103 / API 8103 runs this flow: login `nurse1`; open `/nurse/intake`; start `SYN-S3-E2E`; type the patient turns of fixture 01; after each turn the question changes and fact rows appear with state, source-turn link and time; finish shows a summary with the handoff reason and the MISSING list. `physician1` on `/nurse/intake` sees the 403 page. 0 axe violations of severity serious or critical. The flow is keyboard-only operable. The disclaimer is visible | `web/e2e/voice-intake.spec.ts` via `make e2e WEB_PORT=3103 API_PORT=8103` |
| S3-A19 | Per-turn latency is reported | With the mock provider in process, per-turn processing p95 is ≤ 500 ms over the 15 fixture runs. p50 and p95 are recorded in the eval JSON | `make eval-voice`; `test_eval_thresholds` |
| S3-A20 | The slice ports are configurable | `make dev API_PORT=8103 WEB_PORT=3103` serves `/api/health` on 8103 and `/login` on 3103, bound to 127.0.0.1. With no variables set, the defaults are still 8000/3000 | e2e-tester `curl` check; `health.spec.ts` with `WEB_PORT=3103` |

The evaluation set is the 15 local fixture dialogues plus the listed unit cases. Results are a system evaluation of mock rules against hand-written synthetic scripts. They are not evidence of clinical extraction accuracy, and with n=15 the CIs are wide by design.

## Required test cases

Backend tests live in `backend/tests/voice/` and are run by `make test`:

- `test_fixtures_schema_and_coverage`
- `test_allergy_semantics[deny|present|unknown|refused]`
- `test_missing_allergy_stays_missing`
- `test_thai_duration_normalization` (digits, number words, เมื่อวาน, สัปดาห์, ชั่วโมง)
- `test_correction_supersedes`
- `test_policy_never_asks_answered_field`
- `test_policy_asks_all_missing_before_finish`
- `test_policy_max_two_asks`
- `test_finish_early_lists_missing`
- `test_fact_provenance_complete`
- `test_fact_grounded_in_span`
- `test_facts_as_of`
- `test_extraction_sees_no_future_turns`
- `test_turn_time_validation[reversed|out_of_order|future]`
- `test_no_patient_facing_advice_scan`
- `test_utterances_from_allowlist_only`
- `test_model_text_never_spoken`
- `test_voice_gateway_audit_rows`
- `test_voice_audit_no_transcript_text`
- `test_voice_provider_isolation`
- `test_extraction_fail_safe[error|rejected|schema_invalid|bad_span|bad_state]`
- `test_nurse_attention_interrupt`
- `test_interrupt_independent_of_gateway`
- `test_voice_auth_matrix`
- `test_voice_start_validation`
- `test_turn_after_finish_409`
- `test_voice_human_action_audit`
- `test_voice_append_only_sqlite`
- `test_no_voice_mutation_routes`
- `test_intake_evidence_validates_as_evidence_item`
- `test_audio_stubs_local_only`
- `test_mock_task_registry_backcompat`
- `test_eval_thresholds` (runs the eval in process if the JSON is stale)

PostgreSQL: `test_voice_append_only_pg` (marker `pg`; skipped without Docker).

Web unit test: `web/tests/voice-intake.test.tsx`. It checks labels on the ref, speaker and text inputs; that the question is rendered in a `role="status"` region; that the handoff banner is rendered; that the MISSING list is rendered; and that model text is not rendered as a question.

Browser test: `web/e2e/voice-intake.spec.ts` (A18).

## Clinical and safety risks

| Risk | Mitigation in this slice |
|---|---|
| Missing allergy information is recorded as "no allergy", or "ปฏิเสธแพ้ยา" is misread as a refusal to answer | Explicit MISSING/UNKNOWN/REFUSED states and Thai denial semantics (A02). Missing is never a negative. The allergy false-"none" count must be 0. |
| The agent gives the patient medical advice or reassurance | The agent speaks only fixed allowlist templates. Model text is never spoken. A scan test and an injection test cover this (A08). Handoff lines are neutral and route to the nurse. |
| An urgent symptom is disclosed but the agent keeps asking routine questions | A deterministic nurse-attention interrupt runs before extraction and independent of the gateway (A11). It assigns no triage level; the nurse decides. |
| Fabricated or ungrounded facts | Grounding checks on spans; a fact is written only when it cites existing non-agent turns (A06). Schema or provider failure gives no facts and a handoff to the nurse (A10). |
| Temporal leakage: a fact appears to be known earlier than it was said | `available_at_time` is the end of the span's last turn, `as_of` filtering is enforced, and extraction never sees future turns (A07). |
| Transcript or patient data leaves the machine | `data_class=synthetic` only, `SYN-` refs, mock provider default, external adapter disabled, audio is local stubs only, and tests run socket-blocked (A09, A12, A15). |
| Silent edits erase what the patient said | Turns and facts are append-only, corrections are versioned, and human actions are audited (A12, A13). |
| Mock-rule scores are over-read as clinical accuracy | Fixtures are committed before the rules, with a held-out subset reported separately. The eval JSON is labelled a system evaluation, not clinical performance. The mock output label is kept (A01, A03). |
| The nurse-attention phrase list is an unvalidated clinical artifact | It is marked as a placeholder, it only ever escalates toward the nurse, and it needs clinical sign-off before any use beyond simulation (Decision D1). |

## Run commands

```bash
make test                                   # all unit/contract tests incl. backend/tests/voice (offline)
make eval-voice                             # writes slices/s3/eval/voice_intake_eval.json (P/R/F1 + 95% CI, latency)
make dev API_PORT=8103 WEB_PORT=3103        # API http://127.0.0.1:8103/api/health, web http://127.0.0.1:3103/nurse/intake
make e2e API_PORT=8103 WEB_PORT=3103        # Playwright incl. voice-intake.spec.ts
make test-pg                                # optional: append-only triggers on PostgreSQL
```

## Integration notes and decisions

- **s0 files touched (additive only):**
  - `app/gateway/__init__.py`: export `register_mock_task` and `invoke_audited`.
  - `adapters/mock.py`: add the task registry.
  - `gateway/router.py`: call the service function.
  - `main.py`: include the voice router and create the voice tables.
  - `Makefile` and `web/playwright.config.ts`: port variables.

  Other slices editing the same files in parallel will need a merge. The integration-auditor should check this.
- **s2 hand-off:** `IntakeEvidence` uses the s0 `EvidenceItem` field names. When s2 publishes the shared `ClinicalText` type, map to it with an adapter. Do not change the semantics of this slice unilaterally.
- **D1 (human, not blocking the build):** clinical sign-off for the nurse-attention phrase list and the Thai utterance templates. Until then they are labelled simulation-only placeholders.
- **D2 (later step):** choice of Thai ASR (Whisper variant) and TTS, and LiveKit integration, behind the `audio.py` interface. Any external speech service needs a recorded approval under the Human Approval Policy, and synthetic audio only.
