# V2D — Nurse review and confirmed handoff of an ambient voice intake into a case (backend)

Planner: innovation-lead. Revision 2, 2026-09-30 (rev 2 fixes checker findings: D8 names the one allowed edit to an existing test; 3.2 defines which 4xx write `voice.review.denied`, puts JSON parse errors in scope, and D6 now measures both plus the check order). Branch: `factory/v2d` (base a27e4b1, which already carries v2a and v2t). Gantt owner: ภูริณัฐ (Voice Agent, PROPOSAL row 16).
Sources: `docs/PROPOSAL.md` §1.3.1 ("ส่งข้อมูลให้ Case Graph เสนอแผนกที่ควรเข้ารับบริการให้พยาบาลยืนยัน"), §3.1, §3.5, Table 3.2. Also `docs/DECISIONS.md` 2026-09-30 "V2 voice direction": the nurse reviews and confirms the facts, and only then do they go to the case as ClinicalText and feed the existing department suggestion. That entry is the owner approval this slice builds on. It closes **D-V1-2** and the v2c carry-over **D-V2C-4**. The proposal wins on any conflict.

This is a research prototype that uses synthetic data only. The system suggests. The nurse confirms twice: first the facts on the phone, then the department in the web app.

## 1. User and job

A nurse at the bedside has finished an ambient voice session (v2a) on the phone (v2c) and has made one decision on each of the 6 intake rows. The backend must then:
- accept those decisions exactly once;
- put **only nurse-approved facts** into the patient's case as ClinicalText-family evidence, time-stamped at confirmation;
- carry any red flag into the case where nothing downstream can hide it;
- run the **existing** triage assessment, so the case shows up in `/nurse/triage` with red-flag alerts first and then a department suggestion or an explicit abstention. The nurse confirms the department there, in the existing UI.

## 2. Scope

**In scope.**
- The endpoint `POST /api/voice/sessions/{id}/review`, which is new: `backend/app/voice/` router, a new module `review.py` and the models.
- Append-only tables `voice_reviews` and `voice_review_decisions`, with SQLite and PG triggers in `voice/db.py`.
- The smallest triage change that lets voice cases join the fixture cases:
  - a case lookup that returns fixture cases plus voice cases, used by `GET /api/triage/cases`, `POST /cases/{ref}/assess` and `GET /cases/{ref}/confirmed`;
  - voice alert injection in assess.
  The existing assess logic is reused through one shared function. It is not copied.
- Audit events, tests and a `docs/DECISIONS.md` line that closes D-V1-2 and D-V2C-4, citing the 2026-09-30 approval.

**Out of scope.**
- `mobile/` or `web/` changes. The orchestrator wires the response into `mobile/` after merge. The web triage UI is unchanged.
- Audio, STT, realtime and deployment.
- Real patients and external providers.
- Guided-mode review.
- A vitals or demographics entry path (D-V2D-1).
- Deriving `symptom.*` from voice facts (D-V2D-5).
- Changes to the red-flag phrase list, the S4 ruleset rf-1.1.0, the department baseline, the Model API Contract or v2a contracts 1–3.
- Using ambient fixtures 11–15, which are v2a held-out. Tests use dev fixtures 01–10 or hand-authored turns only.

## 3. Contract

### 3.1 Request (fixed by the orchestrator to match `mobile/lib/review.ts` on factory/v2c, which already sends it; do not rename)

`POST /api/voice/sessions/{id}/review`. Nurse role only. The body is strict (`extra="forbid"`, 422 on unknown keys):

```
ReviewPayload = {
  session_id: str, patient_ref: str,
  decisions: [{field: str, action: "confirm"|"edit"|"reject"|"add"|"unknown",
               value: str|null, original: str|null, reason?: str (<=200)}]  (1..16 items),
  consent_acknowledged_at: AwareDatetime,
  red_flag_acknowledged_at: AwareDatetime|null
}
```

