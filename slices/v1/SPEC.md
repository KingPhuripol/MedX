# V1 — MedX Live: a mobile Thai voice screen that fills the intake

Planner: Opus lead (2026-09-29). Source plan: `~/.claude/plans/cuddly-churning-sparkle.md` (owner-approved).
Approval: `docs/DECISIONS.md` 2026-09-29 "Voice agent via OpenAI Realtime (synthetic audio only)".
Branches: W1 `factory/v1-backend`, W2 `factory/v1-web`, both from `main` 61ab4c9. The integrator merges them into `factory/v1-voice`.
Roles: planner/reviewer = lead. Builders = W1 and W2 (they never read `.env` or any key; every test mocks the vendor).
Checker = `e2e-tester`, which runs the live check in §7 after the owner's permission rule is in place.

## 1. Goal and safety rules

Goal: a nurse holds a phone next to a synthetic/role-play patient. MedX speaks the next intake question in Thai. It hears the answer, and the existing rules-based intake fills the facts live on screen. When the conversation ends, the case hands off into the existing nurse flow.

How it works: the vendor realtime model is used only for **speech in and speech out**. Everything else stays in the existing pipeline:
- `POST /api/voice/sessions/{id}/turns` → Model Gateway (mock) extraction → the deterministic policy picks the next question.

Safety rules. All are binding; the reviewer fails the slice on any breach.

| # | Rule |
|---|---|
| S1 | **The policy picks the question.** The only text the model is ever asked to speak is `next_action.utterance_th` from a `/turns` or `/sessions` response. That text comes from the allowlist in `backend/app/voice/utterances_th.py`. |
| S2 | **The model speaks the given text verbatim.** Every `response.create` is out-of-band (`conversation:"none"`). Its only input is one user message containing that text. The model never sees patient audio or transcripts in a response context, so it cannot answer the patient. |
| S3 | No advice, reassurance, diagnosis or disease naming by the model. The session instructions say so (Thai + English). On-screen captions always show the **server text**, never the model's output transcript. The model transcript is never displayed, stored or posted. |
| S4 | Each completed input transcription becomes a normal patient turn through `/turns`, the same as typed text. The facts are extracted server-side by rules, with evidence (`span_turn_ids`). |
| S5 | Research-prototype disclosure: the global `Disclaimer` stays first on `/live`. A vendor banner (warning tone) reads **"เสียงถูกส่งไปยัง {vendor_label} — ใช้กับบทสังเคราะห์เท่านั้น"** and is visible in every state except `disabled`. |
| S6 | Red-flag cue (`nurse_attention`) and allergy conflict (`allergy_conflict`) show as **critical** `Notice` with `role="alert"` (AlertOctagon icon plus text). This deliberately upgrades U5 §6.3, which used warning for the allergy banner; on a call screen it must interrupt. A red-flag cue also ends listening (§2.6). |
| S7 | Nurse role only (backend `require_nurse`, frontend `RoleGuard role="nurse"`). |
| S8 | The vendor key is server-side only. The browser gets a client secret that is valid for 60 s to connect. The secret, the key and the access code are never written to the audit log, the application log, `localStorage` or the URL. |
| S9 | Half-duplex. The mic track is disabled while MedX speaks, plus a 300 ms tail. Any transcription from audio that started while MedX was speaking is dropped. Barge-in is not supported (documented limitation). |
| S10 | Fail safe. Vendor down, disabled, mic denied or rate-limited → a clear Thai error plus the text fallback. The screen never shows fabricated facts or questions. |

Out of scope:
- a voice-session → triage ingestion API (see Decisions required, D-V1-2);
- barge-in;
- LiveKit;
- Realtime function calling;
- storing audio.

## 2. `/live` screen contract (W2)

### 2.1 Route and shell
- Files: `web/app/live/layout.tsx` and `web/app/live/page.tsx`. `/live` sits **outside AppShell**, under the root layout, so the global `Disclaimer` renders first.
- Hide the root `.site-header` on this route by adding `[data-live-root]` to the existing selector at `web/app/globals.css:90`. This is the only change W2 makes to `globals.css`.
- `page.tsx` renders `<RoleGuard role="nurse"><Suspense><LiveCall/></Suspense></RoleGuard>`. `useSearchParams` needs the Suspense boundary in Next 15.
- Query parameters, all optional:
  - `case=<SYN-…>` sets the `patient_ref`;
  - `run=<id>` is kept for the handoff link;
  - `session=<voice_session_id>` continues an existing session through `GET /api/voice/sessions/{id}`.
- Default `patient_ref`: `SYN-LIVE-` plus 6 random uppercase hex characters. It can be edited only in `idle`, through `Field` "รหัสผู้ป่วยสังเคราะห์" with pattern `SYN-[A-Za-z0-9-]+`.
- Exactly one `h1`, visible: `<h1><Wordmark/> Live</h1>`, accessible name "MedX Live".
- `layout.tsx` exports:
  - `metadata` = { title "MedX Live", `manifest: "/manifest.webmanifest"`, `appleWebApp: { capable: true, title: "MedX Live", statusBarStyle: "black-translucent" }`, `icons.apple: "/icons/apple-touch-icon.png"` };
  - `viewport` = { width "device-width", initialScale 1, viewportFit "cover" }.
  - No `themeColor` in TS: hex literals are banned outside `theme.css`, so the manifest carries the colour.

### 2.2 Layout regions (mobile-first 390×844 and 430×932; also usable at 1280)

```text
[global Disclaimer — unchanged]
live-root  (min-height 100dvh, background var(--call-bg), color var(--call-fg), padding = safe-area insets)
 ├ header ≤56px: h1 "MedX Live" · case chip "ผู้ป่วยสังเคราะห์ · SYN-…" (live-case-chip) · timer mm:ss (live-timer) · ✕ (live-close, 44×44, aria-label "ปิด MedX Live")
 ├ banners: vendor banner (warning, compact one line) · critical alerts · extraction warning
 ├ centre (flex:1): orb (live-orb, decorative aria-hidden) → status line (live-status, role="status", aria-live="polite")
 ├ captions: question 20px/700 lang="th" (live-question) · last patient line 16px var(--call-muted) "คุณพูดว่า: …" (live-last-utterance)
 ├ bottom sheet "ข้อมูลที่กรอกแล้ว" (live-sheet), light card on the dark surface, collapsed peek ≤136px
 └ controls (padding-bottom max(16px, env(safe-area-inset-bottom))):
     [mute 56px] [END 72px round, var(--call-end)] [พิมพ์แทน 56px]  — icon + 14px label under each
```

