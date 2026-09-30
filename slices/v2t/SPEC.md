# V2T — OpenAI Realtime transcription-only session for the ambient mobile scribe (backend only)

Planner: Innovation Lead (2026-09-30). Gantt owner: ภูริณัฐ. Branch: `factory/v2t` (from main 1c2648f).
Approval: `docs/DECISIONS.md` 2026-09-30 "D1 superseded: OpenAI Realtime transcription-only instead of LiveKit", together with the vendor approval of 2026-09-29 "Voice agent via OpenAI Realtime (synthetic audio only)".
Consumers: v2c (`mobile/`) builds against §3 in parallel. v2a adds `voice_sessions.mode` on another branch.

## 1. Scope

Extend `backend/app/voice_realtime.py` with the smallest possible diff. The ambient scribe gets a short-lived client secret for an OpenAI Realtime session of type **`transcription`**. The phone then streams mic audio straight to OpenAI over WebRTC and receives transcript events only.

The slice reuses everything that already exists:
- availability reasons;
- the access code;
- the per-instance rate limit;
- the session existence and status checks;
- the `voice.realtime.session` audit;
- `Cache-Control: no-store`;
- the httpx mint call with `app.state.realtime_transport`;
- the existing test style.

**Out of scope:**
- any UI (v2c);
- extraction, the question classifier and the `mode` column or migration (v2a);
- LiveKit (it stays forbidden by the isolation guard);
- audio storage;
- Model Gateway changes;
- deployment and Vercel env changes;
- `gpt-live-transcribe` (see D-V2T-3).

**Accepted proposal deviation (owner, 2026-09-30).** Proposal §3.1 routes voice through LiveKit Agents, with the Model Gateway creating the Realtime connection config. In this slice:
- there is no LiveKit;
- the audio does not pass through the gateway (the same known weakness as V1);
- the backend mints the secret and audits every mint;
- extraction stays on the gateway path (v2a).

The builder's report must restate this deviation.

## 2. Official references (verified 2026-09-30)

- Realtime transcription guide: https://developers.openai.com/api/docs/guides/realtime-transcription (redirect target of https://platform.openai.com/docs/guides/realtime-transcription)
- Client secrets reference (the `RealtimeTranscriptionSessionCreateRequest {type, audio, include}` schema): https://developers.openai.com/api/reference/resources/realtime/subresources/client_secrets
- WebRTC with an ephemeral token: https://developers.openai.com/api/docs/guides/realtime-webrtc (section "Connecting using an ephemeral token")
- VAD in transcription sessions: https://developers.openai.com/api/docs/guides/realtime-vad
- Server events: https://developers.openai.com/api/reference/resources/realtime/server-events

What the docs say:
- A transcription session has **no** top-level `model`, `instructions`, `tools`, `output_modalities` or `audio.output`.
- `audio.input.transcription` accepts `model` and `language`. `gpt-4o-mini-transcribe` is a listed option.
- `server_vad` is supported for models that support VAD. `gpt-live-transcribe` and `gpt-realtime-whisper` need `turn_detection: null`.
- `create_response`, `interrupt_response` and `idle_timeout_ms` are used only in conversation sessions, so this slice omits them.
- The guide now *recommends* `gpt-live-transcribe`. The owner locked `gpt-4o-mini-transcribe` with server VAD instead (D-V2T-3).

## 3. Contract (LOCKED — v2c builds against it)

### 3.1 `POST /api/voice/realtime/session`
Body: `{voice_session_id, access_code?, purpose?: "guided" | "ambient"}`.
- `purpose` defaults to `"guided"`.
- Any other value returns 422. `extra="forbid"` is kept.

**The guided path is unchanged.** It sends the same upstream bytes, returns the same response and uses the same status codes as today.

Order of checks for **both** purposes (the same as today, with one new step 6):
1. Unavailable → 503 `{reason}`.
2. Rate limit → 429 `rate_limited` with `Retry-After`.
3. Access code → 403 `access_code_invalid`.
4. Unknown session → 404 `"voice session not found"`.
5. Session not `active` → 409 `"voice session is not active"`.
6. **Mode must match the purpose.** Otherwise the response is 409 `"voice session mode does not match purpose"` and the audit reason is `session_mode_mismatch`:
   - `purpose:"ambient"` requires `mode == "ambient"`;
   - `purpose:"guided"` requires `mode == "guided"`, so a speaking model can never be minted for an ambient session.
