# V2B — LiveKit STT worker (`voice_agent/`) and LiveKit token endpoint

Planner: innovation-lead (2026-09-30). Gantt owner: ภูริณัฐ. Branch: `factory/v2b` (from main `d81efae`).
Source of truth: `docs/PROPOSAL.md` §3.1 (the Voice Agent runs on LiveKit Agents; its output is a transcript that
becomes ClinicalText after review). Approvals: `docs/DECISIONS.md` 2026-09-30 "V2 voice direction" and
"D1 approved: LiveKit Cloud + OpenAI STT for synthetic audio (slice v2b)".
Roles: planner = this spec. Builder = Sonnet on `factory/v2b`. Checker runs §6. Reviewer is read-only.

Research prototype. The AI never speaks to the patient. Only synthetic audio is used. A transcript is evidence for the
nurse to review; it is never a confirmed fact.

## 1. Scope

### 1.1 `voice_agent/` package (repo root)
- A LiveKit Agents worker on the current **1.x** Python API with `agent_name="medx-scribe"` (explicit dispatch only).
- **STT only.** `AgentSession(stt=..., vad=silero.VAD.load(), llm=None, tts=None)`.
  - The `Agent` subclass overrides `on_user_turn_completed` to raise `StopResponse` (or the current 1.x
    equivalent), so no reply is ever generated.
  - The agent never publishes an audio track and never calls `say` or `generate_reply`.
- **STT switch.** `VOICE_STT_PROVIDER` defaults to `openai`. Use a plain if/else, not a factory.
  - `openai` uses `livekit.plugins.openai.STT(model=VOICE_STT_MODEL or "gpt-4o-mini-transcribe", language="th")`.
  - Any other value, including `typhoon`, makes the worker refuse to start: it exits non-zero with
    `unsupported_stt_provider`. There is no silent fallback. A self-hosted Typhoon branch is added in a later slice.
- **Transcripts reach the client** only through the framework's standard `lk.transcription` text stream, using the
  standard attributes. Final segments carry `lk.transcription_final="true"`. Do not invent a custom topic. Slice v2c
  uses stock `livekit-client` `registerTextStreamHandler("lk.transcription")`.
- The worker gets the voice session id from the room name `voice-<voice_session_id>`. It must not call the backend in
  this slice.
- **Privacy.** No audio is persisted: no recording, egress or temp `.wav` files. No transcript text goes to any log.
  Log metadata only: room, provider, model, audio seconds, segment counts, error class.
- **Commands.**
  - `python -m voice_agent dev` / `start` runs the LiveKit CLI.
  - `python -m voice_agent download-files` fetches the silero weights.
  - `python -m voice_agent transcribe <file.wav> --synthetic` runs the same STT config over a local file. It prints
    one JSON object to stdout with this shape:
    `{"schema":"voice-agent-transcribe/0.1","provider","model","language":"th","file_sha256","audio_seconds","segments":[{"index","text","start","end","final":true}]}`.
    `start` and `end` may be `null`.
  - Without `--synthetic`, a missing or non-WAV file, or an unsupported provider, the command exits 2, and no STT call
    is made. Slice v2e consumes this JSON.
- **Dependencies.** `voice_agent/requirements.txt` pins every direct dependency exactly (`==`): livekit-agents 1.x,
  livekit-plugins-openai, livekit-plugins-silero, and livekit-api. `requirements.lock` must stay unchanged, so backend
  dependencies stay lean.
- `voice_agent/README.md` (short): env vars, `download-files`, `dev`, `transcribe`, the synthetic-only rule, and the
  fact that the worker never speaks.

### 1.2 Backend token endpoint (**locked contract**; v2c builds against it in parallel)
- New module `backend/app/voice_livekit.py`. Its router is registered in `backend/app/main.py`. Mirror the structure of
  `backend/app/voice_realtime.py`.
- **Settings:** `livekit_url`, `livekit_api_key` (`repr=False`), `livekit_api_secret` (`repr=False`), read from
  `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`. `VOICE_ENABLED` is reused. Add these keys with empty
  values to `.env.example`, together with `VOICE_STT_PROVIDER` and `VOICE_STT_MODEL`.
- **`GET /api/voice/livekit/config`** (nurse only) returns `{enabled, reason, agent_name:"medx-scribe", token_ttl_s}`.
  `reason` is `null` or one of:
  - `voice_disabled`;
  - `not_configured` (any LIVEKIT_* value is empty, or the URL is not `wss://` or `ws://`);
  - `public_demo_disabled` (`PUBLIC_DEMO=1`; see D-V2B-1).

  The response never contains the URL, key or secret.