- At **≥1024px** there are two columns. The call column is centred, max 560px. The sheet is a right panel 360px wide, expanded by default, with its toggle hidden.
- At 390×844 and 430×932, in `idle` and in `listening`:
  - the End/Start button's bounding box lies fully inside the initial viewport (no scroll needed);
  - `document.documentElement.scrollWidth ≤ clientWidth` (no horizontal overflow).
- Touch targets are ≥44×44 px. Type is 14/16/20/28 px only. Spacing follows the U5 §6.1 scale. The `:focus-visible` ring on the dark surface uses `--call-focus`.

### 2.3 Orb
- It is a CSS element: a radial gradient of `--orb-core` → `--orb-mid` → `--orb-edge`, with `box-shadow: var(--orb-glow)`. No Canvas.
- Size: 200px at <430, 240px at ≥430, 280px at ≥1024.
- Level:
  - A Web Audio `AnalyserNode` computes RMS, smoothed to 0..1. It reads the **mic stream** in `listening` and the **remote stream** in `speaking`.
  - A `requestAnimationFrame` loop writes `el.style.transform = scale(1 + 0.3*level)` directly. There is no React state per frame and no CSS var for the level.
- `connecting`: CSS shimmer (rotating gradient, 1.6 s).
- `processing`: slow pulse.
- `prefers-reduced-motion: reduce`: no scale, shimmer or pulse. The orb is static and the state is conveyed by the status text and an icon only.
- The orb conveys no information by colour alone; the status line is always present.

### 2.4 States and exact Thai copy
`live-root` carries `data-state`, which tests rely on. `live-status` text:

| data-state | Status line | Notes |
|---|---|---|
| `disabled` | "โหมดเสียงยังไม่เปิดใช้งาน — ใช้การพิมพ์แทนได้" + reason line | Reasons: `voice_disabled` "ผู้ดูแลระบบยังไม่เปิดโหมดเสียง"; `not_configured` "ยังไม่ได้ตั้งค่าบริการเสียง"; `access_code_not_configured` "ยังไม่ได้ตั้งรหัสเข้าใช้โหมดเสียงสำหรับเดโมสาธารณะ". The text form is open by default; turns work. Container `live-disabled`. |
| `idle` | "พร้อมเริ่มสนทนา" | Sub-line: "พยาบาลถือเครื่องไว้ใกล้ผู้ป่วย แล้วกดเริ่มเมื่อพร้อม". The centre button `live-start` "เริ่มสนทนา" replaces END. If `access_code_required`, show `Field` "รหัสเข้าใช้โหมดเสียง" (`live-access-code`, type=password, autocomplete=off, kept in memory only). |
| `connecting` | "กำลังเชื่อมต่อ…" | |
| `listening` | "กำลังฟัง…" | When muted: "ปิดไมค์อยู่ — แตะปุ่มไมค์เพื่อเปิด" |
| `processing` | "กำลังบันทึก…" | From transcription completed until the next `response.create` is sent |
| `speaking` | "MedX กำลังพูด…" | Between `output_audio_buffer.started` and `.stopped` |
| `error` | "การเชื่อมต่อขัดข้อง" + cause line | Buttons `live-retry` "ลองใหม่" and `live-type-toggle`. Causes are listed in §2.4.1. The container is `live-error`, `role="alert"`. |
| `ended` | "จบการสนทนาแล้ว" | Summary (§2.6) |

#### 2.4.1 Error causes (exact copy)

| Cause | Copy |
|---|---|
| mic denied | "ไม่ได้รับสิทธิ์ใช้ไมโครโฟน — อนุญาตในการตั้งค่าเบราว์เซอร์ หรือพิมพ์แทน" |
| insecure context | "ต้องเปิดผ่าน HTTPS จึงจะใช้ไมโครโฟนได้" |
| 403 `access_code_invalid` | "รหัสเข้าใช้ไม่ถูกต้อง" (returns to `idle` with the field error) |
| 429 | "เริ่มสนทนาบ่อยเกินไป ลองใหม่ในอีกสักครู่" |
| 502/504 or SDP failure or `pc.connectionState==="failed"` | "เชื่อมต่อบริการเสียงไม่สำเร็จ" |

Non-fatal events do not change the state. They show a one-line caption hint:

| Event | Hint |
|---|---|
| transcription `failed`, or empty after normalisation | "ไม่ได้ยินชัดเจน กรุณาพูดอีกครั้ง" (no turn is posted) |
| `response.done` with status ≠ completed | "เสียงขัดข้อง — โปรดอ่านคำถามบนจอให้ผู้ป่วยฟัง" |

### 2.5 Bottom sheet "ข้อมูลที่กรอกแล้ว"
- **Header and toggle:** `live-sheet-toggle` is a button with `aria-expanded` and the label "ข้อมูลที่กรอกแล้ว {known}/{total}". `total` counts the `field_statuses` entries, which are the 6 ask fields. When collapsed, the sheet shows the 2 most recent rows. Swipe-up is optional; the button is required.
- **Fact rows** (`live-fact-row`, `data-field`): one per fact from `GET /api/voice/sessions/{id}`, which gives the latest fact per field. Each row shows:
  - a check icon (aria-hidden);
  - the Thai field label, using the `FIELD_LABELS_TH` below;
  - `value_text` (Thai, as said; `lang="th"`);
  - the normalised value in muted 14px, from the existing `displayValue(fact, speakers)`, which keeps the "stated by nurse" caveat;
  - **"จากประโยค #n"**, where n is the `seq` of the first `span_turn_ids` turn.