The client first calls `POST /finish`. A 409 there means the session is already finished, which is fine. Then it calls `/review`. Any 2xx means submitted.

### 3.2 Validation. Order is normative. Every failure makes zero case writes.

"Case writes" means rows in `voice_reviews`, `voice_review_decisions` and `triage_assessments`, and any new entry in `/api/triage/cases`.

- **Order.** Checks run top to bottom; a request that fails several checks gets the status and `detail` of the first failing row. Row 1 runs before the body is read, so authentication always wins over any body problem (e.g. logged out + malformed JSON → 401, not 422).
- **Denied audit.** Row 1 (401/403) is the shared `require_nurse` and writes **no** `voice.review.denied` row (unchanged behaviour of every voice route). Every failure in rows 2–17 writes **exactly one** audit row `voice.review.denied` `{status, reason}`, where `reason` is the `detail` string of that row (`schema_invalid` for row 2).
- **Parse errors are in scope (row 2).** Malformed JSON, an empty body and a JSON value that is not an object are row-2 failures, the same as a schema error. Mechanism is the builder's choice (e.g. read the raw body in a dependency that runs after `require_nurse`); FastAPI's own pre-handler body parsing must not be the path, because it skips both the auth-first order and the denied row.

| # | Check | Status | `detail` |
|---|---|---|---|
| 1 | not logged in / not nurse | 401 / 403 | existing `require_nurse` |
| 2 | body parses as a JSON object, and it matches 3.1 (types, enum, extra keys, missing keys, naive datetimes) | 422 | a list of error objects (FastAPI shape); audit `reason` `schema_invalid` |
| 3 | session exists | 404 | `voice session not found` |
| 4 | `body.session_id == {id}` | 422 | `session_id_mismatch` |
| 5 | session `mode == "ambient"` | 422 | `session_not_ambient` |
| 6 | session `status == "finished"` | 409 | `session_not_finished` |
| 7 | session `data_class == "synthetic"`, `patient_ref` matches `^SYN-`, and `body.patient_ref == session.patient_ref` | 422 | `not_synthetic` / `patient_ref_mismatch` |
| 8 | case_ref `"V-" + patient_ref` is ≤ 64 chars | 422 | `case_ref_too_long` |
| 9 | no review exists for this session (UNIQUE `session_id`; an IntegrityError on a race also gives 409) | 409 | `review_exists` |
| 10 | `consent_acknowledged_at` ≤ first turn `started_at` (if any turn) and ≤ now + 60 s | 422 | `consent_time_invalid` |
| 11 | the session had a red flag (any turn `nurse_attention`) ⇒ `red_flag_acknowledged_at` not null | 422 | `red_flag_ack_required` |
| 12 | no red flag ⇒ `red_flag_acknowledged_at` is null; if given, it is ≥ `started_at` of the first attention turn and ≤ now + 60 s | 422 | `red_flag_ack_unexpected` / `red_flag_ack_time_invalid` |
| 13 | the decision fields are exactly the 6 `ASK_ORDER` fields, each once. A missing, extra, duplicate or unknown field (e.g. `allergens`) fails | 422 | `decision_fields_mismatch` |
| 14 | the action is allowed for the field status (3.4) | 422 | `action_not_allowed` |
| 15 | `original` equals the display value (3.3) for confirm/edit/reject, and is null for add/unknown | 422 | `original_mismatch` |
| 16 | confirm: `value` equals the display value (3.3) | 422 | `confirm_value_mismatch` |
| 17 | edit/add: `value.strip()` is 1..500 chars. reject: `value` is null. unknown: `value` is null or `"ผู้ป่วยไม่ทราบ"`, and it is ignored | 422 | `value_invalid` |

"now" is the server clock (`app.state.voice_clock` if set). It is also the confirmation time `submitted_at`.

### 3.3 Display value (the "latest system fact" a confirm must equal)

