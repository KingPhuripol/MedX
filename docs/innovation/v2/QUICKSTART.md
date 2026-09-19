# Clinical Front Door — runnable handoff

Use synthetic adult data only. Nan Hospital coordination through NTI is pending. The current deliverable is a research prototype, with no hospital trial or clinical validation claim.

## Install and run

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m innovation.v2.demo
.venv/bin/python -m uvicorn innovation.api.app:app --host 127.0.0.1 --port 8000
```

Open the two role-specific entry points: http://127.0.0.1:8000/platform for the central review and evaluation platform, and http://127.0.0.1:8000/nurse for staff-assisted nurse intake. They are separate frontend apps with separate bundles (`innovation/workspace/nurse.html` and `platform.html`, built with `make web`; DEC-0017) that share only `src/shared/` and deliberately share the same API, case store and append-only audit history. `/workspace` redirects to `/platform` and `/ui/v2` remains a recovery fallback. Use one API process; do not run multiple uvicorn workers against the same demo database. Default: offline mock, in-memory data, local demonstration physician identity. For persistence set `FRONT_DOOR_DB=artifacts/v2/demo.sqlite3` before starting. The primary case routes are `#/cases`, `#/cases/{id}/intake`, `#/cases/{id}/facts` and `#/cases/{id}/draft`; the nurse entry uses `#/voice` and can preserve an encounter ID. Restart recovers interrupted case reservations without automatically replaying uncertain provider calls; retrying that old command returns `INTERRUPTED_RUN_USE_NEW_KEY`. Reload the case and submit a new reviewed command. Interrupted runs conservatively consume one turn and eight calls from the case budget.

The CLI demo is the offline backup and checks conversation → edited proposal → accepted fact → correction → draft → modified draft → confirmation. It raises on an integrity failure rather than reporting false success.

## UI demo script

1. Create a synthetic adult case with a new ID.
2. Send `อาการ: ไอสองวัน เป็นข้อมูลสังเคราะห์`.
3. The mock creates a proposal, not a draft or a confirmed fact. Edit its value and click **ยืนยันข้อมูลที่เลือก 1 รายการ**. Revision increases only after confirmation.
4. Ask another question to see missing-information guidance. Mock supports explicit prefixes `อาการ:`, `ประวัติ:`, `แพ้ยา:`, `ยา:`, `รายงาน:`; it does not claim general clinical language understanding.
5. Click **เตรียมร่างส่งต่อ**. Inspect evidence and outstanding items.
6. Expand the draft edit form, change the summary and enter a reason. Save; the new draft revision still requires confirmation. Confirm it explicitly.
7. Add a fact or correction. Existing drafts become stale. Current facts and full event history are separate views.

The nurse website exposes staff-assisted voice intake and system readiness. The central platform exposes case review, Agent Design and system readiness according to the signed-in role. Each website links to the other, but does not mix the other's primary workflow into its navigation. Voice transcription only fills an editable draft; staff must explicitly press **ตรวจแล้ว ส่งให้ผู้ช่วย**. In Agent Design, run the four visible stages in order: ค้นหา, ตรวจ validation, ตรึงแบบ and ประเมิน held-out. Raw design IDs and JSON are available only under the evaluator disclosure panel.

A failed network mutation exposes **ตรวจคำขอเดิม** and retains its exact body/key in page memory. Resolve it before making another mutation. Unsent conversation text is stored in session storage per encounter and survives a page refresh; credentials and uncertain mutation bodies are never persisted there. Speech transcripts append to existing editable text and are never submitted or confirmed automatically.

Before a supervised pilot, follow `PILOT_RUNBOOK.md`. The participant must confirm that each new case contains no identifying patient information. The interface repeats the synthetic-only restriction in the navigation, page banner and create-case form.
Use `../USER_RESEARCH_PLAN.md` for the contextual-interview guide, moderated task script, observation fields and synthesis method.

## Configurable model and speech services

The custom gateway adapter remains supported. Set `FRONT_DOOR_V2_TRANSPORT=openai_compatible` for a base URL ending at `/v1`, with chat at `/chat/completions` and multipart transcription at `/audio/transcriptions`. Configure the reasoning and speech URL/model separately. No specific model is silently selected or downloaded.

See `local.env.example` for the local endpoint template. Copy values into your own untracked environment configuration. Token mode needs a private principals file in the format described in README.md. Set an actual model ID supported by your service. Run the UI first with synthetic data to validate its JSON-mode compatibility. `json_schema` is the default; select `json_object` only when required by the endpoint. In either mode Pydantic validation still runs. Unsupported capabilities, refusal/truncation, malformed results and timeouts produce explicit errors.