- **Missing fields:** each `MISSING` field is a grey `StatusChip tone="neutral"` (`live-missing-chip`, `data-field`). If `not_elicited`, add " (ถามครบ 2 ครั้งแล้ว)".
- `FIELD_LABELS_TH` goes in `web/lib/voice.ts` (additive export):

  | Field | Label |
  |---|---|
  | chief_complaint | "อาการสำคัญ" |
  | onset_duration | "ระยะเวลาที่เป็น" |
  | severity | "ความรุนแรง (0–10)" |
  | allergy_status | "ประวัติแพ้ยา" |
  | allergens | "ยาที่แพ้" |
  | current_medications | "ยาที่ใช้อยู่" |
  | relevant_history | "โรคประจำตัว/ประวัติเดิม" |

  Also add the optional `value_text?: string` to the `Fact` type.
- **Alerts** above the orb, all rendered from the session payload:

  | Condition | Test id | Tone | Copy |
  |---|---|---|---|
  | `nurse_attention` | `live-alert-nurse-attention` | critical, role=alert | "พบสัญญาณอันตราย: มีคำพูดที่ต้องให้พยาบาลประเมินทันที" |
  | `allergy_conflict` | `live-alert-allergy-conflict` | critical, role=alert | "ข้อมูลแพ้ยาขัดแย้ง: คำตอบภายหลังไม่ตรงกับประวัติแพ้ยาที่บันทึกไว้ ระบบคงประวัติเดิมไว้ — พยาบาลโปรดยืนยันกับผู้ป่วย" |
  | `extraction_error` | `live-alert-extraction` | warning | "ระบบสกัดข้อมูลไม่สำเร็จ — พยาบาลบันทึกต่อเอง" |

### 2.6 Controls, flow and end
- **Mute** (`live-mute`, `aria-pressed`): toggles `track.enabled`. Labels: "ปิดไมค์" / "เปิดไมค์".
- **พิมพ์แทน** (`live-type-toggle`, `aria-expanded`): opens `live-type-form` with:
  - `select` labelled "ผู้พูด": ผู้ป่วย / ญาติ / พยาบาล, default ผู้ป่วย;
  - `input` labelled "ข้อความ", `lang="th"`;
  - submit button "ส่ง".

  It posts the same `/turns` with `source:"typed"`. The selected speaker is also used for voice turns.
- **END** (`live-end`, label "จบการสนทนา", `var(--call-end)` background with `var(--card)` icon and label): closes the realtime connection, then `POST /finish`, then `ended`.
- **Automatic end:**
  - `next_action.action === "handoff"` → speak the handoff utterance, wait for `output_audio_buffer.stopped` (or a 10 s fallback), then the same as END.
  - `nurse_attention` → the critical alert shows immediately on the `/turns` response, the mic is disabled at once, then the same as the handoff flow.
  - Timer reaches 0 → END. At 30 s left the timer text says "เหลือ 0:30" and the status line says "ใกล้หมดเวลา".
- **✕ close:** closes the realtime connection and releases the mic and the wake lock without finishing. It navigates to `/app/queue`, or back to the case when `case` and `run` are set. The session can be continued with `?session=`.
- **Summary** (`live-summary`, its `h2` receives focus). It shows:
  - "เหตุผลที่ส่งต่อ: {Thai reason}". Thai reasons:
    - complete "ตอบครบทุกหัวข้อ";
    - attempts_exhausted "บางหัวข้อยังไม่ได้คำตอบหลังถาม 2 ครั้ง";
    - nurse_attention_phrase "พบคำพูดที่ต้องให้พยาบาลประเมินทันที";
    - extraction_unavailable "ระบบสกัดข้อมูลไม่พร้อม";
    - finished_by_nurse "พยาบาลจบการสนทนา".
  - "หัวข้อที่ยังขาด: …" or "ไม่มี";
  - "หลักฐานที่บันทึก: {evidence.length} รายการ";
  - the fact rows.
- **Handoff:** the primary button `live-handoff` "ส่งต่อให้พยาบาลตรวจ" navigates to `/app/cases/{case}/triage?run={run}` when both are set, else to `/nurse/triage`.
- **Wake lock:** `navigator.wakeLock?.request("screen")` on entering `listening`. Re-acquire on `visibilitychange` → visible while in a call. Release on `ended`, ✕ or unmount. A failure is silent.

### 2.7 Tokens (add to `web/app/theme.css` `:root` — ONLY these)

```css
  /* MedX Live call surface (slice v1) */
  --call-bg: #061A2E;
  --call-fg: #F5F8FB;
  --call-muted: #A9BED3;
  --call-control: #16324F;
  --call-control-border: #6F8BA8;
  --call-end: #D92D20;
  --call-focus: #B9DEFF;
  --orb-core: #B9DEFF;
  --orb-mid: #2378C9;
  --orb-edge: #0B5CAD;
  --orb-glow: 0 0 64px 16px rgba(35, 120, 201, 0.45);
```

Contrast pairs to add to `PAIRS` in `web/tests/theme.test.ts` (ratios computed by the lead):

| Foreground | Background | Required | Computed |
|---|---|---|---|
| call-fg | call-bg | ≥4.5 | 16.5 |
| call-muted | call-bg | ≥4.5 | 9.2 |
| call-fg | call-control | ≥4.5 | 12.3 |
| card | call-end | ≥4.5 | 4.83 |
| call-control-border | call-bg | ≥3 | 4.97 |
| call-end | call-bg | ≥3 | 3.64 |
| call-focus | call-bg | ≥3 | 12.5 |
| call-focus | call-control | ≥3 | 9.3 |

- Controls get `1px solid var(--call-control-border)`, because the control fill alone is only 1.34:1 against the background.
- The bottom sheet and the banners reuse the existing light tokens (`--card`, `--foreground`, `--critical*`, `--warning*`).

### 2.8 PWA
- `web/public/manifest.webmanifest`:

  ```json
  {"name":"MedX Live (ต้นแบบวิจัย)","short_name":"MedX Live","lang":"th","start_url":"/live","scope":"/","display":"standalone","orientation":"portrait","background_color":"<= --call-bg>","theme_color":"<= --call-bg>","icons":[192 png, 512 png, 512 png purpose "maskable"]}
  ```