- **`POST /api/voice/livekit/token`**. The body is `{voice_session_id}` with `extra="forbid"`, so any extra field
  returns 422. The success response is 200
  `{server_url, participant_token, room, expires_at}` with `Cache-Control: no-store`, where:
  - `server_url` = `LIVEKIT_URL`;
  - `room` = `voice-<voice_session_id>`;
  - `expires_at` = the JWT `exp`, as integer Unix seconds (the same type as `voice_realtime`).
- **Order of checks.** Each failure below is audited, with the reason shown in parentheses:
  1. The caller is not a nurse: 401 or 403.
  2. The service is unavailable: 503 `{"reason": ...}`, where the reason is one of the three `config` reasons.
  3. The caller is rate limited: 429 with `Retry-After`. The limit works like `voice_realtime` (every attempt counts,
     module constants, and tests monkeypatch them).
  4. The session is unknown: 404.
  5. The session status is not `active`: 409 (`session_not_active`).
  6. The session's `data_class` is not `"synthetic"`: 409 (`data_class_not_allowed`).
- **Token.** The token is an HS256 JWT minted with the stdlib (`hmac`/`hashlib`/`base64`). Do not add a new backend
  dependency. Claims:
  - `iss` = API key;
  - `sub` = `str(nurse user id)`;
  - `nbf`, and `exp` ≤ `nbf + 600`;
  - `video` = `{room:"voice-<id>", roomJoin:true, canPublish:true, canSubscribe:true, canPublishData:false,
    canPublishSources:["microphone"]}`, with no `roomCreate`, `roomList`, `roomAdmin`, `roomRecord`, `recorder`,
    `ingressAdmin`, `hidden` or `agent` grant;
  - `roomConfig` = `{agents:[{agentName:"medx-scribe"}]}`.
- **Audit.** Write `voice.livekit.token` for **every** outcome (`success`, `unavailable`, `rate_limited`, `error`).
  - The target is `voice_session/<id>`.
  - Details are limited to: room, agent name, ttl, expires_at and reason.
  - Never include the token, its signature, the API key, the API secret or the URL.

### 1.3 Provider-isolation guards
- Update `backend/tests/voice/test_api_audit.py::test_voice_provider_isolation` and
  `backend/tests/test_isolation_hygiene.py::test_provider_isolation`.
  - Python imports of `livekit*` or `openai` are allowed **only** under `voice_agent/**` and in
    `backend/app/voice_livekit.py`. They remain violations in every other file.
  - `backend/app/voice/**` stays network-free.
  - `requirements.lock` and `web/package.json` must still not pin or depend on livekit or openai. Only
    `voice_agent/requirements.txt` may.
- Refactor each guard's scan into a helper that takes a root and a file list, so it can be tested on a `tmp_path` tree
  (see B6). Do not plant files inside the real repo.
- `mobile/` JavaScript dependencies are out of scope for this guard (D-V2B-2). Do not add a rule that would block v2c's
  `livekit-client`.

### 1.4 Makefile and tests
- `make install` adds a stamp `$(VENV)/.voice_agent_installed` that installs `voice_agent/requirements.txt` into the
  repo `.venv` without changing any version pinned in `requirements.lock`. Pick a mechanism, for example a hash-free
  constraints file derived from the lock.
- Add `voice_agent/tests` to pytest `testpaths`, so `make test` runs them. They are not skipped.
- Tests stay offline (`--disable-socket` remains), and every STT, room and LiveKit call is mocked.
- VAD weights are not needed in unit tests.

## 2. Out of scope
- Any UI: `mobile/` is slice v2c, and `web/` `/live` is unchanged.
- Ambient fact extraction and posting transcripts to `/turns` (v2a/v2c).
- Audio evaluation (v2e).
- Deploying the worker.
- Building Typhoon ASR.
- TTS, LLM, Realtime or function calling.
- Recording or egress.
- Changes to `voice_realtime.py` behaviour.