7. Mint.

Non-nurse roles still get 403 from `require_nurse`, and anonymous callers get 401. Neither writes an audit row, the same as today. When a request fails at steps 1–6, no upstream request is made.

**Reading `mode` defensively (integration with v2a).** This branch has no `voice_sessions.mode` column.
- Read the session row so that a DB column named `mode` is picked up if it exists. For example, use `text("SELECT * FROM voice_sessions WHERE session_id = :sid")` and `.mappings()`, or use `voice_sessions.c.mode` when `"mode" in voice_sessions.c`.
- A missing column, or a NULL value, is treated as `"guided"`.
- This slice adds **no** migration and **no** Table column.
- After v2a merges, the integrator may simplify this read to `voice_sessions.c.mode`. That note goes in the builder report.

**Ambient upstream request.** The method, URL, headers and timeout are the same as today. The body is exactly:
```json
{"expires_after": {"anchor": "created_at", "seconds": 60},
 "session": {"type": "transcription",
   "audio": {"input": {
     "transcription": {"model": "<settings.voice_transcribe_model>", "language": "th"},
     "noise_reduction": {"type": "near_field"},
     "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 700}}}}}
```
The session contains no `model`, `instructions`, `tools`, `tool_choice`, `output_modalities`, `audio.output`, `max_output_tokens`, `reasoning`, `create_response`, `interrupt_response`, `idle_timeout_ms` or `include`.

The upstream response is validated as today: `value` must start with `ek_` and `expires_at` must be an int. A malformed response returns 502, a timeout returns 504 and a non-2xx status returns 502.

**Response (200, `Cache-Control: no-store`).** The key set is identical to today's:
`{client_secret, expires_at, connect_url, data_channel, model, transcribe_model, vendor_label, max_session_seconds, instructions_version}`

For ambient:
- `model` = `transcribe_model` = `settings.voice_transcribe_model`;
- `instructions_version` = `"v2-transcribe-0.1.0"` (module constant `TRANSCRIBE_CONFIG_VERSION`);
- `connect_url` = `https://api.openai.com/v1/realtime/calls`;
- `data_channel` = `oai-events`.

### 3.2 `GET /api/voice/realtime/config`
Adds `ambient_supported: true` and `ambient_model: settings.voice_transcribe_model`. Every existing key stays the same.

### 3.3 Audit `voice.realtime.session`
- Every row that the endpoint writes now carries `details.purpose` (`"guided"` or `"ambient"`). This covers `unavailable`, `rate_limited`, `denied`, the `error` outcomes (404 / 409 / mode mismatch / upstream) and `success`.
- On ambient rows:
  - `model` = the transcribe model;
  - `instructions_version` = `v2-transcribe-0.1.0`;
  - `instructions_sha256` = `null`, because there are no instructions.
- The guided success key set is today's set plus `purpose`.
- The key, the minted secret and the access code never appear in audit rows, logs or error bodies.

### 3.4 Client connect flow and events (for v2c, from the official docs)
Connect flow:
1. `POST /api/voice/realtime/session {purpose:"ambient"}` returns `client_secret`.
2. Create an `RTCPeerConnection` and add **only** the mic track. No remote audio is expected; ignore `ontrack`.
3. `createDataChannel("oai-events")` **before** creating the offer.
4. Call `createOffer`, then `setLocalDescription`.
5. `POST {connect_url}` with body = `offer.sdp` and headers `Authorization: Bearer <client_secret>`, `Content-Type: application/sdp`.
6. `setRemoteDescription({type:"answer", sdp: await res.text()})`.

The secret is valid for 60 s to connect. The session may continue after that. v2c enforces `max_session_seconds` on the client.

**The client sends no client events on the data channel**: no `session.update`, `response.create` or `conversation.item.create`. The docs allow a client to override the session config, so this is a v2c acceptance item.

Server events that v2c consumes:

| Event | Fields used | Meaning |
|---|---|---|
| `input_audio_buffer.speech_started` | `item_id`, `audio_start_ms` | VAD start (UI "listening") |
| `input_audio_buffer.speech_stopped` | `item_id`, `audio_end_ms` | VAD stop |
| `conversation.item.input_audio_transcription.delta` | `item_id`, `delta` | partial text, display only, never posted |
| `conversation.item.input_audio_transcription.completed` | `item_id`, `transcript` | final text. Post one turn per `item_id` (`source:"asr"`, `asr_model` = `transcribe_model`). Completion order across items is **not** guaranteed, so order turns by `item_id`/`speech_started` |
| `conversation.item.input_audio_transcription.failed` | `item_id`, `error.code` | recommended: show "ถอดเสียงไม่สำเร็จ" for that segment. Never drop it silently |
| `error` | `error.type`, `error.code`, `error.message` | fail safe: stop recording and show the Thai error with the text fallback |

## 4. Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| T1 | Full suite green; existing V1 tests preserved | `make test` exits 0. In `backend/tests/test_voice_realtime.py` the **only** diffs vs main are two expected-value edits: B1 `test_b1_config_enabled_shape` gains the 2 config keys, and B5 `test_b5_no_secret_leaks` key set gains `purpose` (D-V2T-1). All 11 B-groups pass | `make test`. `git diff main -- backend/tests/test_voice_realtime.py` shows exactly those 2 hunks |
| T2 | Ambient upstream body exact | 1 upstream request. Its JSON equals §3.1 exactly (dict equality). The recursive key set contains none of the forbidden keys listed in §3.1. `settings.voice_transcribe_model="m-tr"` flows into `transcription.model` | `test_t2_ambient_upstream_request_exact`, `test_t2_ambient_no_output_keys`, `test_t2_ambient_model_flows_through` |
| T3 | Guided byte-identical | For explicit `purpose:"guided"` and for an omitted `purpose`: upstream `req.content` bytes are equal to each other and to a committed snapshot of today's body. The response JSON is equal to today's B4 dict | `test_t3_guided_bytes_snapshot` (fixture `backend/tests/fixtures/v2t_guided_mint_body.json`, generated from main 1c2648f `_mint_body` **before** editing the module). `test_t3_purpose_omitted_equals_guided` |
| T4 | Session, mode and role rules | Ambient on a guided session → 409, on a finished session → 409, on an unknown session → 404. Guided on an ambient session → 409. `purpose:"x"` → 422. physician/pharmacist → 403, anonymous → 401. Public demo without a code, or with a wrong code → 403. 0 upstream requests in every one of these cases | `test_t4_ambient_session_rules`, `test_t4_guided_on_ambient_refused`, `test_t4_purpose_validation`, `test_t4_roles_ambient`, `test_t4_access_code_ambient` |
| T5 | Audit + no leaks | Exactly one `voice.realtime.session` row per audited outcome, each with the correct `details.purpose`. Ambient success details = `{purpose, model, transcribe_model, instructions_version, instructions_sha256(null), max_session_seconds, expires_at, upstream_status, upstream_session_id}`. With `caplog` at DEBUG, the sentinel key, sentinel secret, access code, a wrong code and `ek_` appear in 0 audit rows, logs or error bodies | `test_t5_ambient_audit_rows`, `test_t5_ambient_no_secret_leaks` |
| T6 | Config | `ambient_supported is True`, and `ambient_model` == the configured transcribe model (default and override) | `test_t6_config_ambient_fields` |
| T7 | Contract documented | This SPEC §2–§3.4 lists the doc URLs, the connect steps and all 6 event names with their fields | Checker reads §2–§3.4 |
| T8 | Optional live mint | Only when `OPENAI_API_KEY` **and** `VOICE_ENABLED=1` are present. One ambient mint through the real endpoint returns 200. The upstream echo has `session.type == "transcription"` and `transcription.model == transcribe model`. No audio is sent and no WebRTC connection is made (~US$0). Output prints status, booleans and the model only, never a secret. Otherwise the result is `SKIPPED` (not a failure) | `python3 scripts/voice_ambient_live_check.py` (exit 0 = PASS, exit 3 = SKIPPED). This is not part of `make test`, which blocks sockets |
| T9 | Isolation unchanged | `voice_realtime.py` imports no gateway, `openai` or `livekit` module and adds no new dependency. The B9 and `test_api_audit` SDK guards pass unchanged. The gateway still reports `default_provider: mock` | existing `test_b9_module_isolation`, `backend/tests/voice/test_api_audit.py`. `git diff main -- backend/requirements* pyproject*` is empty |
| T10 | Fail-safe upstream (ambient) | Upstream 500 → 502, timeout → 504, a malformed body (4 B7 payloads) → 502. The vendor body never appears in the response, and each case writes an `error` audit row with `purpose:"ambient"` | `test_t10_ambient_upstream_failures` (parametrised like B7) |