- Icons: `web/public/icons/icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` (180). Content: the MedX wordmark text on `--call-bg`. No filename may contain "logo" (theme test). They may be generated by any local means; a committed generator is not required.
- A vitest check asserts that the manifest `theme_color` and `background_color` equal `TOKENS["call-bg"]`. It compares values; no hex literal is written in the test.

### 2.9 Entry points (shown only when `process.env.NEXT_PUBLIC_VOICE_ENABLED === "1"`)
- `web/components/clinical/AppShell.tsx`, nurse `roleTools`: add `{ href: "/live", label: "MedX Live", en: "Live voice intake", icon: <AudioLines size={18}/> }`.
- `web/components/clinical/WorkQueue.tsx`:
  - nurse role-tool card `{ href: "/live", title: "เปิด MedX Live", text: "สัมภาษณ์ด้วยเสียงภาษาไทยแบบเรียลไทม์ (บทสังเคราะห์เท่านั้น)" }`;
  - on each nurse task row of kind `intake`, a secondary link "เปิด MedX Live" → `/live?case={case_id}&run={runId}` (`live-entry-task`).
- `/live` itself always works. With voice disabled it shows `disabled` plus the text form.

### 2.10 Client realtime layer (`web/lib/realtime.ts`, W2) — see §4 for wire facts
- Exports:
  - `connectRealtime({ clientSecret, connectUrl, micStream, onEvent, onRemoteStream }) → Promise<{ send(evt), setMic(on), close() }>`;
  - `speakEvent(utteranceTh, utteranceId)`;
  - `normaliseTranscript(s)`;
  - `rmsLevel(analyser)`.
- Allowed client events: `response.create` (built only by `speakEvent`) and `input_audio_buffer.clear`. The client never sends `session.update`.
- `normaliseTranscript`: trim, then strip trailing `[.!?,…。\s]+`. If the result is empty, no turn is posted.
  - Reason: the mock extractor misses `"ไม่เคยแพ้ยาค่ะ."` with a trailing period. The lead verified that it returns `[]`, while without the period it returns `allergy_status none`.
- Turn timing, as in `VoiceIntake`:
  - `started_at = max(clientTime(speech_started), lastTurnEnd)`;
  - `ended_at = max(clientTime(transcription completed), started_at)`.
- Turn POSTs are serialised through one promise chain.
- Voice turns post `{speaker, text, started_at, ended_at, source:"asr", asr_model: <transcribe_model from the session response>}`.
- **Web hygiene:** `backend/tests/test_isolation_hygiene.py` fails on the words openai, anthropic, gemini, mistral, cohere or adapter (case-insensitive) in **any** file under `web/` (tests and e2e included), and on diagnos, prescrib or treat in `web/app` and `web/components`. The vendor name and URL therefore come only from the server (`vendor_label`, `connect_url`). No hex, rgb or hsl anywhere in `web/` except `theme.css`, tests included.

## 3. Backend contract (W1)

### 3.1 Config (`backend/app/config.py`)

Add these `Settings` fields, read in `from_env`:

| Field | Env | Default | Rule |
|---|---|---|---|
| `voice_enabled: bool` | `VOICE_ENABLED` | False | `_bool` |
| `voice_api_key: str` (repr=False) | `OPENAI_API_KEY` | "" | only ever read by the voice realtime module |
| `voice_access_code: str` (repr=False) | `VOICE_ACCESS_CODE` | "" | |
| `voice_max_session_seconds: int` | `VOICE_MAX_SESSION_SECONDS` | 300 | 60–900, else `ValueError` at startup |
| `voice_realtime_model: str` | `VOICE_REALTIME_MODEL` | `gpt-realtime-2.1-mini` | |
| `voice_transcribe_model: str` | `VOICE_TRANSCRIBE_MODEL` | `gpt-4o-mini-transcribe` | |

**Isolation rule:**
- The `PUBLIC_DEMO` check in `__post_init__` stays exactly as it is and still refuses `gateway_provider != "mock"`, `external_enabled`, `external_base_url` and `external_api_key`.
- The voice fields are **not** part of that check.
- `OPENAI_API_KEY` never populates `external_api_key`. `build_provider` and `app/gateway/**` never read any `voice_*` field.

Voice availability is computed per request, never by crashing startup:
- `voice_enabled` false → `voice_disabled`;
- `voice_api_key` empty → `not_configured`;
- `public_demo` and `voice_access_code` empty → `access_code_not_configured`.

### 3.2 Module
- New single module `backend/app/voice_realtime.py`, holding the router, rate limiter, instructions and mint call. It is included in `main.py` with `app.include_router(voice_realtime.router)`.
- It lives **outside** `backend/app/voice/` on purpose: `backend/tests/voice/test_api_audit.py::test_voice_provider_isolation` forbids network imports (`httpx`) in that directory, and the test must stay unchanged.
- It reuses `require_nurse` from `app.voice.router` and reads `voice_sessions` through `app.voice.db`.
- It uses `httpx` directly (no vendor SDK; `test_provider_isolation` forbids them). The transport is injectable for tests: `app.state.realtime_transport` (None → the default transport).

### 3.3 `GET /api/voice/realtime/config` (nurse; no audit)

200:

```json
{"enabled": bool, "reason": null|"voice_disabled"|"not_configured"|"access_code_not_configured",
 "access_code_required": bool, "max_session_seconds": int, "vendor_label": "OpenAI",
 "model": str, "transcribe_model": str}
```

`access_code_required` = `public_demo or voice_access_code != ""`.

### 3.4 `POST /api/voice/realtime/session` (nurse)

Body (extra=forbid): `{"voice_session_id": str (1–64), "access_code": str|null (≤128)}`. Checks run in this order:

| Step | Failure | Response |
|---|---|---|
| 1 | not signed in | 401 |
| 2 | not a nurse | 403 `{"detail":"voice intake is for the nurse role"}` |
| 3 | body invalid | 422 |
| 4 | not available | 503 `{"detail":{"reason":<§3.1 reason>}}` |
| 5 | rate limit: **every** attempt counts, including bad codes | 429 `{"detail":{"reason":"rate_limited"}}` + `Retry-After` |
| 6 | access code (when required) wrong or missing; compared with `hmac.compare_digest` | 403 `{"detail":{"reason":"access_code_invalid"}}` |
| 7 | voice session unknown | 404 |
| 7 | voice session not `active` | 409 |
| 8 | mint: vendor non-2xx or malformed body (`value` not starting with `ek_`, `expires_at` not int) | 502 `{"detail":{"reason":"upstream_error","upstream_status":int}}` (never echo the vendor body) |
| 8 | mint: timeout (10 s) | 504 `{"detail":{"reason":"upstream_timeout"}}` |

- Rate limit: in-memory, per app instance, **10 per 600 s** as a module constant (tests monkeypatch it).
- 200 response. Header `Cache-Control: no-store`. Body:

  ```json
  {"client_secret":"ek_…","expires_at":int,"connect_url":"https://api.openai.com/v1/realtime/calls",
   "data_channel":"oai-events","model":str,"transcribe_model":str,"vendor_label":"OpenAI",
   "max_session_seconds":int,"instructions_version":"v1-live-0.1.0"}
  ```

- Upstream request: `POST https://api.openai.com/v1/realtime/client_secrets` with `Authorization: Bearer <voice_api_key>` and `Content-Type: application/json`. The body is exact:

  ```json
  {"expires_after":{"anchor":"created_at","seconds":60},
   "session":{"type":"realtime","model":"<voice_realtime_model>","output_modalities":["audio"],
     "instructions":"<INSTRUCTIONS>",
     "audio":{"input":{"transcription":{"model":"<voice_transcribe_model>","language":"th"},
                       "noise_reduction":{"type":"near_field"},
                       "turn_detection":{"type":"server_vad","threshold":0.5,"prefix_padding_ms":300,
                                         "silence_duration_ms":700,"create_response":false,"interrupt_response":false}},
              "output":{"voice":"marin"}},
     "tools":[],"tool_choice":"none","max_output_tokens":1024,"reasoning":{"effort":"minimal"}}}
  ```

  `idle_timeout_ms` must be absent: it triggers automatic responses.
- `INSTRUCTIONS` (constant; `instructions_version` changes whenever it changes):

  > คุณคือเสียงอ่านของ MedX ซึ่งเป็นต้นแบบเพื่อการวิจัย ใช้กับบทสังเคราะห์เท่านั้น หน้าที่เดียวของคุณคืออ่านออกเสียงข้อความภาษาไทยในข้อความผู้ใช้ล่าสุดให้ตรงตามตัวอักษรทุกคำ ด้วยน้ำเสียงสุภาพ ชัดเจน ไม่เร่งรีบ แล้วหยุด ห้ามเพิ่ม ตัด เปลี่ยน แปล หรือตอบคำถาม ห้ามให้คำแนะนำทางการแพทย์ ห้ามคาดเดาโรค ห้ามปลอบใจหรือให้ความมั่นใจ ห้ามพูดสิ่งอื่นใด
  > Speak ONLY the exact Thai text in the latest user message, verbatim, then stop. Never answer, advise, reassure, name a disease, or add any words.

- **Audit** (`write_audit`): action `voice.realtime.session`, target `voice_session/{id}`, outcome `success|denied|rate_limited|unavailable|error`.
  - Details (only these): `model`, `transcribe_model`, `instructions_version`, `instructions_sha256`, `max_session_seconds`, `expires_at`, `upstream_status`, `upstream_session_id` (the `sess_…` from the response, if present), `reason`.
  - Never: the secret, the key or the access code.
  - Step 1–3 failures are not audited. Steps 4–8 are.
- **Turn provenance (additive):**
  - `backend/app/voice/models.py` `AddTurnBody` gains `source: Literal["typed","asr"] = "typed"` and `asr_model: str | None = Field(default=None, max_length=64)`.
  - `asr_model` is required iff `source=="asr"`; otherwise 422.
  - `service.add_turn` adds `source` and `asr_model` to the `voice.turn.add` audit details **only**.
  - No DB schema change. Existing clients and fixtures are unaffected.

### 3.5 Deploy (W1)
- `docs/DEPLOY-VERCEL.md`, new section "Voice (blue link only)":

  ```bash
  printf 1 | vercel env add VOICE_ENABLED production
  vercel env add OPENAI_API_KEY production          # owner pastes; sensitive
  openssl rand -hex 6 | tee /dev/tty | vercel env add VOICE_ACCESS_CODE production   # hand the code to the owner
  printf 300 | vercel env add VOICE_MAX_SESSION_SECONDS production
  printf 1 | vercel env add NEXT_PUBLIC_VOICE_ENABLED production   # build-time: shows the entry points
  ```

  Also replace "Never set … EXTERNAL_*" with a sentence saying `OPENAI_API_KEY` is used only by the voice session endpoint and the gateway stays mock. Add a smoke step: `GET /api/voice/realtime/config` as nurse → `enabled:true, access_code_required:true`. Add the recommendation of a monthly budget on the vendor project.
- `scripts/vercel_stage.sh`: add one guard after the rsync: `[ -f "$OUT/backend/app/voice_realtime.py" ] || { echo "stage missing voice realtime route" >&2; exit 2; }`. `vercel.json` `includeFiles` already covers `backend/app/**`.
- `deploy/vercel/api/index.py`: update the docstring (voice exception, DECISIONS 2026-09-29). No code change.
- `.env.example`: add `OPENAI_API_KEY=`, `VOICE_ENABLED=0`, `VOICE_ACCESS_CODE=`, `VOICE_MAX_SESSION_SECONDS=300`, `VOICE_REALTIME_MODEL=gpt-realtime-2.1-mini`, `VOICE_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe`, `NEXT_PUBLIC_VOICE_ENABLED=0`, all with empty or placeholder values.

## 4. Realtime wire facts (verified 2026-09-29; W2 uses exactly these)