## 3. Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| B1 | Full suite green including new voice_agent and token tests | `make test` exit 0; voice_agent tests collected and 0 skipped; `git diff main -- requirements.lock` empty; `.venv/bin/pip check` exit 0; every lock-pinned package's installed version equals the lock | Checker runs `make test`, `pip check`, compares `pip freeze` to the lock |
| B2 | Token endpoint status matrix | nurse+active synthetic session → 200 with exactly keys `{server_url,participant_token,room,expires_at}` and `Cache-Control: no-store`; physician/pharmacist → 403; anonymous → 401; unknown session → 404; finished session → 409; `VOICE_ENABLED=0` → 503 `voice_disabled`; any LIVEKIT_* empty → 503 `not_configured`; `PUBLIC_DEMO=1` → 503 `public_demo_disabled`; extra body field → 422; over limit → 429 + `Retry-After`; `GET /config` mirrors each reason and has no URL/key/secret | `backend/tests/test_voice_livekit.py` (TestClient, synthetic sessions) |
| B3 | Decoded token is least-privilege | Signature verifies with the test secret; `video.room == "voice-<id>"`; exactly one room; `roomJoin, canPublish, canSubscribe` true; `canPublishSources == ["microphone"]`; `canPublishData` false; no admin/create/list/record/hidden/agent grant; `exp - nbf ≤ 600` and `exp == expires_at`; `sub == str(nurse id)`; `iss == API key`; `roomConfig.agents == [{"agentName":"medx-scribe"}]` | Backend test decodes the JWT with stdlib; a `voice_agent/tests` test also verifies the backend-minted token with `livekit.api.TokenVerifier` (proves LiveKit accepts the format) |
| B4 | No credential leakage | 0 occurrences of the sentinel API key, sentinel secret, minted token or its signature segment in any audit row or captured log record, across all B2 outcomes | Test sets sentinel `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`, dumps `audit_rows()` + `caplog.text`, asserts absence |
| B5 | Worker publishes final transcripts and never speaks | With a fake STT emitting scripted interim + final events: each final segment appears once on topic `lk.transcription` with `lk.transcription_final="true"`; 0 LLM calls, 0 TTS calls, 0 `say`/`generate_reply` calls, 0 audio tracks published by the agent; `session.llm is None and session.tts is None`; `on_user_turn_completed` raises `StopResponse`; `agent_name == "medx-scribe"` | `voice_agent/tests/test_worker.py` with a fake STT and a fake room/text-stream writer (or the framework RoomIO over a fake `rtc.Room`) |
| B6 | Isolation guard enforces the two allowed locations | On a `tmp_path` tree: `import livekit` / `from openai import X` in `backend/app/other.py`, `casegraph/x.py`, `backend/app/voice/x.py` → violations; the same in `voice_agent/w.py` and `backend/app/voice_livekit.py` → none; `livekit-agents==` in a fake `requirements.lock` → violation; the real repo scan → 0 violations | Guard helper tests in `backend/tests/voice/test_api_audit.py` and `backend/tests/test_isolation_hygiene.py` |
| B7 | `transcribe` CLI works offline with STT mocked | `python -m voice_agent transcribe x.wav --synthetic` with the STT mocked → exit 0, stdout parses as JSON with `schema=="voice-agent-transcribe/0.1"`, `language=="th"`, correct `file_sha256`, `audio_seconds` within 0.05 s of the generated wav, and scripted segments in order; without `--synthetic`, a missing file or a non-WAV file → exit 2 and 0 STT calls | `voice_agent/tests/test_transcribe.py` (generates a 1 s silent 16 kHz wav in `tmp_path`) |
| B8 | Optional live smoke, synthetic only | If `LIVEKIT_URL/API_KEY/API_SECRET` and `OPENAI_API_KEY` are all present: the worker registers with LiveKit Cloud, a token from `POST /api/voice/livekit/token` is accepted by the room, and a synthetic Thai clip yields ≥1 final `lk.transcription` segment; spend ≤ US$0.50; no secret value printed. Otherwise record `SKIPPED` (not a failure) | Checker procedure §6.3; evidence in `slices/v2b/CHECK.md` (presence of vars reported as set/unset only) |
| B9 | STT config switch fails safe | Default provider `openai`, model `gpt-4o-mini-transcribe`, language `th`; `VOICE_STT_MODEL` overrides the model; `VOICE_STT_PROVIDER=typhoon` or any unknown value → startup error `unsupported_stt_provider`, no STT constructed | `voice_agent/tests/test_config.py` |
| B10 | No audio persisted, no transcript text logged | Running the B5/B7 paths with a Thai sentinel transcript: sentinel absent from `caplog` and from stderr; no new files anywhere under `tmp_path`/cwd except the test's input wav; log records contain only the allowed metadata keys | Tests in `voice_agent/tests` |
| B11 | Existing behaviour unchanged | `backend/tests/test_voice_realtime.py` and all existing voice tests pass unmodified (except the guard edits in §1.3); `openai` is still forbidden in `web/` terms and the gateway adapter rule is unchanged | `make test`; `git diff main --stat` reviewed by checker |
| B12 | Repo hygiene | `.env.example` has `LIVEKIT_URL=`, `LIVEKIT_API_KEY=`, `LIVEKIT_API_SECRET=`, `VOICE_STT_PROVIDER=`, `VOICE_STT_MODEL=` with empty values; `test_repo_hygiene` passes; `voice_agent/README.md` states the research-prototype, synthetic-only and never-speaks rules | `make test`; checker reads README |