The server recomputes what the v2c phone showed for each row. The input is the session's `field_statuses` and latest facts, as returned by `GET /api/voice/sessions/{id}`. This mirrors `mobile/lib/voice.ts` `rows()`/`knownValue()` on factory/v2c f6bcf6d. The strings are constants in `voice/review.py`.

| Field status | Field | Display value |
|---|---|---|
| MISSING | any | none (the row has no system value) |
| UNKNOWN | any | `ผู้ป่วยไม่ทราบ` |
| REFUSED | any | `ผู้ป่วยไม่ตอบ` |
| KNOWN | not `allergy_status` | `factText(latest)`: `value_text.strip()` if non-empty, else a list joined with `", "`, else `str(value)`. An empty result gives `ยังไม่มี` |
| KNOWN | `allergy_status`, **negative allowed** (latest allergy_status KNOWN, `value=="none"`, not `allergy_conflict`, not `extraction_error`) | `ไม่มีประวัติแพ้ยา` |
| KNOWN | `allergy_status`, `allergy_conflict`, or `value != "present"` | `ข้อมูลแพ้ยายังไม่ชัด ตรวจในหน้าตรวจทาน` (UNCLEAR) |
| KNOWN | `allergy_status` present | `factText(latest allergens)` if allergens is KNOWN, else `factText(allergy_status)`. An empty result, or one matching `/ไม่แพ้\|ไม่มีประวัติแพ้/`, gives UNCLEAR |

### 3.4 Decision → case outcome ("final")

| Field status | Action | Final in the case |
|---|---|---|
| KNOWN | confirm | the system fact becomes a KNOWN `VoiceFact`: same value/value_text/span/extractor/provider/model_version/request_sha256, with `supersedes_fact_id` = system fact id. **allergy_status:** a negative-allowed row gives `value "none"`, and this is the only way `"none"` can reach a case. A present row gives `"present"` plus the latest KNOWN `allergens` fact. UNCLEAR gives **no fact**, and the field goes to `missing_fields` |
| UNKNOWN / REFUSED | confirm | no fact → `missing_fields` |
| KNOWN / UNKNOWN / REFUSED | edit | a KNOWN `VoiceFact`: `value` = nurse text, `value_text` = nurse text, `extractor:"nurse_review"`, `provider:"human"`, `span_turn_ids:()`, `supersedes_fact_id` = system fact id or null. **allergy_status:** `value` is `null` and the nurse's words are in `value_text` only. Free text is never parsed into `none` or `present` |
| MISSING | add | as for edit, with `supersedes_fact_id: null` |
| KNOWN / UNKNOWN / REFUSED | reject | no fact → `missing_fields`. The rejected value exists only in `voice_review_decisions.original` |
| MISSING | unknown | no fact → `missing_fields` |
| MISSING | confirm / edit / reject | 422 `action_not_allowed` |
| not MISSING | add / unknown | 422 `action_not_allowed` |

Every final fact has `available_at_time = submitted_at`. `event_time` is the system fact's `event_time` for a confirm, and `submitted_at` for an edit or add. `fact_id` is `vr:{review_id}:{field}`. `missing_fields` = the `ASK_ORDER` fields with no KNOWN final fact.

### 3.5 Response: `201 Created`

```
{
  "review_id": "<32 hex>", "session_id": str, "patient_ref": str, "case_ref": "V-<patient_ref>",
  "submitted_at": ISO, "red_flag": bool,
  "triage_path": "/nurse/triage/<assessment_id>" | "/nurse/triage",
  "evidence_item_ids": ["voice:<sid>:review:<rid>:facts", "voice:<sid>:review:<rid>:transcript"?],
  "confirmed_fields": [KNOWN final fields, ASK_ORDER order, "allergens" after "allergy_status"],
  "missing_fields": [...],
  "department_suggestion": {
    "status": "suggested" | "abstained" | "pending",
    "assessment_id": str|null, "as_of": ISO|null, "reason": str|null,
    "top3": [{code, label_th, label_en, score}]   // [] unless suggested
    "missing_information": [...], "alert_rule_ids": [...], "escalation_required": bool|null,
    "label": "Suggestion for nurse review"
  }
}
```