Sources:
- `openai/openai-openapi` `main/openapi.yaml` (repo pushed 2026-09-28): paths `/realtime/client_secrets` (L20922), `/realtime/calls` (L20615); schemas `RealtimeSessionCreateRequestGA`, `RealtimeTurnDetection`, `AudioTranscription`, `RealtimeResponseCreateParams`, and the server-event schemas;
- https://developers.openai.com/api/docs/guides/realtime-webrtc;
- https://developers.openai.com/api/reference/resources/realtime/subresources/client_secrets/methods/create;
- https://developers.openai.com/api/docs/guides/realtime-transcription;
- https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini.

1. **Mint.** `POST https://api.openai.com/v1/realtime/client_secrets` returns `{value:"ek_…", expires_at:<unix>, session:{id:"sess_…", …}}`.
   - `expires_after.seconds` is 10–7200 (default 600). The secret may open several sessions until it expires; a started session outlives it.
   - The client connection **can override** the attached session config (spec text). Residual risk R1.
2. **Connect (browser).**
   - `pc = new RTCPeerConnection()`; `pc.addTrack(micTrack)`; `pc.ontrack` → `audioEl.srcObject = e.streams[0]` (autoplay).
   - `dc = pc.createDataChannel("oai-events")`.
   - `offer = await pc.createOffer()`; `await pc.setLocalDescription(offer)`.
   - `fetch(connect_url, { method:"POST", body: offer.sdp, headers:{ Authorization:"Bearer "+client_secret, "Content-Type":"application/sdp" } })` returns **201** with the SDP answer as text and a `Location` header holding the call id.
   - `await pc.setRemoteDescription({ type:"answer", sdp })`.
   - Session parameters come from the secret, so no model query parameter is sent.
3. **Server VAD** with `create_response:false` and `interrupt_response:false`: "the model will never respond automatically but VAD events will still be emitted". `idle_timeout_ms` (5000–30000) would auto-trigger responses, so it is omitted.
4. **Events the client handles** (JSON on `dc.onmessage`):

   | Event | Payload | Use |
   |---|---|---|
   | `session.created` | | treat as connected → `listening`, then speak the current question |
   | `input_audio_buffer.speech_started` | `audio_start_ms`, `item_id` | |
   | `input_audio_buffer.speech_stopped` | `audio_end_ms`, `item_id` | |
   | `conversation.item.input_audio_transcription.completed` | `item_id`, `content_index`, `transcript` | "ordering between completion events from different speech turns isn't guaranteed" → match by `item_id` |
   | `conversation.item.input_audio_transcription.failed` | | |
   | `output_audio_buffer.started` / `output_audio_buffer.stopped` | `response_id` | WebRTC/SIP only; drives `speaking` |
   | `response.done` | `response.status` completed/cancelled/failed/incomplete, `usage` | |
   | `error` | `error.type`, `code`, `message` | non-fatal unless `pc.connectionState` is `failed` or `disconnected` for more than 5 s |

5. **Speak** (the only `response.create` shape; built by `speakEvent`):

   ```json
   {"type":"response.create","response":{"conversation":"none","output_modalities":["audio"],
    "input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"<utterance_th>"}]}],
    "metadata":{"utterance_id":"<utterance_id>"}}}
   ```

   - There is no `instructions` field; the session instructions apply.
   - `input` replaces the context for this response ("empty array [] will clear the context"), so the model sees only the question text.
6. **After MedX speaks:** on `output_audio_buffer.stopped`, wait 300 ms, re-enable the mic and send `{"type":"input_audio_buffer.clear"}`.
7. **Model:** `gpt-realtime-2.1-mini` is in the GA session model enum. It is Realtime-only and reasoning-capable (`reasoning.effort` minimal|low|…, default low).
   - Price per 1M tokens: text $0.60 in / $2.40 out; audio $10 in / $0.30 cached / $20 out.
   - Transcription `gpt-4o-mini-transcribe` is in the `AudioTranscription.model` enum. The field is `language` (singular) for this model.

## 5. Work split (disjoint files)

