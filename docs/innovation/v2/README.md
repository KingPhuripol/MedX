# Clinical Front Door v2 — implementation handoff

**Start with [QUICKSTART.md](QUICKSTART.md) for the completed software handoff, new conversation/proposal API, compatible providers and authored-family suite.** The sections below retain the initial delivery context.

Status: synthetic research prototype, 12 September 2026. Nan Hospital participation is being coordinated through NTI; neither access to patient data nor permission to conduct a hospital trial is implied. This implementation follows the user-approved Clinical Front Door / Agent Design plan. It adds `synthetic_intake_v1`; existing ED profiles, fixtures and v1 contracts retain their meanings.

## Start and demonstrate

From the repository root, install `requirements.txt`, then run:

```sh
python3 -m uvicorn innovation.api.app:app --host 127.0.0.1 --port 8000
```

For a reproducible command-line vertical slice run `python3 -m innovation.v2.demo`.

Open http://127.0.0.1:8000/workspace (OpenAPI: `/docs`). `/ui/v2` remains a recovery fallback. The default is in-memory, offline, synthetic-only, fixed local-demo physician identity. Keep this mode on loopback. No paid provider is invoked.

1. Create an adult synthetic encounter.
2. Enter a fact and click the reviewed-data save button. Unknown, refused and unavailable are distinct states; absent fields remain absent.
3. Send a message. The assistant proposes a missing field and creates a pending draft. Conversation text is **not automatically confirmed evidence**: review it and enter the desired facts in the form.
4. To correct a fact, copy its event ID into “แก้แทน event ID”, change the value and save. Leave that field blank for a new measurement. Old events remain available.
5. Prepare a new draft, inspect its evidence links and outstanding items, then confirm it. MODIFY creates a new pending draft revision, which needs its own confirmation. REJECT revokes the current confirmation.
6. Add another fact: previous drafts become STALE and cannot be used as current handoffs.

All results remain inside the prototype. There is no automated referral, treatment, prescription, test ordering or HIS connection.

## Delivered implementation

| Area | Implementation |
|---|---|
| Case integrity | Append-only events and corrections; case revisions; timestamp-filtered snapshots; LABEL exclusion; resolver restricted to same-case evidence IDs |
| Review | Latest-decision projection, actual modified draft revisions, stale-draft rejection, backend identity, atomic idempotency/revision conflicts |
| API | Additive `/v2` encounters/events/turns/runs/drafts/reviews/transcriptions/capabilities; legacy `/v1` and unversioned routes retained |
| Runtime | Shared bounded executor; form, single and fixed designs; mandatory evidence-reference validation; 8 calls/turn, 30/case, 20 turns/case; failed-safe results |
| UI | Thai text workspace, revision/review history, evidence links, trace, push-to-talk adapter path with editable transcript and text fallback |
| Simulation | 24 explicit software regression behaviours, seeded scripted execution, isolated evaluation SQLite databases, state/action assertions |
| Design | Schema-constrained search, at most 12 candidates and 4 nodes, feedback heuristic and equal-budget random comparison, top-three validation, explicit freeze before held-out |
| External adapter | Configurable provider-neutral HTTP contract; disabled by default; persistent pre-call budget reservations; sanitized transport errors |

The legacy review projection was corrected so a later rejection revokes an earlier confirmation. Legacy MODIFY semantics otherwise remain unchanged; actual content revisions are a v2 capability.

## Persistence, identity and rollback

Set `FRONT_DOOR_DB=/absolute/path/demo.sqlite3` for persistence. Startup applies additive v2 tables/triggers, without modifying legacy tables. Back up the entire SQLite database while the application is stopped. Roll back features with `FRONT_DOOR_V2_ENABLED=false`; keep the database and its v2 tables. Do not run a destructive down migration.

For token mode set `FRONT_DOOR_AUTH_MODE=token` and `FRONT_DOOR_PRINCIPALS_FILE` to a private JSON file:

```json
{"principals":[{"subject":"staff-1","role":"intake","token":"REPLACE-WITH-RANDOM-SECRET"},{"subject":"doctor-1","role":"physician","token":"REPLACE-WITH-ANOTHER-SECRET"},{"subject":"assessor-1","role":"evaluator","token":"REPLACE-WITH-THIRD-SECRET"}]}
```

Roles come from that server file, never request fields. Intake can capture data; physicians review drafts; evaluators read only. This is one shared synthetic laboratory, **not** a multi-tenant hospital access-control system: authenticated users share its encounters. UI tokens stay in page memory. Do not commit secrets. Use one application process for this prototype; evaluation workers use separate databases. Inference now runs outside write transactions with one durable reservation per case; changed data invalidates the result. Production-scale concurrency is not claimed.

Mutations need an `idempotency_key` and `expected_revision`; creation uses the `Idempotency-Key` header. Reviews additionally carry `draft_revision` and `expected_review_sequence`. Clients must retry the same command with the same key/body after an uncertain response. A changed body or stale revision returns 409. After an uncertain UI request, reload before submitting again.

## External reasoning and speech contract

External integration requires token mode, `FRONT_DOOR_ALLOW_EXTERNAL=true`, a **separate persistent** `FRONT_DOOR_V2_BUDGET_DB`, explicit `FRONT_DOOR_V2_PAID_BUDGET_USD` and positive `FRONT_DOOR_V2_CALL_RESERVATION_USD`. Zero budget prevents transport calls. Reservations are not refunded on uncertain failures. The endpoint must enforce the per-request `max_charge_usd` ceiling; the application tracks reservations, not independently verified vendor invoices.