The response has no fact values and no transcript text. `department_suggestion` is mapped from the automatic assessment as follows:
- department `suggested` → `suggested`;
- `abstained` or `error` → `abstained`, with the department `reason`;
- the assessment itself raised → `pending`, with `assessment_id` null, `reason:"assessment_unavailable"` and `triage_path:"/nurse/triage"`. The review is still committed and still returns 201.

## 4. Behaviour

**B1. Persist in one transaction.** One transaction writes:
- one `voice_reviews` row: `review_id` PK, `session_id` UNIQUE, `patient_ref`, `case_ref`, `reviewer_id`, `reviewer_role`, `submitted_at`, `consent_acknowledged_at`, `red_flag`, `red_flag_acknowledged_at`, `attention_turn_ids_json`, `evidence_json`, `case_facts_json`;
- six `voice_review_decisions` rows: `review_id`, `session_id`, `field`, `action`, `original`, `final_value`, `final_state` (`KNOWN` or `none`), `system_fact_id`, `reason`, `actor_id`, `decided_at = submitted_at`;
- the audit rows in B5, written on the same connection (`insert_audit`).

Both new tables are append-only. They go in `APPEND_ONLY`, with SQLite `BEFORE UPDATE/DELETE` triggers and PG `UPDATE/DELETE/TRUNCATE` triggers, created idempotently. `voice_sessions.status` is not changed by the review.

**B2. Evidence (ClinicalText family, `casegraph.data.CLINICAL_TEXT_TYPES`; no new evidence type).** The review produces these items:
- `VoiceIntakeFacts`, with `item_id voice:{sid}:review:{rid}:facts`. `facts` holds the KNOWN finals only. It also carries `missing_fields`, `handoff_reason:"nurse_review"` and the session's `allergy_conflict`.
- `IntakeTranscript`, with `item_id …:transcript`, if the session has turns. All turns are included, speaker `unknown` is kept, and `available_at_time = submitted_at`.
- Both items have `source:"voice.review"`, `provenance:"voice_session/{sid}/review/{rid}"`, `version:"v2d-1"`, `data_class:"synthetic"`, `patient_ref`, `available_at_time = submitted_at`, and `event_time` = the first turn `started_at` (or `submitted_at` if there are no turns).

The transcript is stored evidence only. In this slice nothing re-extracts facts from it, so a rejected utterance cannot re-enter as a fact.

**B3. Triage case.** Every voice case has `case_ref = "V-" + patient_ref`. All reviews of one patient add to the same case.
- **S4 facts.** Only the KNOWN finals of `chief_complaint` and `onset_duration` become S4 `IntakeFact`s:
  - `kind` is the field name and `value` = `value_text[:500]`;
  - `fact_id` is `vr:{rid}.{field}`, `available_at_time` = `submitted_at`;
  - `source:"voice.review"`, and provenance as in B2.
- **Everything else.** Severity, allergy, medications and history have no S4 kind. They live in the evidence only.
- **Missing inputs.** Age, sex and vitals have no source in this slice, so the S4 snapshot lists them in `missing_required()` and the department **abstains** (`required_information_missing`). Nothing fabricates them.
- **Case list.** `GET /api/triage/cases` returns voice cases first. Red-flag voice cases come first, newest first, then the other voice cases, newest first, then the 40 fixtures in their existing order.
  - Each voice item has `{case_ref, chief_complaint, suggested_as_of, source:"voice_review", red_flag}`. `chief_complaint` is the latest KNOWN reviewed chief complaint, or null; `suggested_as_of` is the latest `submitted_at`.
  - Fixture items are unchanged and have exactly 3 keys.
- **`as_of` window.** The C3 window for a voice case is `[earliest submitted_at, latest submitted_at + skew]`. It works when the case has zero S4 facts.