**W1 — backend + deploy** (`factory/v1-backend`):
- `backend/app/voice_realtime.py` (new)
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/voice/models.py` (`AddTurnBody` only)
- `backend/app/voice/service.py` (the `voice.turn.add` audit details only)
- `backend/tests/test_voice_realtime.py` (new)
- `backend/tests/test_public_demo.py` (additions only)
- `deploy/vercel/api/index.py` (docstring)
- `scripts/vercel_stage.sh`
- `docs/DEPLOY-VERCEL.md`
- `.env.example`

**W2 — web** (`factory/v1-web`):
- `web/app/live/**`
- `web/components/live/**`
- `web/lib/realtime.ts` (new)
- `web/lib/voice.ts` (additive exports only)
- `web/app/theme.css` (§2.7 tokens only)
- `web/app/globals.css` (the one selector at :90)
- `web/components/clinical/AppShell.tsx`
- `web/components/clinical/WorkQueue.tsx`
- `web/public/manifest.webmanifest`
- `web/public/icons/*`
- `web/tests/realtime.test.ts` (new)
- `web/tests/live-call.test.tsx` (new)
- `web/tests/theme.test.ts` (PAIRS and manifest check)
- `web/e2e/live.spec.ts` (new)
- `web/e2e/theme.spec.ts` (add `{ name:"live", path:"/live", role:"nurse" }` to PAGES)

**Integrator** (main session): merge both branches, update the `docs/DECISIONS.md` 2026-09-29 voice entry (the `/live` screen; realtime used as speech I/O only; see D-V1-1), run `make test` and e2e, then deploy.

W2 must not touch `CaseWorkspace.tsx` or `backend/app/demo/**`: slice U6 is editing them concurrently.

Both workers: keep all existing tests green and do not edit existing test assertions. The one known failure is `web/e2e/voice-intake.spec.ts:36` (evidence 2 vs 7, pre-existing).

### 5.1 W1 tests (`pytest`, sockets blocked; vendor via `httpx.MockTransport` on `app.state.realtime_transport`)

| # | Test |
|---|---|
| B1 | config endpoint reports each disabled reason. Session → 503 with the same reason. No transport call is made. |
| B2 | physician/pharmacist → 403. Anonymous → 401. |
| B3 | public_demo with code set: missing code → 403; wrong code → 403; right code → 200. With `voice_access_code` empty → 503 `access_code_not_configured`. |
| B4 | The upstream request body equals §3.4 exactly (JSON compare): URL, `Authorization` header built from the settings key, `expires_after.seconds == 60`, `create_response`/`interrupt_response` false, no `idle_timeout_ms`. The 200 body has the §3.4 keys and `Cache-Control: no-store`. |
| B5 | Sentinel key `SENTINEL-KEY-…` (not `sk-`-shaped), sentinel code and returned `ek_SENTINEL…` never appear in the audit rows dump or `caplog.text`. `repr(Settings(...))` contains neither the key nor the code. |
| B6 | The 11th attempt within 600 s → 429 with `Retry-After`. Bad-code attempts count. |
| B7 | upstream 500 → 502 (no vendor body echoed); `httpx.TimeoutException` → 504; malformed body → 502. |
| B8 | unknown voice session → 404; finished → 409. |
| B9 | Isolation. `Settings(public_demo=True, session_secret=S, voice_enabled=True, voice_api_key="x", voice_access_code="c")` constructs, and `create_app` gives a mock provider (`/api/health` default_provider mock). `Settings(public_demo=True, …, external_api_key="x")` still raises. An AST scan: `voice_realtime.py` imports nothing from `app.gateway`, and no file in `app/gateway/**` mentions `voice_`. |
| B10 | `/turns` with `source:"asr"` and no `asr_model` → 422. With both, the `voice.turn.add` audit details carry them. Without them, `source=="typed"`. |
| B11 | `VOICE_MAX_SESSION_SECONDS=30` → `ValueError`. |

### 5.2 W2 tests
- **Vitest** (jsdom; mocks `RTCPeerConnection`, `navigator.mediaDevices.getUserMedia`, `AudioContext`, `fetch`, `wakeLock`):

  | # | Test |
  |---|---|
  | F1 | `connectRealtime` POSTs the offer SDP to `connect_url` with `Authorization: Bearer <secret>` and `Content-Type: application/sdp`, creates channel `oai-events`, and sets the remote answer. |
  | F2 | `speakEvent` shape equals §4.5 exactly (no `instructions`, `conversation:"none"`, a single `input_text`). |
  | F3 | The client never sends `session.update`: after a scripted run, every sent `type` is in {`response.create`, `input_audio_buffer.clear`}. |
  | F4 | A `transcription.completed` event → one POST `/turns` with `source:"asr"`, `asr_model`, speaker patient and the normalised text. The next `response.create` carries exactly the new `next_action.utterance_th`. |
  | F5 | The fact sheet renders a row with "จากประโยค #2" and missing chips from the GET session payload. |
  | F6 | `data-state` walks idle → connecting → listening → processing → speaking → listening on the scripted events. The status texts match §2.4 exactly. |
  | F7 | `nurse_attention` / `allergy_conflict` payloads render critical `role="alert"` with the §2.5 copy. |
  | F8 | Config 503 reason → `disabled` + text form. Mic denied → `error` with the §2.4.1 copy. 429 copy. |
  | F9 | Half-duplex: the mic track is disabled between `output_audio_buffer.started` and `stopped`+300 ms, and a completion whose `speech_started` fell inside that window posts nothing. |
  | F10 | END → finish → `live-summary` with the Thai reason. `live-handoff` href or navigation follows the §2.6 rule. |
  | F11 | Theme: the new PAIRS pass. The manifest colours equal the `call-bg` token. |
  | F12 | Entry links render only with `NEXT_PUBLIC_VOICE_ENABLED=1` (`vi.stubEnv`). |
  | F13 | `normaliseTranscript("ไม่เคยแพ้ยาค่ะ.") === "ไม่เคยแพ้ยาค่ะ"`; whitespace-only → "". |

- **Playwright** `web/e2e/live.spec.ts`. The real backend (mock gateway) is started by `make dev`. The vendor is fully faked:
  - `page.route("**/api/voice/realtime/config")` and `page.route("**/api/voice/realtime/session")` are fulfilled with fixtures; `connect_url` is `http://127.0.0.1:<port>/__fake-rt/calls`, also routed, returning a fake SDP answer.
  - `page.addInitScript` replaces `window.RTCPeerConnection` with a fake that exposes `window.__liveFake = { emit(evt), sent: [] }`. The mic is either the Chromium fake-media flags (`test.use({ launchOptions:{ args:["--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream"] }, permissions:["microphone"] })`) or a stubbed `getUserMedia`.
  - `page.on("request")` asserts that every request host is `127.0.0.1`/`localhost` (`make dev` loads `.env`, so this guard proves no vendor call is made).

  | # | Scenario |
  |---|---|
  | E1 | 390×844 as nurse1: `/live` → Start → emit `session.created` → question 1 is shown. Emit `speech_started`, `speech_stopped`, `transcription.completed` "เจ็บหน้าอกมาสองชั่วโมงค่ะ" → rows `chief_complaint` and `onset_duration` with "จากประโยค #2". The question becomes "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ" and `__liveFake.sent` contains a `response.create` with exactly that text. |
  | E2 | Emit "ไม่เคยแพ้ยาค่ะ." → row `allergy_status` "จากประโยค #4". |
  | E3 | END → `live-summary` "พยาบาลจบการสนทนา", missing includes ความรุนแรง → `live-handoff` → URL `/nurse/triage`. |
  | E4 | axe: 0 serious/critical in `idle`, `listening` (with the sheet expanded) and `ended`. No horizontal overflow and END/Start in viewport at 390×844 and 430×932. Page usable at 1280 (sheet panel visible). |
  | E5 | Config 503 → `disabled` and a typed turn via `live-type-form` fills a row. |
  | E6 | Physician on `/live` → the Forbidden view. |
  | E7 | Emulated `prefers-reduced-motion: reduce`: the orb's computed `animation-name` is `none` and its transform stays `none` after a level event. |

## 6. Acceptance (measurable)