## 4. Required test cases (minimum)
- `backend/tests/test_voice_livekit.py`:
  - one test per B2 cell;
  - the B3 claim decode;
  - the B4 sentinel scan;
  - one audit row per call, with action `voice.livekit.token` and the correct outcome;
  - config never exposes URL/key/secret;
  - rate-limit window reset.
- `voice_agent/tests/test_worker.py` (B5, B10), `test_transcribe.py` (B7, B10), `test_config.py` (B9) and
  `test_token_compat.py` (B3 `TokenVerifier` cross-check).
- Guard tests (B6), including the helper-on-`tmp_path` cases.
- Gold labels: none. This is a transport/infra slice, and no clinical labels are produced.

## 5. Clinical and privacy risks
| Risk | Mitigation in this slice |
|---|---|
| Real patient audio is sent to a US vendor | D1 allows synthetic audio only. The session must be `data_class=="synthetic"` (409 otherwise). The CLI needs `--synthetic`. `PUBLIC_DEMO` is disabled, and the README states the rule. |
| The AI speaks or advises the patient | No LLM or TTS is present. `StopResponse` is raised, and there is no audio track (B5). |
| A Thai mis-transcription (e.g., a negated allergy "ไม่แพ้") becomes a fact | The transcript is only a caption and evidence here. Facts are extracted in v2a and confirmed by the nurse in v2c. Nothing is written to the case in this slice. |
| STT invents text during silence | VAD gating. v2e measures this; it is not claimed here. |
| A leaked token grants access to other rooms or admin | One room, microphone only, TTL ≤ 10 min, no admin grants, `no-store`, and never logged (B3, B4). |
| A transcript leaks into logs | Only metadata is logged (B10). |
| The provider fails or times out | The worker logs the error class. The client (v2c) keeps a text fallback. The worker never fabricates text. |
| Cost runaway | Rate limit, nurse-only access, TTL, public demo disabled, and a live-smoke budget ≤ US$0.50. |

## 6. Run commands
1. `make install && make test` (B1–B7, B9–B12).
2. Narrow: `.venv/bin/python -m pytest -q backend/tests/test_voice_livekit.py voice_agent/tests backend/tests/voice/test_api_audit.py backend/tests/test_isolation_hygiene.py`.
3. Optional live smoke (B8, synthetic only). `set -a; . ./.env; set +a`, then report only whether each required
   variable is set or unset.
   - Run `.venv/bin/python -m voice_agent download-files`, then `.venv/bin/python -m voice_agent dev` in the
     background.
   - Run `make dev`, log in as `nurse1`, and create a synthetic voice session.
   - `POST /api/voice/livekit/token`.
   - Join the room with a headless client (e.g., `livekit-api`/`livekit` rtc in a scratch script) that publishes a
     ≤10 s synthetic Thai TTS or recorded role-play clip.
   - Assert ≥1 final `lk.transcription` segment is received, then stop the worker.
   - Record the result, the approximate cost and any error class in `slices/v2b/CHECK.md`. Never print tokens or
     secrets.

## 7. Decisions required (do not block the build)
- **D-V2B-1:** with `PUBLIC_DEMO=1`, the token endpoint returns 503 `public_demo_disabled`, because the locked
  contract has no access-code field. Enabling it on a public demo, for example for D5 `medx-mobile`, needs an owner
  decision on access control and STT cost.
- **D-V2B-2:** `mobile/package.json` will depend on `livekit-client` (v2c). The owner or integrator should confirm
  that allowing it is covered by D1, and whether a JavaScript guard should limit it to `mobile/`.
- **Integration dependency:** v2c posts final transcripts to the backend `/turns` endpoint, and v2a extracts facts. The
  worker does not call the backend. The integrator confirms this split when v2a and v2c land.