**B4. Red flag carried as a non-suppressible Alert.**
- **When the alert is added.** Every assessment of a voice case whose `as_of` is ≥ the `submitted_at` of any red-flag review gets one triage `Alert`. It is **prepended** to `alerts`, and `escalation_required` becomes `true`. The alert fields are:
  - `rule_id:"voice.nurse_attention"`
  - `ruleset_version:"voice-attention-placeholder-1"`
  - `severity:"escalate"`
  - `evidence_refs`: `voice_review/{rid}` and `voice_turn/{tid}` for every attention turn
  - `name_en:"Red-flag phrase heard during voice intake"`
  - `name_th:"พบสัญญาณที่ต้องประเมินเร่งด่วนระหว่างซักประวัติ"`
  - `message_en:"A nurse-attention phrase was heard during the ambient voice intake and acknowledged by the nurse. Assess the patient now per unit protocol. Placeholder phrase list, not clinically validated."`
  - `message_th:"ระบบได้ยินคำที่ต้องให้พยาบาลประเมินระหว่างการบันทึกเสียง และพยาบาลรับทราบแล้ว ให้ประเมินผู้ป่วยทันทีตามแนวปฏิบัติของหน่วยงาน (รายการคำเป็นตัวอย่าง ยังไม่ผ่านการรับรองทางคลินิก)"`
- **What it survives.** The alert is added after the S4 engine and the Case Graph, and does not depend on either. A department output, a graph failure, or a later review without a red flag cannot remove it. The existing `/confirm|/edit|/reject` rule (`alerts_not_acknowledged`, 409) then forces the nurse to acknowledge it.
- **Other text.** No transcript text appears in the alert.

**B5. Audit.** Every audit row carries the actor id and role and the server `ts_utc`. Audit rows never contain turn text, decision values or reason text; reasons appear as `reason_sha256` only.
- `voice.review.submit` `{review_id, session_id, case_ref, mode:"ambient", decisions:[{field, action, changed: bool, system_fact_id}], confirmed_fields, missing_fields, evidence_item_ids, red_flag}`
- `voice.review.consent_ack` `{review_id, session_id, consent_acknowledged_at}`
- `voice.review.red_flag_ack` `{review_id, session_id, red_flag_acknowledged_at, attention_turn_ids}` (only if `red_flag`)
- after commit: `voice.review.handoff` `{review_id, case_ref, assessment_id|null, department_status, error_type|null}`, plus the existing `triage.assess` row from the reused assess path
- `voice.review.denied` `{status, reason}` for each failure in 3.2 rows 2–17 (none for row 1)

**B6. Automatic assessment.** After commit, the review handler runs the shared assess function at `as_of = submitted_at`, with the same nurse as actor. This is the code `POST /api/triage/cases/{ref}/assess` uses: S4 engine, Case Graph, fail-safe, `triage.assess` audit and `triage_assessments` insert. The nurse can later assess again from `/nurse/triage`. Department confirmation stays in the existing triage review endpoints and UI, which are unchanged.