| ID | Criterion |
|---|---|
| V1-A01 | `make test` green. pytest ≥ 2170 passed + all B1–B11. vitest ≥ 97 + all F1–F13. `test_isolation_hygiene.py` and `test_voice_provider_isolation` unchanged and passing. |
| V1-A02 | `npx playwright test e2e/live.spec.ts` 100% pass. The full e2e suite has only the known `voice-intake.spec.ts:36` failure. `theme.spec.ts` passes with `/live` in PAGES. |
| V1-A03 | Zero requests to any non-local host during all automated tests (E-guard, sockets-blocked pytest). |
| V1-A04 | `grep -rniE "openai" web/ --exclude-dir=node_modules --exclude=package-lock.json` → 0 hits. No hex/rgb/hsl outside `theme.css`. The only `theme.css` diff is the §2.7 block. |
| V1-A05 | Audit: a success mint writes exactly one `voice.realtime.session` row with the §3.4 keys. A dump of `audit_events` contains no `ek_`, no key sentinel and no code sentinel. |
| V1-A06 | Screenshots at 390×844 and 430×932 for `idle`, `listening` (sheet collapsed and expanded), `speaking`, `error`, `disabled` and `ended`, plus 1280×800 `listening`. They are saved to `artifacts/factory/v1/screens/` (gitignored) for the lead review. |
| V1-A07 | The staged bundle contains `backend/app/voice_realtime.py` (the stage guard passes). |
| V1-A08 | Live check L1–L8 (§7) PASS locally, then on the blue link. |

## 7. Live check protocol (checker, real key, after the owner's permission rule)

**Preconditions:**
- the owner has added the permission rule;
- `.env` has `OPENAI_API_KEY` and `VOICE_ENABLED=1`;
- **the checker never prints, echoes or writes the key.** Every artifact and log is grepped for `sk-` and `ek_` before the report.
- Budget: **≤ US$1 total**. Abort if one run exceeds $0.25.

1. **Synthetic audio.** Call `POST https://api.openai.com/v1/audio/speech` with `model: gpt-4o-mini-tts`, a female Thai-capable voice and `response_format: "wav"`. Generate:
   - L-a "เจ็บหน้าอกมาสองชั่วโมงค่ะ";
   - L-b "ไม่เคยแพ้ยาค่ะ".

   Build one WAV (mono, 16-bit, 48 kHz): 8 s silence + L-a + 12 s silence + L-b + 20 s silence. Store it in `artifacts/factory/v1/live/` (gitignored). The silences cover connect time plus MedX speaking with the mic muted; tune them if a line is lost and record the values.
2. **Chromium.**
   - Flags: `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>%noloop`, with permission `microphone`.
   - An `addInitScript` **spy** (not a fake) wraps `RTCPeerConnection.prototype.createDataChannel`. It records every sent and received data-channel message into `window.__rtLog`, with `ek_` values redacted.
   - Local run: `make dev`, nurse1, `/live` at 390×844. Then the blue link with the access code.

**Pass criteria:**

| ID | Criterion |
|---|---|
| L1 | `data-state` reaches `listening` within 10 s. Question 1 "วันนี้มีอาการอะไรมาคะ" is spoken (`output_audio_buffer.started` seen). |
| L2 | After L-a: rows `chief_complaint` (value `chest_pain`, `value_text` contains เจ็บหน้าอก, "จากประโยค #2") and `onset_duration` (`PT2H`, #2). The question shows and is spoken: "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ". |
| L3 | After L-b: row `allergy_status` (`none`, "จากประโยค #4"). The next question is "ขอทวนอีกครั้งนะคะ ถ้าให้คะแนน 0 ถึง 10 จะให้เท่าไรคะ". |
| L4 | **Verbatim:** for every response, `response.output_audio_transcript.done.transcript` equals the given `utterance_th` after removing whitespace and punctuation. **Any** deviation, and any extra words (advice or reassurance), is a FAIL and is recorded verbatim. |
| L5 | `__rtLog` sent types ⊆ {`response.create`, `input_audio_buffer.clear`}. No response is created without a preceding client `response.create`. |
| L6 | END → summary "พยาบาลจบการสนทนา"; missing = severity, current_medications, relevant_history; evidence ≥ 2. Handoff lands on `/nurse/triage`. |
| L7 | The DB `audit_events` has a `voice.realtime.session` success row, and the `voice.turn.add` rows have `source:"asr"`. No `ek_`/`sk-` in the DB dump, the server log, the Playwright trace or the report. |
| L8 | Cost report from the `response.done.usage` and transcription usage at the §4.7 prices, plus the TTS cost. Total ≤ $1. |

**Blue link:** in addition, `GET /api/voice/realtime/config` → `enabled:true, access_code_required:true`, and a wrong code → 403. Phone check by the owner: optional, same lines spoken aloud.

## 8. Risks and decisions

| ID | Item |
|---|---|
| R1 | The client secret lets a nurse-role browser override the session config (instructions) or keep a session open up to the vendor maximum. Mitigations: nurse only, access code on public, 60 s secret TTL, rate limit, client timer, synthetic only, the vendor project budget cap (owner). The policy and fact pipeline are unaffected, because model output is never stored. |
| R2 | ASR punctuation breaks rule extraction (trailing "."). It is mitigated client-side (§2.10). The rules extractor itself should be hardened in a later S3 follow-up. |
| R3 | `reasoning.effort:"minimal"` or `max_output_tokens:1024` may be rejected for this model. The live check shows a 502 with `upstream_status` 400; the fix is to drop `reasoning` (one line) and re-run. |
| R4 | Speakerphone echo is handled by half-duplex muting plus browser echo cancellation. With no barge-in, a patient who speaks during a question is lost and gets a re-ask. |
| R5 | The per-instance rate limit on Vercel is per warm instance, not global. |
| D-V1-1 | PROPOSAL §3.1 describes Realtime mode on LiveKit with Function Calling extraction. V1 instead uses direct browser WebRTC, and Realtime is used only as speech I/O, with extraction still via the Gateway rules. **Record this in DECISIONS (integrator).** |
| D-V1-2 | "Lands in triage" here means navigating to the nurse triage page or the case triage tab. Linking a finished voice session into a triage case needs a new API (a contract change), which is **out of scope and needs an owner decision**. |