Configure `FRONT_DOOR_V2_PROVIDER_URL`, `FRONT_DOOR_V2_PROVIDER_TOKEN`, `FRONT_DOOR_V2_MODEL`, and optional JSON tuple `FRONT_DOOR_V2_CAPABILITIES`. HTTPS is required except loopback. Redirects are not followed. This is a **custom gateway contract**, not a direct OpenAI/Anthropic-compatible endpoint:

- `POST /infer`: receives the authorized snapshot, untrusted text, validated DesignSpec and output JSON schema. Returns `content`, `model_version`, `provider_version`; `content` follows DraftContent in `innovation/v2/models.py`.
- `POST /design`: optional `design` capability; receives development failure feedback and DesignSpec schema. No gold labels, evaluator changes, arbitrary code or held-out cases are provided.
- `POST /transcribe`: separate `FRONT_DOOR_V2_SPEECH_URL`; receives temporary base64 synthetic audio, MIME type and Thai language. Returns `{ "text": "...", "confirmed": false }`. Backend forces false even if the provider returns true. The app closes the upload and does not explicitly persist audio; configure the external service's retention separately.

Audio is limited to 10 MB and recording to 60 seconds. Speech is disabled without an adapter. A playback button reads only completed assistant responses using a local Thai browser voice; if none exists it reports text fallback. Live ASR and audible playback have not been tested with a real device. Text works without either. The reasoning adapter has no vendor credentials bundled.

Differential output requires both configuration `FRONT_DOOR_V2_DIFFERENTIAL=true` and provider capability `differential`; it is visible in physician draft projections only. Each entry requires a rationale, cited evidence, contradictions and missing information. Mock has no differential capability. Citation validation verifies IDs, **not medical truth or semantic entailment**. Clinical references, calibrated clinical rubrics, and expert-reviewed diagnostic evaluation remain pending.

## Simulation and design experiments

```sh
python3 -m innovation.v2.evaluation regression --output artifacts/v2/regression.json
python3 -m innovation.v2.evaluation search --output artifacts/v2/search.json
# Team selects a design that has validation evidence (baseline is allowed):
python3 -m innovation.v2.evaluation freeze --input artifacts/v2/search.json --design fixed --output artifacts/v2/selection.json
python3 -m innovation.v2.evaluation heldout --input artifacts/v2/selection.json --output artifacts/v2/heldout.json
```

Output files are exclusive-created: use a new versioned filename for reruns. Default execution is mock, with one process worker (`--workers` up to 4). External mode requires explicit `--provider external` and configuration. `--llm-designer` invokes the configured design adapter; otherwise “feedback” means a deterministic heuristic, not an LLM designer. Do not interpret the heuristic comparison as a trained-model result.

The 24 explicit scenarios are software regression tests. The additional 120 entries are **factorial workflow configurations**, split 60 development / 30 validation / 30 test before any language/audio variations. They are not 120 clinician-authored independent clinical scenario families. The shared generator and deterministic mock constrain interpretation. The optional constrained-language simulator is a scaffold tested separately; the main runner uses scripted simulation. Human-reviewed content rubrics, factual-simulator validation integrated into a live LLM study, independent clinical families and robustness experiments are still work to do.

Search rejects test cases. Freeze binds the selection to source, scenario, model configuration and policy hashes. Held-out runs repeat each case five times and report both success rate and pass^5; deterministic repetition demonstrates reproducibility only. No accepted clinical accuracy or under-triage threshold is invented. Current clinical verdict is `NOT_REVIEWED`.

## Team handoff and remaining milestones

Use the agreed 100 hours/week capacity (80 planned, 20 integration/review buffer). Dates below preserve the approved schedule; hospital coordination does not block synthetic software delivery.

| Owner | Next responsibility | Reviewer / backup |
|---|---|---|
| Phurinat Polasa | NTI/Nan unit and clinical contact; experimental design; select candidate after validation | Thanapol / Thanrada |
| Thanapol Popit | Live provider integration, execution timeouts, designer experiments | Supreeya / Phurinat |
| Jakkapat Bunjongruxsa | Clinically authored scenario families and simulator factual-state validation | Thanrada / Thanapol |
| Thanrada Tungweerapornpong | Independent safety/content review, split audit, clinical rubric with experts | Jakkapat / Phurinat |
| Supreeya Nuamkhayan | UI usability, speech adapter and playback, deployment and integration | Thanapol / Jakkapat |

- 11–17 Sep: review this offline vertical slice and contract; preserve legacy ED results separately.
- 18–24 Sep: review 24 regressions and text workspace; proposal draft 22 Sep; seek clinical unit/contact/evaluation format by 24 Sep.
- 25 Sep–1 Oct: validate live ASR if available; advisor-ready report 27 Sep, content freeze 29 Sep.
- 2–9 Oct: proposal 2 Oct, demo freeze 5 Oct, rehearsal/backup 7 Oct, presentation 8–9 Oct.
- 10 Oct–6 Nov: build expert-reviewed families and external-provider evidence; development/validation search.
- 7–20 Nov: team freezes candidate; held-out and robustness study; simulated staff evaluation if authorized.
- 21 Nov–15 Dec: failure analysis, progress report 4 Dec, presentation 14–15 Dec.
- Jan–May 2027: user/Thai speech evaluation and final handoff; provisional until official calendar.

No clinical deployment, live provider quality claim, hospital usability study or final research outcome is completed by this software implementation. If the partner, budget or speech adapter is unavailable, use the offline text demo and report the limitation. If search does not improve outcomes, retain the baseline and publish the negative result.