## 5. Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| V2D-D1 | Full suite green | `make test` exit 0; 0 failures; new skips are `pg`-marked only | `make test` output in the checker report |
| V2D-D2 | Happy path | Fixture th_ambient_01 via API → finish 200 → review with confirm ×4, edit ×1 (`onset_duration`), reject ×1 (`relevant_history`) → **201** with the exact 3.5 keys. The stored `VoiceIntakeFacts` has exactly the KNOWN finals of 3.4 (edited value = nurse text; `relevant_history` absent and in `missing_fields`). Every stored evidence item has `data_type ∈ CLINICAL_TEXT_TYPES`, `available_at_time == submitted_at` and `provenance == voice_session/{sid}/review/{rid}`. `GET /api/triage/cases` lists `V-SYN-V2A-01` at index 0. `department_suggestion.status == "abstained"`, `missing_information ⊇ {age, sex, vitals.hr, vitals.rr, vitals.sbp, vitals.spo2, vitals.temp_c, vitals.avpu}`, `assessment_id` resolves via `GET /api/triage/assessments/{id}` | `test_review.py::test_happy_path_confirm_edit_reject` |
| V2D-D3 | Rejected or unknown facts never enter the case as positive facts | For every field × {reject, unknown, confirm-of-UNKNOWN/REFUSED}: 0 `VoiceFact`s for that field, the field is in `missing_fields`, and 0 S4 facts of that kind. A rejected chief complaint whose words are in the transcript gives 0 `chief_complaint` S4 facts and 0 `symptom.*` facts | `test_review_case.py::test_rejected_and_unknown_never_positive` (parametrized, ≥ 12 cases) |
| V2D-D4 | Allergy never becomes `none` unless the nurse confirmed a system `none` | Across all 7 cases the case holds `allergy_status value "none"` **only** in case (a): (a) confirm on negative-allowed (fixture 01) gives `"none"`; (b) missing + unknown; (c) missing + add "ไม่แพ้ยา"; (d) KNOWN none + reject; (e) KNOWN none + edit "ไม่แพ้"; (f) `allergy_conflict` + confirm UNCLEAR; (g) fixture 03/10 UNKNOWN + confirm. Cases (b)–(g) give no fact or `value null` | `test_review_case.py::test_allergy_none_only_by_nurse_confirm` |
| V2D-D5 | Red flag is required, carried and shown first | Fixture 06 (or 09) with `red_flag_acknowledged_at: null` → **422** `red_flag_ack_required`, 0 case writes. With the ack → 201, `red_flag:true`. In the case list the case is at index 0 with `red_flag:true`. The assessment has `alerts[0].rule_id == "voice.nurse_attention"`, alerts serialized before `department`, and `escalation_required:true`. `/confirm` without the ack → 409 `alerts_not_acknowledged`; with it → 200. The alert is still present in: a re-assessment after a second non-red-flag review of the same patient; a run with `casegraph_run.run_graph` monkeypatched to raise; and a run with a department provider returning `error` | `test_review_redflag.py` (≥ 5 tests) |
| V2D-D6 | Validation → correct 4xx, denied audit, order, zero case writes | (a) Each row of 3.2 #2–#17 has ≥ 1 test with the exact status + `detail` (row 2: status 422 and `detail` is a list), plus: physician and pharmacist → 403; logged out → 401; guided → 422; active → 409; unknown id → 404; 2nd review → 409; 5 and 7 decisions, a duplicate field, and `allergens` as a field → 422; confirm value ≠ display (incl. raw `"none"` on an UNCLEAR row) → 422. (b) **Parse errors** as a logged-in nurse: malformed JSON (`b"{"`), empty body, and JSON `[]` → each 422 with exactly 1 new `voice.review.denied` `{status:422, reason:"schema_invalid"}`. (c) **Denied audit count**: every case in (a)/(b) for rows 2–17 adds exactly 1 `voice.review.denied` row whose `{status, reason}` equals the response; every 401/403 case adds 0. (d) **Order**: logged out + malformed JSON → 401; pharmacist + malformed JSON → 403; unknown session id + schema-invalid body → 422 `schema_invalid`; body `session_id` ≠ path on a guided session → 422 `session_id_mismatch`; active red-flag ambient session without ack → 409 `session_not_finished`; second review whose decisions are also wrong → 409 `review_exists`. (e) After every case: `voice_reviews`, `voice_review_decisions` and `triage_assessments` counts unchanged, and `/api/triage/cases` unchanged | `test_review_validation.py` (parametrized) |
| V2D-D7 | Append-only and audit | On SQLite, `UPDATE` and `DELETE` on `voice_reviews` and `voice_review_decisions` raise. The PG equivalents (including TRUNCATE) pass under `make test-pg` when PG is available, and are otherwise reported as skipped. After D2 there is exactly 1 each of `voice.review.submit`, `voice.review.consent_ack` and `voice.review.handoff`; after D5, 1 `voice.review.red_flag_ack`. Each has `actor_id`, `actor_role:"nurse"` and `ts_utc`. No audit `details_json` contains any turn text, edited value or reason text (substring check over all rows) | `test_review_audit.py`, `test_pg_voice_review.py` (`pg` marker) |
| V2D-D8 | Guided mode and fixture triage unchanged | (a) `git diff --name-only --diff-filter=MD a27e4b1..HEAD -- backend/tests casegraph/tests tests web mobile` prints **only** `backend/tests/voice/test_api_audit.py` (or nothing). (b) That file's one allowed edit is in `test_no_voice_mutation_routes`: the two counts `len(voice_routes) == 5` and `len(paths) == 5` become `== 6` for the new review route; `git diff -U0 a27e4b1..HEAD -- backend/tests/voice/test_api_audit.py` has exactly 2 `-` and 2 `+` code lines, and they differ only in `5`→`6` (a trailing `#` comment is allowed). No other assertion in that test or file changes. (c) With no reviews, `/api/triage/cases` equals the pre-slice 40-item list (same order and 3 keys). (d) The guided `POST /review` → 422 | checker runs both git commands; `test_review_case.py::test_fixture_case_list_unchanged` |
| V2D-D9 | End-to-end mobile sequence | One test reproduces `submitFlow` exactly: login nurse → start `{mode:"ambient"}` → turns (`speaker:"unknown"`, `source:"asr"`, `asr_model`) → `GET` session → decisions built by a test-local port of 3.3 from the GET payload → `POST /finish` 200 → `POST /review` 201. A second variant calls finish twice (409, treated as done) and then review → 201. Retrying review → 409 | `test_review_e2e.py::test_mobile_submit_flow` (+ `_finish_409_variant`) |
| V2D-A10 | Time validity | Assess of `V-…` at `as_of < submitted_at` → 422 `as_of_before_evidence`. An assessment at `as_of` between two reviews sees only the first review's S4 facts and alert. No stored item or fact has `available_at_time > submitted_at` | `test_review_case.py::test_time_validity` |
| V2D-A11 | Fail safe | With `triage_engine.assess` patched to raise → 201, `department_suggestion.status "pending"`, `assessment_id null`, `triage_path "/nurse/triage"`, review and decisions committed, `voice.review.handoff` with `error_type`. A case with 0 S4 facts (cc and onset rejected) is listed, and assess → 201 with `abstained` | `test_review_case.py::test_pending_on_assess_failure`, `::test_zero_s4_facts` |
| V2D-A12 | Contract shape | The request model is exactly 3.1 (strict). The response keys are exactly 3.5. `department_suggestion.status ∈ {suggested, abstained, pending}` in every test | `test_review.py::test_response_shape` |
| V2D-A13 | Records | `docs/DECISIONS.md` has a dated line: D-V1-2 and D-V2C-4 closed by v2d under the 2026-09-30 "V2 voice direction" approval (not a new approval) | checker reads the file |