Every new test lives in `backend/tests/test_voice_realtime_ambient.py` and reuses `make`, `login`, `Vendor`, `rt_rows` from the V1 test module (import them; do not copy them).

## 5. Required test cases (gold)

- **Ambient session helper.** If `"mode" in voice_sessions.c`, create the session through `POST /api/voice/sessions {mode:"ambient"}`. Otherwise:
  1. create a guided session through the API;
  2. run `ALTER TABLE voice_sessions ADD COLUMN mode VARCHAR(16)`, guarded;
  3. run `UPDATE voice_sessions SET mode='ambient' WHERE session_id=:sid`.

  The fixed-column trigger does not cover `mode` on this branch.
- **Gold ambient body.** The §3.1 JSON with `gpt-4o-mini-transcribe`.
- **Gold ambient response.** `{client_secret:"ek_SENTINEL_c0ffee", expires_at:1900000000, connect_url:".../v1/realtime/calls", data_channel:"oai-events", model:"gpt-4o-mini-transcribe", transcribe_model:"gpt-4o-mini-transcribe", vendor_label:"OpenAI", max_session_seconds:300, instructions_version:"v2-transcribe-0.1.0"}`.
- **Vendor stub for ambient.** Use `{"value": SECRET, "expires_at": 1900000000, "session": {"id": "sess_tx1", "object": "realtime.transcription_session", "type": "transcription"}}`. Then `upstream_session_id == "sess_tx1"`.
- **Rate limit counts ambient attempts.** Ambient and guided attempts share one window. The 11th attempt of either purpose → 429.

## 6. Clinical and safety risks

| # | Risk | Mitigation in this slice | Residual / owner |
|---|---|---|---|
| R1 | A speaking model reaches the patient in ambient mode | Transcription session type. No instructions, tools or output keys (T2). Guided purpose is refused on ambient sessions (T4) | The client could send `session.update`. v2c must send zero client events (v2c acceptance) |
| R2 | Real patient audio goes to OpenAI | The approval is synthetic only. v2c keeps the "synthetic only" banner and the consent tick | Owner / D3 key rotation still open |
| R3 | Transcript errors become facts silently | The transcript is only a Turn. Facts come from v2a extraction plus nurse confirmation. `.failed` and `error` are surfaced, not dropped (§3.4) | Thai WER is unmeasured, so report it as a system evaluation |
| R4 | The locked model/VAD config is rejected upstream or deprecated (the docs now recommend `gpt-live-transcribe`) | T8 live mint | D-V2T-3 |
| R5 | Secret or key leakage | no-store, no logging, and T5 sentinel tests | — |
| R6 | Audio bypasses the Model Gateway (Proposal §3.1) | Owner-accepted deviation. Every mint is audited with its purpose | Stated in the slice report and the final docs |

## 7. Decisions

- **D-V2T-1 (planner, contract conflict).** The task requires both "B1–B11 unchanged" and "config and audit gain new keys". B1 and B5 assert exact key sets, so both cannot hold. Resolution: exactly two expected-value edits (T1). Every other line of the V1 test file is unchanged.
- **D-V2T-2 (planner, safety).** Guided purpose on an ambient session → 409. This adds no new names or shapes, and today's guided sessions are unaffected.
- **D-V2T-3 (owner, non-blocking).** OpenAI now recommends `gpt-live-transcribe`. It has no server VAD and uses `languages:["th"]`, so it would change the event set, because v2c would need client-side commit. This slice keeps the locked `gpt-4o-mini-transcribe` + `server_vad`. Revisit only if T8 fails or Thai quality is poor.

## 8. Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/01_Projects/Senior-Project/Full-Agent/.claude/worktrees/v2t
.venv/bin/python -m pytest -q backend/tests/test_voice_realtime.py backend/tests/test_voice_realtime_ambient.py
.venv/bin/python -m pytest -q backend/tests/voice/test_api_audit.py
make test
git diff main -- backend/tests/test_voice_realtime.py      # T1: only the 2 hunks
python3 scripts/voice_ambient_live_check.py                # T8: PASS or SKIPPED; never prints secrets
```