`FRONT_DOOR_V2_LOCAL_FREE=true` skips paid reservations only for loopback compatible endpoints. The gateway running there is responsible for staying local; this flag cannot prove that an independently operated local proxy does not forward requests. For remote paid endpoints leave it false and explicitly configure a positive budget and per-call reservation. Budget defaults remain zero. Reservations, not verified vendor bills, are reported; configure provider-side usage limits too. Model output length is bounded by `FRONT_DOOR_V2_MAX_TOKENS` (default 2048). No paid call was made during this implementation.

Microphone recording is available only when the speech adapter is configured. Record ≤60 seconds / upload ≤10 MB; review the transcript before sending. Audio is not explicitly saved by the application. External retention depends on the configured service. Completed assistant responses can be read with a local Thai browser voice, if installed. A missing voice or speech service leaves text available. Real microphone/ASR accuracy is not validated by mock transport tests.

## APIs and invariants

- `POST /v2/encounters/{id}/turns`: set `intent=conversation` to answer/propose without making a draft. Omitted intent retains the previous v2 draft behaviour.
- `POST /v2/runs/{run_id}/proposals/{proposal_id}/accept`: reviewed `fact`, `expected_revision`, `idempotency_key`. Applies the same event/correction service as manual capture. Another case revision invalidates the proposal.
- `GET /v2/encounters/{id}/snapshot`: current eligible evidence, excluding future/label/superseded facts.
- `GET /v2/tools`: fixed registry input/output schemas and roles.
- `GET /v2/capabilities`: configured capabilities and honest mock/live-validation-pending status.

Model inference occurs outside the SQLite transaction. One durable reservation per case prevents concurrent inference from overspending the case call budget. Human edits remain possible during inference; changed revisions return `NEEDS_REVIEW` and do not publish a draft. Provider and designer do not write facts directly. All tool calls pass role/schema checks and trace accounting.

The application is a shared synthetic laboratory, not a tenant-isolated hospital system. Authentication does not imply per-patient clinical authorization. Legacy routes remain available, and disabling v2 leaves additive tables intact. Never delete tables to roll back. Files under `sources/` remain read-only.

## Experiments

Use a new output filename for each run:

```sh
python3 -m innovation.v2.evaluation regression --output artifacts/v2/regression-new.json
python3 -m innovation.v2.evaluation search --suite families --output artifacts/v2/search-new.json
python3 -m innovation.v2.evaluation freeze --suite families --input artifacts/v2/search-new.json --design fixed --output artifacts/v2/selection-new.json
python3 -m innovation.v2.evaluation heldout --suite families --input artifacts/v2/selection-new.json --output artifacts/v2/heldout-new.json
```

The fixed selection above is a reproducible pipeline demonstration, not automatic final research selection. Select a design with validation evidence after team review. `--provider external` uses configured inference; `--llm-designer` additionally uses the configured design capability. Without it, feedback search is explicitly a deterministic heuristic. Random search uses equal candidate and evaluation budgets; LLM designer overhead is additional and should be reported separately from candidate inference costs.

`data/scenarios/v2/families.tsv` contains 120 separately written synthetic vignettes with presentation, contextual evidence state and workflow challenge. `families.py` deterministically expands IDs/time/corrections into each world and expected visible evidence, with 60 development / 30 validation / 30 test fixed before variation. They are not clinician-validated or statistically independent disease families; related complaints and repeated workflow patterns remain limitations. The previous 120 factorial configurations remain accessible via `--suite factorial`. The 24 regressions remain separate.

State/action checks use code; the content report audits citations and, for mock extractive summaries, unexpected/omitted lines. Free-form clinical truth and semantic entailment remain `HUMAN_REVIEW_REQUIRED`. Simulator expectation mismatches are invalid simulations before any agent invocation. The optional language simulator scaffold is not a validated conversational patient. Repeated mock runs measure reproducibility, not LLM reliability. Report failures, invalid runs, reserved cost, unknown actual billed cost, latency, success rate and pass^5 separately.

## Hospital-specific adaptation later

Confirm the participating unit, actual handoff form, clinical review rubric, staff workflow and technology constraints. Keep the current profile and experiment history unchanged; add a new versioned profile for confirmed local requirements. No HIS integration, automatic treatment/referral, autonomous clinical deployment or expert approval is implied by completing this prototype.