## 6. Required test cases (new files only, under `backend/tests/voice/`)

- **Fixtures.** Dev fixtures only:
  - 01: allergy none, happy path
  - 02: allergy present
  - 03 or 10: allergy unknown
  - 04: refused and correction
  - 06 or 09: red flag
  - 07: field never answered → MISSING row → add or unknown

  Fixtures 11–15 are **not** read. Turns are posted through the API with `app.state.voice_clock` fixed after the last turn's `ended_at`.
- **Probed gold.** The planner ran these fixtures through the API on a27e4b1 with the mock provider.

  | Fixture | Field statuses | Display values (3.3) | Session flags |
  |---|---|---|---|
  | 01 | all 6 KNOWN | `มีไข้`, `3 วัน`, `ปานกลาง`, `ไม่มีประวัติแพ้ยา`, `ไม่ได้กินยาอะไร`, `ไม่มีโรคประจำตัว` | `allergy_conflict` false, `extraction_error` false, `nurse_attention` false |
  | 03 | `allergy_status` UNKNOWN, the rest KNOWN | allergy row `ผู้ป่วยไม่ทราบ` | — |
  | 06 | cc and onset KNOWN (`เจ็บหน้าอก`, `1 ชั่วโมง`), 4 MISSING | — | `nurse_attention` true |
  | 07 | `relevant_history` MISSING; allergy present | allergy row `ซัลฟา` | — |

- **Gold for D2** (fixture 01; the checker recomputes it independently from 3.3/3.4):
  - `confirmed_fields == [chief_complaint, onset_duration, severity, allergy_status, current_medications]`
  - `missing_fields == [relevant_history]`
  - `allergy_status.value == "none"`
  - `onset_duration.value_text` == the nurse's edit text
  - S4 facts are exactly `chief_complaint = "มีไข้"` and `onset_duration` = the edit text
- **Gold for D5** (fixture 06): the 4 MISSING rows use `add` or `unknown`.
- **Cross-module.** Assess, confirm, edit and reject on a `V-` case use the unchanged `/api/triage/assessments/*` endpoints.

## 7. Clinical and safety risks

| Risk | Control in this slice | Residual |
|---|---|---|
| An unreviewed or rejected fact reaches the case | 6/6 decisions required; only KNOWN finals are written; the transcript is never re-extracted (D3) | the transcript is visible to readers as raw evidence |
| Missing allergy read as "no allergy" | `none` only via confirm of a system `none` shown as `ไม่มีประวัติแพ้ยา`; free text is never parsed (D4) | a nurse who types "ไม่แพ้" gets text, not structured `none` (D-V2D-2) |
| Red flag lost between phone and triage | ack required; alert prepended after engine and graph; escalation; ack before department confirm (D5) | the phrase list is a placeholder pending D4 clinical sign-off |
| Fabricated certainty with no vitals | the S4 required-field check abstains, and missing information is listed (D2, A11) | voice cases cannot reach `suggested` until D-V2D-1 |
| Stale or forged review | server-side display recomputation; original/confirm equality; one review per session; finished sessions only | depends on the mobile copy strings (D-V2D-3) |
| Decision uses future evidence | `available_at_time = submitted_at`; as_of window; per-as_of alert filter (A10) | none known |

## 8. Decisions

- **D-V2D-1 (open, owner).** There is no path yet for vitals or age/sex into a voice case, so every voice case abstains. A later slice must add nurse vitals entry, as §1.3.1 says the nurse measures vitals.
- **D-V2D-2 (planner default).** A structured allergy `none` comes only from confirming the system's `none`. Nurse free text for allergy is stored as text with `value null`.
- **D-V2D-3 (planner default, integration).** 3.3 mirrors the v2c display strings (PROPOSED_V2C, which are pending owner copy approval D-V2C-2). A copy change there makes confirms 422. After merge, the orchestrator adds a cross-check test that reads `mobile/lib/copy.ts`.
- **D-V2D-4 (planner default).** Voice cases use `case_ref "V-" + patient_ref`, so they never collide with fixture refs such as `SYN-S4-001`. Refs over 62 chars are rejected (422).
- **D-V2D-5 (planner default).** No `symptom.*` facts are derived from voice facts. Symptom red-flag rules on voice cases show as not evaluable, which is visible and not negative.

## 9. Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/v2d
.venv/bin/python -m pytest -q backend/tests/voice -k review      # pyproject sets pythonpath . and backend
.venv/bin/python -m pytest -q backend/tests/triage backend/tests/voice casegraph/tests
make test
make test-pg          # if a PG URL is available; else report D7-PG as skipped
git diff --name-only --diff-filter=MD a27e4b1..HEAD -- backend/tests casegraph/tests tests web mobile   # D8a: only test_api_audit.py
git diff -U0 a27e4b1..HEAD -- backend/tests/voice/test_api_audit.py                                      # D8b: only the two 5->6 counts
```
