# Slice v2c: MedX mobile scribe app (`mobile/`)

Planner: innovation-lead (2026-09-30). Branch: `factory/v2c`. Gantt owner: ภูริณัฐ (Voice Agent, PROPOSAL row 16).

Status: **design approved 2026-09-30** (`docs/DECISIONS.md` "v2c mobile design comps approved"); **build section added 2026-09-30** (sections 9–16) against the owner's transport decision "D1 superseded: OpenAI Realtime transcription-only instead of LiveKit". Sections 1–8 are the approved design and are binding; the only edits to them are the two transport words in the 3.1 table (LiveKit room/token → realtime connection/mint), which follow the D1-superseded decision.

Source of truth: Proposal v8 §1.3.1 (Voice Agent), §2.1.6, §3.1, §3.5, Table 3.2; `docs/DECISIONS.md` 2026-09-30 (ambient + prompt scribe, separate `mobile/` PWA); `docs/UI-SPEC.md` (tokens, copy rules); `web/app/theme.css` (the only colours).

---

## 1. Design direction

### 1.1 Design read

Operate-mode mobile tool for a nurse standing at the bedside. The phone is held in one hand while the nurse talks to the patient in Thai. The patient is present and can see the screen. Ward lighting is bright, so the app uses the light theme from the tokens.

The screen has three jobs, in this order:
1. Say what to do now: the next question, a red flag, or "done".
2. Show that listening works: status, timer, level meter.
3. Show what has been captured so far.

Everything else is quiet. Dials: variance 3, motion 2, density 5.

### 1.2 Principles

1. **One slot says what to do now.** The top of the recording screen is always one block, and its content follows a fixed priority: unacknowledged red flag > all fields complete > next question. The colour of the slot carries meaning:
   - navy (`--primary-deep`) = live and asking;
   - neutral (`--nav`) = not listening;
   - green outline (`--success`) = complete;
   - red (`--critical`) = red flag.

   This slot is the one signature element. The rest of the screen stays still.
2. **Red means red flag, nothing else.** Recording uses blue, not the usual red record dot. Connection errors use the warning palette. The only red on screen is the red-flag alert, so it cannot be mistaken for anything else.
3. **The thumb does the work at the bottom.** Every tap during a session sits in the bottom 300px:
   - record / pause / resume;
   - finish;
   - acknowledge a red flag, which is the one exception (see 3.3);
   - review decisions and submit, in the sticky bar.

   The top of the screen is for reading only.
4. **The nurse asks, the app listens.** The AI never speaks. Questions are suggestions: "ใช้คำพูดของคุณเองได้". Copy talks to the nurse as a colleague, never as the product selling itself.
5. **Nothing reaches the case without a human decision.** Every fact needs confirm, edit or reject, with the transcript snippet it came from. Missing is never shown as negative. An allergy that was not captured is never displayed as "ไม่แพ้ยา".

### 1.3 Tokens (copied, never redefined)

`mobile/` uses a synced copy of `web/app/theme.css`. There are no other colour literals: no hex, rgb or named colours in components. The comp copy is `slices/v2c/comp/theme.css`.

| Role | Token | Where |
|---|---|---|
| Canvas | `--background` | page |
| Surface | `--card` | grouped lists, recorder dock, sticky bar, buttons |
| Neutral slot, selected row | `--nav` | prompt slot when not listening; selected patient row |
| Ink / secondary ink | `--foreground` / `--muted-foreground` | text; labels, timestamps, empty values, form-control borders |
| Hairlines | `--border` | list dividers, dock top edge |
| Live prompt | `--primary-deep` + `--card` text + `--primary-soft` note | prompt slot while listening; live record button |
| Accent | `--primary` / `--primary-hover` | the single filled CTA, links, focus ring, selection, level meter, "กำลังถาม" |
| Red flag | `--critical`, `--critical-fg`, `--critical-bg`, `--critical-border` | red-flag alert, flagged transcript line, acknowledged strip |
| Warning | `--warning`, `--warning-fg`, `--warning-bg`, `--warning-border` | reconnecting, error, "edited" tag |
| Success | `--success`, `--success-bg` | captured fact glyph, confirmed tag, complete slot |
| Elevation | none by default | borders before shadows; no shadow on any comp surface |

### 1.4 Type

Font is SCBXBeta2, loaded exactly as `web/` loads it (`/fonts/SCBXBeta2-{Regular,Bold}.otf`, copied into `mobile/public/fonts/`). There are four sizes and two weights. Thai text is never uppercase or letter-spaced.

| Role | Size / weight / line-height | Used for |
|---|---|---|
| Display | 28 / 700 / 1.4 | the prompt question, screen titles |
| Title | 20 / 700 / 1.4 | alert heading, complete heading, review values, timer |
| Body | 16 / 400 or 700 / 1.5 | transcript, fact values, buttons, inputs (16px also stops iOS zoom) |
| Meta | 14 / 400 or 700 / 1.5 | labels, timestamps, notes, limitation label |

- Headings and paragraphs use `text-wrap: balance` for the prompt and `pretty` for the rest, so Thai does not leave an orphan syllable on its own line.
- Times, IDs and the timer use `font-variant-numeric: tabular-nums`.

### 1.5 Spacing, shape, touch

- **Spacing:** only 4, 8, 16, 24, 32, 48 and 64 (UI-SPEC). Screen gutter 16. The safe area is `env(safe-area-inset-*)`; the comps assume 48 at the top and 16 at the bottom.
- **Radius:** 8 for controls and tags, 12 for grouped surfaces and the prompt slot. The record button is the only round control.
- **Touch:** every tap target is at least 44×44.
  - Primary CTA: 56.
  - Record button: 72.
  - Secondary buttons: 48.
  - Review actions: 44.
  - Patient rows: 64.
- **One-handed use:** during a session, the controls above plus the sticky review bar all sit in the bottom third of an 844pt screen. Nothing that must be tapped mid-conversation sits above the fold line of the thumb, except "รับทราบ" (see 3.3).

---

## 2. Screens

The comps are at 390×844 in `slices/v2c/comp/`. Screenshots are in `comp/png/`.

### 2.1 Login (`01-login.html`)

- **Top:** the MedX wordmark (text "Med" + "X" in `--primary`, the same as `web/components/Wordmark.tsx`, never the SCBX logo), a display-size heading and one line of purpose.
- **Bottom third:** username, password with show/hide, and the primary button "เข้าสู่ระบบเดโม".
- The limitation label is the last line.
- Only the `nurse` role may enter. Any other role gets the error below.

### 2.2 Start session (`02-start.html`)

- **App bar:** wordmark and the account button (`nurse1`, sign-out icon).
- **Title:** "เลือกผู้ป่วย".
- **Search input:** accepts `SYN-` ids only.
- **Patient list:** one grouped surface of radio rows. The id is bold, then sex/age, bed and arrival time. The selected row is `--nav` with a filled primary radio.
- **Mic explainer:** two short lines plus a required consent checkbox: "แจ้งผู้ป่วยแล้วว่าจะบันทึกเสียงบทสนทนา".
- **Primary button:** "เปิดหน้าบันทึก". It is disabled until a patient is selected and the checkbox is ticked.
- The microphone permission is not requested here. It is requested on the first press of the record button, in context (see 3.1).

### 2.3 Recording (`03-recording.html` + `03a`–`03f`)

From top to bottom:

1. **Patient line:** the id and sex/age/bed.
2. **Prompt slot:** see 1.2 and 3.2.
3. **"ข้อมูลที่ได้ n จาก 6 หัวข้อ":** a six-row grouped list.
   - Each row has a status glyph, a label and a value.
   - Glyphs:
     - `circle-check` in `--success` = captured;
     - `circle-dot` in `--primary` with the text "กำลังถาม" = the field the slot is asking for;
     - `circle-dashed` in muted colour with the text "ยังไม่มี" = missing.
   - This list is the only flexible region. On short screens it scrolls; the slot and the dock never move.
4. **Recorder dock** (white, hairline top edge):
   - the last 3 transcript lines. The newest is at the bottom, the interim line is in muted colour ending in "…", older lines fade out through a 16px mask at the top. Tapping opens the full transcript sheet.
   - a three-column control row:
     - left: timer and status, with the level meter;
     - centre: the 72px record button with its label below;
     - right: "จบการบันทึก".
   - the limitation label.

Transcript lines have **no speaker labels**. ASR speaker is `unknown` in contract §2, and guessing "พยาบาล/ผู้ป่วย" would be fabricated certainty.

### 2.4 Review and confirm (`04-review.html`, `04b-review-ready.html`)

- **Back link:** "บันทึกต่อ" returns to recording, paused.
- **Title:** "ตรวจทานข้อมูล", with the id and duration.
- **Instruction line.**
- **One grouped list with one item per field:**
  - **Waiting:** label, tag "รอตรวจ", value (20/700), the source snippet as a muted quote with its time ("จากบทสนทนา 10:32"), and three equal buttons: ยืนยัน / แก้ไข / ปฏิเสธ.
  - **Decided:** collapses to label + tag + value + a "เปลี่ยน" link.
  - **Editing:** replaces the value with a labelled textarea, "ค่าที่ถูกต้อง", and two buttons: "บันทึกการแก้ไข" and "กลับไปตรวจสอบ".
  - **Edited:** shows "ระบบได้ยินว่า: …" under the new value.
- **Sticky bottom bar:** progress "ตรวจแล้ว n จาก 6 หัวข้อ" and the one filled primary button, "ยืนยันและส่งเข้าเคส".
  - It is disabled until every field has a decision.
  - Under it: "ระบบจะเสนอแผนกจากข้อมูลที่ยืนยันแล้ว และรอพยาบาลยืนยันอีกครั้งในเคส".
- **Acknowledged red flag:** if the session had one, the acknowledged strip (3.3) is pinned above the title. It is also sent with the case.

---

## 3. Behaviour

### 3.1 Record-button state machine

The record state is one enum. The red flag and all-complete are separate flags layered on top (3.2), so they never replace the record state.

| State | Entered by | Centre button: icon · label · `aria-label` | Button style | "จบการบันทึก" | Status (left) |
|---|---|---|---|---|---|
| `idle` | open screen | mic · เริ่มบันทึก · "เริ่มบันทึก" | filled `--primary` | disabled | mic · พร้อมบันทึก · 00:00 |
| `requesting_permission` | first tap in `idle` | mic · กำลังขอสิทธิ์ | disabled | disabled | กำลังขอใช้ไมโครโฟน |
| `connecting` | permission granted, or retry | loader · กำลังเชื่อมต่อ | disabled | enabled if ≥1 turn | กำลังเชื่อมต่อ |
| `listening` | realtime data channel `oai-events` open | pause · หยุดชั่วคราว · "หยุดบันทึกชั่วคราว" | `--primary-deep` with 2px `--primary` ring | outline | level meter · กำลังฟัง · clock runs |
| `paused` | tap in `listening`, or page hidden (system pause) | mic · บันทึกต่อ · "บันทึกต่อ" | filled `--primary` | outline | pause · หยุดชั่วคราว · clock frozen |
| `reconnecting` | unexpected disconnect; up to 3 automatic attempts | spinning loader · กำลังเชื่อมต่อ | disabled | outline | wifi-off · ขาดสัญญาณ |
| `error` | 3 attempts failed, or a non-retryable mint/connection error (section 11, T7) | rotate-ccw · ลองอีกครั้ง · "ลองเชื่อมต่ออีกครั้ง" | filled `--primary` | outline | mic-off · หยุดบันทึก |
| `permission_denied` | mic permission denied | mic-off · ขอสิทธิ์อีกครั้ง | filled `--primary` | enabled if ≥1 turn | mic-off · ไม่มีสิทธิ์ไมโครโฟน |
| `finishing` | tap "จบการบันทึก" | disabled | disabled | loader · กำลังจบการบันทึก | clock frozen |

Transitions:
- `idle → requesting_permission → connecting → listening`
- `listening ⇄ paused`
- `listening → reconnecting → listening | error`
- `error → connecting`
- `requesting_permission → permission_denied → requesting_permission`
- `{listening, paused, error, permission_denied} → finishing → review`

Rules:
- A screen wake lock is held only in `listening`.
- `visibilitychange: hidden` forces `paused` and shows the system-pause copy.
- Data already captured is never discarded by any transition.

### 3.2 Prompt-slot priority and flags

1. **`redFlag && !acknowledged`** → the red-flag alert (3.3). Question suggestions are suppressed. Recording continues unchanged.
2. **`allComplete`** → the complete slot: success outline, `circle-check`, "ได้ข้อมูลครบ 6 หัวข้อแล้ว".
   - "จบการบันทึก" becomes the one filled primary.
   - The record button drops to the quiet outline style, so there is still exactly one filled blue control.
3. **Record state `listening`** → the navy slot with `suggested_question_th` from `next_action` (`kind: "prompt_nurse"`). The allowlist is `backend/app/voice/utterances_th.py`. Then the note "เพื่อเก็บ “<field label>” · ใช้คำพูดของคุณเองได้".
4. **Any other record state** → the same question on the neutral slot, with a state note from section 5.

When the question changes, the slot text cross-fades (3.4) and is announced through `aria-live="polite"`. The question text comes only from the allowlist; model output is never rendered as a question.

### 3.3 Red flag / nurse-attention alert

**Trigger:** the backend `nurse_attention` hit (`policy.py`: single phrases plus the chest-pain + dyspnoea combination). This list is a simulation placeholder pending D4 clinical sign-off. It assigns no urgency level and no department.

**Presentation** (`03e-redflag.html`):
- A full-bleed `--critical` block from the top edge of the screen. It absorbs the patient line and replaces the slot.
- Inside the block:
  - `triangle-alert` icon + heading;
  - the patient's words quoted with their time, on `--critical-fg`;
  - one line saying that prompts are paused and the system did not grade urgency;
  - a 56px white button, "รับทราบ".
- The transcript is hidden in the dock while the alert is unacknowledged, so the facts stay readable on an 844pt screen.
- Recording keeps running, and the status says "ยังบันทึกอยู่".

**Not colour-only:**
- the icon, the heading text, and the full-bleed change of layout;
- `role="alert"`;
- focus moves to the heading;
- `navigator.vibrate([200,100,200])` where supported (not on iOS);
- the flagged transcript line is bold on `--critical-bg`.

**No motion:** the alert appears instantly (UI-SPEC: no motion for safety alerts).

"รับทราบ" sits mid-screen, not in the thumb zone. This is deliberate: it is a deliberate acknowledgement, not a reflex tap.

**After "รับทราบ":**
- The block becomes a one-line acknowledged strip above the slot: `--critical-bg`, `--critical-border`, icon, "มีสัญญาณที่ต้องประเมินเร่งด่วน · รับทราบเมื่อ HH:MM น.".
- The strip stays for the rest of the session and on review.
- The acknowledgement is audited with actor and time.

Tapping "จบการบันทึก" while the alert is unacknowledged does not finish. It moves focus to the alert and shows "รับทราบสัญญาณเร่งด่วนก่อนจบการบันทึก". Pause always works.

### 3.4 Motion

Motion is state feedback only. There is no page-load choreography and no decorative loops.

| What | Motion | Reduced motion |
|---|---|---|
| Level meter while `listening` | bar `scaleY` from real input RMS, about 12 fps, transform only | static bars; the text "กำลังฟัง" carries the state |
| New transcript line | opacity 0→1, 150ms ease-out, no slide | instant |
| Fact captured | value cross-fade 200ms, glyph swap | instant |
| Prompt question changes | cross-fade 200ms | instant |
| Button press | `scale(0.98)` (record button 0.96), 150ms | none |
| Reconnecting / connecting loader | rotate, 1s linear | static loader glyph plus attempt count in text |
| Red-flag alert, error, all-complete | **none**: appear instantly | none |

### 3.5 Loading, empty and error states

Every state has exact copy in section 5.

- Patient list: skeleton rows in the list's final shape, then an empty state, then an error state.
- Transcript: an empty state before recording.
- Facts: "ยังไม่มี" per row.
- Extraction unavailable: a warning notice; the slot falls back to the neutral question.
- Submit: loading, success and error states.
- Stale or conflict: UI-SPEC copy.

---

## 4. Accessibility

**Contrast**, WCAG 2.2, computed from the token hex values:

| Pair | Ratio |
|---|---:|
| `--card` on `--primary-deep` (prompt question) | 10.9:1 |
| `--primary-soft` on `--primary-deep` (prompt note) | 7.8:1 |
| `--card` on `--critical` (alert text) | 6.6:1 |
| `--card` on `--critical-fg` (quoted words) / `--critical-fg` on `--card` ("รับทราบ") | 9.8:1 |
| `--card` on `--primary` (primary CTA) | 6.7:1 |
| `--muted-foreground` on `--card` / `--background` / `--nav` / `--muted` | 6.0 / 5.6 / 5.2 / 5.4:1 |
| `--success` on `--success-bg`; `--warning-fg` on `--warning-bg`; `--critical-fg` on `--critical-bg` | 5.5 / 9.2 / 9.1:1 |
| Form-control border `--muted-foreground` on `--card` (non-text, needs 3:1) | 6.0:1 |

`--border` (1.5:1) is used only for dividers, never as the only boundary of a control.

**Not colour-only:** every status has a glyph and Thai text.
- captured / asking / missing;
- confirmed / waiting / editing / edited / rejected;
- live / paused / reconnecting / error;
- red flag (see 3.3).

**Screen reader:**
- the record button's `aria-label` follows the state machine table;
- the status column is `role="status"`;
- the prompt slot is `aria-live="polite"`;
- the red flag is `role="alert"` and takes focus;
- fact glyphs carry `aria-label` (ได้ข้อมูลแล้ว / กำลังถาม / ยังไม่มีข้อมูล);
- the transcript opener is "เปิดบทสนทนาทั้งหมด";
- decided-row links read "เปลี่ยน<field>";
- the patient list is a `radiogroup`;
- the consent control is a real checkbox.

**Focus:** a visible 2px `--primary` ring with 2px offset on every control.

**Order:**
- recording: patient → slot → facts → transcript → record → finish;
- review: flag strip → title → items → submit.

**Text size:** the layout survives 200% zoom. The facts list scrolls. The slot text wraps and is never truncated. Safety text never uses an ellipsis.

**Language:** `lang="th"` on the page. IDs and model metadata are left untranslated.

---

## 5. Thai copy (exact)

Global rules:
- No "Submit / OK / Cancel / Retry" style labels.
- Never "AI-powered", "อัจฉริยะ", "วินิจฉัย" or any claim of diagnosis.
- Dismissals use "กลับไปตรวจสอบ".
- `↵` in these tables marks a line break between a notice heading and its body; it is never rendered.

**Global**

| Key | Copy |
|---|---|
| Limitation label (every screen, last line) | ข้อมูลสังเคราะห์ · ต้นแบบเพื่อการวิจัย |
| Wordmark | MedX (text) |

**Login**

| Key | Copy |
|---|---|
| Heading | บันทึกซักประวัติข้างเตียง |
| Purpose | สำหรับพยาบาล อัดเสียงบทสนทนากับผู้ป่วย แล้วตรวจทานข้อมูลก่อนส่งเข้าเคส |
| Fields | ชื่อผู้ใช้สังเคราะห์ · รหัสผ่าน · (icon button) แสดงรหัสผ่าน / ซ่อนรหัสผ่าน |
| CTA / loading | เข้าสู่ระบบเดโม / กำลังเข้าสู่ระบบ… |
| 401 | ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง |
| Other failure | เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้ง |
| Network | บริการเข้าสู่ระบบไม่พร้อมใช้งาน โปรดลองอีกครั้ง |
| Wrong role | บัญชีนี้ไม่ใช่บัญชีพยาบาล แอปนี้ใช้ได้เฉพาะพยาบาล |

**Start session**

| Key | Copy |
|---|---|
| Account button label | ออกจากระบบ (nurse1) |
| Title / subtitle | เลือกผู้ป่วย / ผู้ป่วยสังเคราะห์ที่รอซักประวัติ |
| Search | (label) ค้นหาหรือพิมพ์รหัสผู้ป่วยสังเคราะห์ · (placeholder) ค้นหาหรือพิมพ์รหัส SYN- |
| Row | `SYN-2026-0023` · หญิง 46 ปี / เตียง 7 · มาถึง 10:24 น. |
| Loading | กำลังโหลดรายชื่อผู้ป่วย… (skeleton rows) |
| Empty | ยังไม่มีผู้ป่วยที่รอซักประวัติ ↵ พิมพ์รหัส SYN- เพื่อเปิดผู้ป่วยสังเคราะห์รายอื่น |
| No match | ไม่พบรหัส “<input>” ↵ ตรวจรหัสอีกครั้ง |
| Non-synthetic id | ใช้ได้เฉพาะผู้ป่วยสังเคราะห์ (รหัสขึ้นต้นด้วย SYN-) |
| Load error | โหลดรายชื่อผู้ป่วยไม่สำเร็จ · button: ลองโหลดอีกครั้ง |
| Explainer heading | ก่อนเริ่มบันทึก |
| Explainer lines | ครั้งแรกที่กดเริ่มบันทึก เบราว์เซอร์จะขอใช้ไมโครโฟน ให้เลือก “อนุญาต” / แอปฟังเฉพาะตอนกำลังบันทึก และไม่พูดกับผู้ป่วย คุณเป็นคนถามเอง |
| Consent | แจ้งผู้ป่วยแล้วว่าจะบันทึกเสียงบทสนทนา |
| CTA / disabled hint | เปิดหน้าบันทึก / เลือกผู้ป่วยและยืนยันว่าแจ้งผู้ป่วยแล้ว |

In the Empty and No match rows, `↵` separates the heading from the helper line; each is rendered on its own line.

**Recording**

| Key | Copy |
|---|---|
| Facts heading / count | ข้อมูลที่ได้ / n จาก 6 หัวข้อ |
| Field labels | อาการสำคัญ · ระยะเวลาที่เป็น · ความรุนแรง · ประวัติแพ้ยา · ยาที่ใช้อยู่ · โรคประจำตัว |
| Fact values | ยังไม่มี · กำลังถาม · ผู้ป่วยไม่ทราบ (UNKNOWN) · ผู้ป่วยไม่ตอบ (REFUSED) · ยังไม่มี (ถามครบ 2 ครั้งแล้ว) (not elicited) |
| Slot note: listening | เพื่อเก็บ “<field label>” · ใช้คำพูดของคุณเองได้ |
| Slot note: idle | คำถามแรกที่แนะนำ · ใช้คำพูดของคุณเองได้ |
| Slot note: paused | หยุดชั่วคราวอยู่ · กดบันทึกต่อเมื่อพร้อม |
| Slot note: reconnecting | รอให้เชื่อมต่อได้ก่อนถามต่อ |
| Slot note: error | บันทึกหยุดอยู่ · ลองอีกครั้งหรือจบเพื่อตรวจทาน |
| Complete slot | ได้ข้อมูลครบ 6 หัวข้อแล้ว ↵ จบการบันทึกเพื่อตรวจทานได้เลย หรือคุยต่อถ้ามีข้อมูลเพิ่ม |
| Transcript empty | กดเริ่มบันทึก แล้วคุยกับผู้ป่วยตามปกติ ข้อความที่ได้ยินจะขึ้นที่นี่ |
| Transcript opener / sheet title | เปิดบทสนทนาทั้งหมด / บทสนทนาทั้งหมด |
| Paused notice | หยุดบันทึกชั่วคราว ↵ เสียงช่วงนี้ไม่ถูกบันทึก ข้อมูลเดิมยังอยู่ครบ |
| System pause (app hidden) | บันทึกหยุดเพราะออกจากแอป ↵ กดบันทึกต่อเมื่อกลับมาคุยกับผู้ป่วย |
| Reconnecting | กำลังเชื่อมต่อใหม่ (ครั้งที่ n จาก 3) ↵ ข้อความก่อนหน้ายังอยู่ครบ เสียงช่วงนี้อาจไม่ถูกถอดข้อความ |
| Error | บันทึกเสียงต่อไม่ได้ ↵ ลองเชื่อมต่อ 3 ครั้งไม่สำเร็จ ข้อมูล n หัวข้อที่ได้ยังอยู่ครบ |
| Permission denied | ไม่ได้รับสิทธิ์ใช้ไมโครโฟน ↵ เปิดสิทธิ์ไมโครโฟนให้เว็บนี้ในการตั้งค่าเบราว์เซอร์ แล้วกดขอสิทธิ์อีกครั้ง |
| No microphone | ไม่พบไมโครโฟน ↵ ตรวจว่าไม่มีแอปอื่นใช้ไมโครโฟนอยู่ แล้วลองอีกครั้ง |
| Extraction unavailable (warning, slot goes neutral) | ระบบสกัดข้อมูลไม่ได้ชั่วคราว ↵ บทสนทนายังถูกบันทึก ตรวจและกรอกข้อมูลเองในหน้าตรวจทาน |
| Status labels | พร้อมบันทึก · กำลังขอใช้ไมโครโฟน · กำลังเชื่อมต่อ · กำลังฟัง · หยุดชั่วคราว · ขาดสัญญาณ · หยุดบันทึก · ไม่มีสิทธิ์ไมโครโฟน · กำลังจบการบันทึก |
| Record button labels | เริ่มบันทึก · หยุดชั่วคราว · บันทึกต่อ · กำลังเชื่อมต่อ · ลองอีกครั้ง · ขอสิทธิ์อีกครั้ง |
| Finish | จบการบันทึก |
| Leave guard (sheet) | ออกจากหน้าบันทึกหรือไม่ ↵ การบันทึกจะหยุด ข้อมูลที่ได้ยังอยู่และตรวจทานต่อได้ · หยุดและออก · กลับไปบันทึก |
| Red flag | heading พบสัญญาณที่ต้องประเมินเร่งด่วน · top right ยังบันทึกอยู่ · quote label ผู้ป่วยพูดว่า · HH:MM · body คำถามแนะนำหยุดไว้จนกว่าจะรับทราบ ระบบไม่ได้จัดระดับความเร่งด่วน ให้ประเมินผู้ป่วยตามแนวปฏิบัติของหน่วยงาน · button รับทราบ |
| Red flag acknowledged strip | มีสัญญาณที่ต้องประเมินเร่งด่วน · รับทราบเมื่อ HH:MM น. |
| Finish while unacknowledged | รับทราบสัญญาณเร่งด่วนก่อนจบการบันทึก |

In the Recording table, `↵` separates a notice heading from its body line; they are rendered as two lines.

**Review**

| Key | Copy |
|---|---|
| Back | บันทึกต่อ |
| Title / meta | ตรวจทานข้อมูล / `SYN-…` · บันทึก m นาที s วินาที |
| Instruction | ยืนยัน แก้ไข หรือปฏิเสธทีละหัวข้อ ข้อมูลจะเข้าเคสเมื่อกดส่งเท่านั้น |
| Source | จากบทสนทนา HH:MM + “quoted words” |
| Actions | ยืนยัน · แก้ไข · ปฏิเสธ · เปลี่ยน |
| Allergy "none" confirm button | ยืนยันว่าไม่มีประวัติแพ้ยา |
| Tags | รอตรวจ · ยืนยันแล้ว · กำลังแก้ไข · แก้ไขแล้ว · ปฏิเสธแล้ว · ไม่มีข้อมูล |
| Edit | label ค่าที่ถูกต้อง · buttons บันทึกการแก้ไข / กลับไปตรวจสอบ · after edit: ระบบได้ยินว่า: <original> |
| Reject (inline, not a modal) | reason chips ได้ยินผิด / ไม่ใช่ข้อมูลของผู้ป่วย / อื่น ๆ · buttons ปฏิเสธและบันทึกเหตุผล / กลับไปตรวจสอบ · decided tag ปฏิเสธแล้ว · ไม่ส่งเข้าเคส |
| Missing field | tag ไม่มีข้อมูล · body ไม่ได้ยินข้อมูลนี้ระหว่างบันทึก · buttons เพิ่มข้อมูล / ระบุว่าไม่ทราบ |
| Bar | ตรวจแล้ว n จาก 6 หัวข้อ · ตรวจครบแล้วจึงส่งได้ / ตรวจครบ 6 หัวข้อ · แก้ไข n หัวข้อ |
| Submit / loading | ยืนยันและส่งเข้าเคส / กำลังส่ง… |
| Submit helper | ระบบจะเสนอแผนกจากข้อมูลที่ยืนยันแล้ว และรอพยาบาลยืนยันอีกครั้งในเคส |
| Submitted screen | ส่งเข้าเคสแล้ว ↵ ข้อมูลของ `SYN-…` อยู่ในเคสแล้ว ระบบกำลังเสนอแผนกให้พยาบาลยืนยันในแอปหลัก · primary เริ่มผู้ป่วยรายถัดไป |
| Submit error | ส่งเข้าเคสไม่สำเร็จ ↵ ข้อมูลที่ตรวจแล้วยังอยู่ในเครื่องนี้ · button ลองส่งอีกครั้ง |
| Stale / conflict | UI-SPEC: ข้อมูลนี้มีเวอร์ชันใหม่กว่า / มีผู้ใช้อื่นกำลังดำเนินการกับเคสนี้ |

---

## 6. Anti-AI-look checklist

The reviewer and the checker both apply this list. The comps were self-checked on 2026-09-30.

| Check | Comp status |
|---|---|
| No decorative gradients or glows. The only gradient is the transcript fade mask, which is functional and has no colour. | pass |
| No emoji as icons. Icons are Lucide paths inlined as SVG at one stroke width (2). | pass |
| No generic card grid. The layout uses one grouped list per screen, a single prompt slot and one dock. | pass |
| No heavy shadows. Comp surfaces have no shadow; borders do the separation. | pass |
| No literal-translation or "AI-powered" copy. Copy is nurse-to-nurse Thai, and no screen names the AI. | pass |
| Clear hierarchy. The prompt slot and the recorder dock dominate; facts are secondary; the limitation label is quietest. | pass |
| Thai line-height is 1.5 for body and 1.4 for 20/28, with no clipped tone marks or orphans (`text-wrap` balance/pretty). | pass |
| Empty, loading and error states are defined (section 5). Comps show idle, paused, reconnecting, error, red-flag and complete. | pass |
| One-handed use: primary actions sit in the bottom third. | pass (red-flag "รับทราบ" is a deliberate exception, see 3.3) |
| One filled primary per surface. | pass (all-complete swaps the emphasis between record and finish) |
| No eyebrow or kicker labels, no section numbers, no em-dash in UI strings. | pass |
| Only theme tokens, and no hex/rgb in comps (`grep` returns nothing). The impeccable detector returned `[]`. | pass |

---

## 7. Decisions for the owner (design only)

1. **Line-height.** Thai 20/28 text uses line-height 1.4 instead of UI-SPEC's 1.3, to avoid stacked tone marks colliding in two-line prompts. This applies to the mobile app only.
2. **Record button shape.** The record button is round, an exception to the 8px control radius.
3. **Consent checkbox.** A patient-informed checkbox gates recording. It is not in the owner brief, but it is recommended for privacy even with role-play.
4. **Navy prompt slot.** The slot uses `--primary-deep` as a fill. This goes beyond UI-SPEC's "accent = CTA, nav, links, focus", but it is the separate deep token and is used for one live element only.
5. **Transcript hidden during the alert.** The red-flag state hides the transcript in the dock until it is acknowledged.
6. **Nurse-attention placeholder.** The nurse-attention phrase list and the question allowlist remain simulation placeholders until D4 clinical sign-off.

## 8. Comp index

The pages share `comp/theme.css` (a copy of `web/app/theme.css`) and `comp/comp.css`, which uses tokens only. To re-render:

```
cd web && node ../slices/v2c/comp/shoot.mjs
```

The render uses Playwright at 390×844 and DPR 2; the output goes to `comp/png/`.

| File | State |
|---|---|
| `01-login.html` | Login |
| `02-start.html` | Choose patient, mic explainer, consent |
| `03a-idle.html` | Recording: idle |
| `03-recording.html` | Recording: listening (main) |
| `03b-paused.html` | Recording: paused |
| `03c-reconnecting.html` | Recording: reconnecting |
| `03d-error.html` | Recording: error |
| `03e-redflag.html` | Recording: red flag, unacknowledged |
| `03f-complete.html` | Recording: all fields complete |
| `04-review.html` (+ `-full.png`) | Review in progress |
| `04b-review-ready.html` (+ `-full.png`) | Review complete, submit enabled |

---

# Part B: build

## 9. Scope

**User and job.** A nurse at the bedside, holding one phone, records an ordinary Thai nurse–patient conversation. The phone shows what is still missing, suggests the next question (the nurse asks it; the app never speaks), raises nurse-attention cues above everything else, and lets the nurse review every captured fact before anything reaches the case.

In scope, all under a **new** `mobile/` project plus the three repo files named below:
1. `mobile/`: Next.js 15 + React 19 + TypeScript PWA with its own `package.json`, `package-lock.json`, `tsconfig.json`, vitest config and Playwright config. It has no imports from `web/` and no shared package. Logic from `web/lib/realtime.ts` and `web/components/live/useLiveCall.ts` is **copied/ported**, not imported.
2. The screens and states of sections 2–5 and every comp in section 8: login, start, recording (idle, listening, paused, reconnecting, error, permission_denied, red flag, complete, finishing), transcript sheet, leave guard, review (waiting, deciding, editing, rejecting, ready, submitting, submitted, submit error, not-yet-connected).
3. The transport client (section 11): a direct phone → realtime-vendor WebRTC **transcription-only** session, minted by the backend.
4. Thin API clients for the backend contracts in section 10, mocked in tests.
5. PWA: manifest, icons, a minimal service worker, Screen Wake Lock, reconnect on visibility/network changes, mic-permission error state.
6. `scripts/sync_theme.sh` (copies `web/app/theme.css` → `mobile/app/theme.css`).
7. `Makefile`: `mobile/node_modules/.installed` install rule; `make test` also runs `cd mobile && npm test && npm run typecheck`; a new `make mobile-dev` target.

Out of scope:
- **Any backend change** (`backend/`, `casegraph/`, `schemas/`), and any `web/` change. v2a, v2t and v2d build the server side in parallel on other branches.
- LiveKit (the `livekit` package stays forbidden), any cascade or TTS, any audio the model speaks.
- Deployment, the `medx-mobile` Vercel project (D5), HTTPS tunnels, native wrappers.
- Audio storage or upload of any kind (no `MediaRecorder`, no audio blobs).
- The review submit endpoint, consent audit and red-flag-acknowledgement audit (v2d). v2c builds the UI and a thin client marked `TODO(v2d)`.
- Diarization, speaker labels, triage/department display, offline mode, and changing the Thai allowlist or red-flag list (D4).

## 10. Contracts consumed (mocked in tests; never implemented here)

All calls are same-origin `/api/*`. `mobile/next.config.mjs` rewrites `/api/:path*` → `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*` (the `web/next.config.mjs` pattern), so the session cookie stays first-party. Every contract below has a JSON fixture in `mobile/tests/fixtures/` whose shape copies the locked contract; the integration auditor diffs these fixtures against the real v2a/v2t responses once those branches merge.

| Call | Contract | Owner |
|---|---|---|
| `POST /api/auth/login {username,password}`; `GET /api/me`; `POST /api/auth/logout` | existing `backend/app/auth.py`; user `{id, username, role, home}` | existing |
| `POST /api/auth/demo-login {role:"nurse"}` | existing `backend/app/public_demo.py`; used only when `NEXT_PUBLIC_PUBLIC_DEMO=1`, where the login screen shows the one-click CTA "เข้าสู่ระบบเดโม" and hides the username/password fields | existing |
| `POST /api/voice/sessions {patient_ref, data_class:"synthetic", mode:"ambient"}` | `{session:{session_id, patient_ref, mode, status, nurse_attention, extraction_error, …}, next_action, field_statuses}` | v2a §3.1 |
| `POST /api/voice/sessions/{id}/turns {speaker:"unknown", text, started_at, ended_at, source:"asr", asr_model}` | `{turn:{turn_id,…}, new_facts[], field_statuses[], next_action, nurse_attention, extraction_error, session}` | v2a §3.2 |
| ambient `next_action` | exactly `{kind: prompt_nurse\|complete\|handoff, field, suggested_question_id, suggested_question_th, reason, missing_fields}` | v2a §3.3 |
| `GET /api/voice/sessions/{id}` | `{session, turns, facts, field_statuses, next_action}`; used for review data and for reconcile-before-retry (T5) | existing + v2a |
| `POST /api/voice/sessions/{id}/finish` | 200 `{session, facts, field_statuses, …}`; 409 = already finished (treated as done) | existing |
| `GET /api/voice/realtime/config` | `{enabled, reason, access_code_required, ambient_supported, ambient_model, max_session_seconds, vendor_label, …}` | v2t |
| `POST /api/voice/realtime/session {voice_session_id, access_code?, purpose:"ambient"}` | 200 `{client_secret, expires_at, connect_url, data_channel, model, transcribe_model, vendor_label, max_session_seconds, instructions_version}`; errors 403 `access_code_invalid`, 404, 409 not active, 429 + `Retry-After`, 502, 503 `{reason}`, 504 | v2t (error set as in current `voice_realtime.py`) |
| review submit | `mobile/lib/review.ts` `submitReview(sessionId, decisions)`, one `fetch` marked `// TODO(v2d): endpoint and body owned by slice v2d` | v2d |

**Display rules derived from the contracts:**
- Six rows in `ASK_ORDER`. "ประวัติแพ้ยา" combines `allergy_status` + `allergens`.
- Row value: `MISSING` → "ยังไม่มี" (or "กำลังถาม" for `next_action.field`); `UNKNOWN` → "ผู้ป่วยไม่ทราบ"; `REFUSED` → "ผู้ป่วยไม่ตอบ"; `KNOWN` → the latest fact's `value_text` for that field.
- The allergy row may show a negative **only** when the latest `allergy_status` fact is `state:"KNOWN", value:"none"`. Every other case (no fact, MISSING, UNKNOWN, REFUSED, `allergy_conflict`, `extraction_error`, unknown value) never renders "ไม่แพ้" or "ไม่มีประวัติแพ้".
- Red flag = `nurse_attention === true` on any turn/session response, or `next_action.kind==="handoff" && reason==="nurse_attention_phrase"`. The quoted words are the text of the turn whose response first set it. Sticky for the session.
- `kind==="handoff" && reason==="extraction_unavailable"` → the "Extraction unavailable" warning notice; the slot goes neutral and keeps the last received `suggested_question_th` (or no question if none was ever received).
- Question text on screen comes **only** from `suggested_question_th`; the client has no question strings of its own.

## 11. Transport and lifecycle rules

**T1. Connect.** On the first record press: `getUserMedia({audio:{echoCancellation:true, noiseSuppression:true, autoGainControl:true}})` → mint (`purpose:"ambient"`, `access_code` from memory if required) → `RTCPeerConnection`, add the mic track, create data channel `oai-events` (the name from `data_channel`), POST the SDP offer to `connect_url` with `Authorization: Bearer <client_secret>` and `Content-Type: application/sdp`, apply the answer. `listening` is entered when the data channel opens.
- `connect_url` comes only from the mint response and must start with `https://`; anything else is a non-retryable error.
- The SDP POST carries only the SDP body and those two headers: no patient ref, no cookie, no transcript.
- `ontrack` attaches nothing. No `<audio>`/`<video>` element is ever created.

**T2. Client never makes the model speak.** The data-channel sender is a single function with a frozen allowlist `ALLOWED_CLIENT_EVENTS = ["input_audio_buffer.clear"]`. Anything else throws and is not sent, including `response.create`, `response.cancel`, `conversation.item.create`, `session.update` and `transcription_session.update`. The session configuration is server-owned (v2t).

**T3. Events consumed.**
- `input_audio_buffer.speech_started {item_id}` → `started_at` for that item (client wall clock, ISO-8601 with offset).
- `input_audio_buffer.speech_stopped {item_id}` → `ended_at`.
- `input_audio_buffer.committed {item_id, previous_item_id}` → the item's place in the post order.
- `conversation.item.input_audio_transcription.delta {item_id, delta}` → live partial line (muted, ends in "…"), never posted.
- `conversation.item.input_audio_transcription.completed {item_id, transcript}` → final line + one POST (T4).
- `conversation.item.input_audio_transcription.failed {item_id}` → the partial line is removed, nothing is posted, the item releases the queue, and the transcript sheet shows the failed-segment count (D-V2C-2).
- `error` and connection-state `failed`/`disconnected`/`closed` → T6.
- Every other event type, including any `response.*` or output-audio/text event, is ignored and never rendered.

**T4. Turn posting (exactly once, in order).**
- One FIFO queue per voice session, in commit order (items completed with no prior `committed` event are appended in completion order). One POST in flight at a time.
- A completed item waits until every earlier committed item is completed, failed or has waited **15 s**; a timed-out earlier item is skipped (no fabricated text).
- Dedupe key = `item_id` (plus `#n` when a transcript over 2,000 chars is split at whitespace into ordered parts). A key is posted at most once for the life of the voice session, across every reconnect; a duplicate `completed` event is ignored.
- Body: `{speaker:"unknown", text: normalise(transcript), started_at, ended_at, source:"asr", asr_model: <mint transcribe_model>}`. `normalise` = the ported `normaliseTranscript`. Empty text after normalising is not posted. `started_at ≤ ended_at ≤` the POST time; missing `speech_*` times fall back to the `committed` time.
- Each response replaces `field_statuses`, `next_action`, the facts shown, and the red-flag/extraction flags.

**T5. Turn POST failure.**
- 401 → stop recording, go to login.
- 409 (session not active) → stop, error state, no retry.
- 422 → the item is dropped, counted as failed, not retried.
- Network error, timeout or 5xx → `GET /api/voice/sessions/{id}`; if a turn with the same `text` and `started_at` already exists, mark the key posted; otherwise retry. At most 2 retries (1 s, 3 s). Then the item is counted as failed and the queue moves on.

**T6. Reconnect.** Unexpected data-channel close, peer connection `failed`/`disconnected` for > 2 s, the `offline` event, or the vendor session ending at `max_session_seconds` → `reconnecting`: close the old connection, re-mint, reconnect.
- Up to 3 attempts, backoff 1 s / 2 s / 4 s (a 429 waits `Retry-After` instead). The `online` event triggers the next attempt at once.
- At most **one** open `RTCPeerConnection` at any time (two live connections would transcribe the same audio twice).
- Planned rollover: when a connection has run `max_session_seconds − 30 s` and no speech is in progress (last `speech_started` has its `speech_stopped`), or at `max_session_seconds − 5 s` regardless, the client drains pending completions for up to 3 s, then closes and reconnects through the same path.
- Queued and already-posted turns are never lost or re-posted by a reconnect.

**T7. Error mapping** (non-retryable → `error` state with its notice; recovery is always "ลองอีกครั้ง" and "จบการบันทึก" when ≥ 1 turn exists):

| Cause | State | Auto-retry |
|---|---|---|
| mic `NotAllowedError`/`SecurityError` | `permission_denied` + Permission denied notice | no |
| mic `NotFoundError`/`NotReadableError` | `error` + No microphone notice | no |
| config `enabled:false` or `ambient_supported:false`, mint 503 | `error` + voice-unavailable notice (D-V2C-2) | no |
| mint 403 `access_code_invalid` | `error` + access-code notice; "ลองอีกครั้ง" returns to start with the field focused | no |
| mint 409 / 404 | `error` + session-ended notice; recovery is "จบการบันทึก" to review, or start a new session | no |
| mint 429 / 502 / 504 / network; SDP POST non-2xx; disconnect | `reconnecting` (T6), then `error` + the "3 attempts" notice | yes, ≤ 3 |

**T8. Pause, visibility, wake lock.**
- Pause disables the mic track (`track.enabled=false`); the connection stays open if it can. Resume re-enables it; if the connection died or expired while paused, resume goes through `connecting` with a fresh mint. A connection that dies while paused never shows `reconnecting` or `error` by itself.
- `visibilitychange → hidden` while `listening` forces `paused` with the System pause copy; returning to visible does **not** auto-resume.
- `navigator.wakeLock.request("screen")` is held only in `listening`; released on every exit from `listening` and on unmount. Unsupported → no error.

**T9. Finish and review data.** "จบการบันทึก" (`finishing`): stop the mic, drain the turn queue (≤ 5 s), close the connection, then `GET /api/voice/sessions/{id}` for the review. The backend `finish` is called at submit (D-V2C-3), so "บันทึกต่อ" can reopen recording (paused) on the same active session. No turn is ever posted after `finish`.

**T10. Review submit.** Enabled only when all 6 rows have a decision (ยืนยัน / แก้ไข / ปฏิเสธ with reason / เพิ่มข้อมูล / ระบุว่าไม่ทราบ). Submit = `POST …/finish` (409 counts as done) → `submitReview` (`TODO(v2d)`), whose payload carries the decisions, the original value per row, the red-flag acknowledgement time if any, and the consent acknowledgement.
- Only a 2xx from `submitReview` shows "ส่งเข้าเคสแล้ว".
- 404/405/501 → the **not-yet-connected** notice (D-V2C-2); the decisions stay on screen; the success screen is never shown.
- Other failures → the Submit error notice.
- Once `finish` has succeeded, "บันทึกต่อ" is hidden.

**T11. Storage and privacy.** Transcript, facts, decisions and the access code live in React memory only. Nothing is written to `localStorage`, `sessionStorage`, IndexedDB, Cache Storage or cookies by the client. The service worker has no Cache Storage use at all and no fetch caching. No `console.*` call logs transcript text. Sign-out clears in-memory state.

**T12. Patient list.** No backend endpoint lists waiting patients, and backend changes are out of scope. The list is a bundled synthetic roster `mobile/lib/roster.ts` (the comp rows: `SYN-` ids with synthetic sex/age/bed/arrival) plus typed `SYN-` ids, validated `^SYN-[A-Za-z0-9-]{1,60}$` with the "Non-synthetic id" copy on mismatch. Only `patient_ref` is sent to the backend (D-V2C-1).

## 12. Acceptance

Base = `git merge-base HEAD main` at build start. The checker records it.

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| V2C-C1 | `make test` is green including mobile | Exit 0. pytest count ≥ the base count with 0 new failures; web vitest unchanged; mobile `vitest run` 100% pass with ≥ 1 test per row of section 13; `tsc --noEmit` 0 errors in `mobile/`. `make mobile-dev` starts API + mobile and `GET /` returns 200 | `make test` tail; `cd mobile && npm test && npm run typecheck`; checker runs `make mobile-dev` and curls `/` and `/api/health` through the rewrite |
| V2C-C2 | Every comp screen/state is implemented and matches the comp | 11 states × 2 viewports = **22 PNGs** at 390×844 and 360×800 (DPR 2) in `artifacts/factory/v2c/screens/<state>-<w>x<h>.png`, for `login, start, idle, recording, paused, reconnecting, error, redflag, complete, review, review-ready`, rendered from the production build with mocked `/api` using the comp's synthetic data. The checker builds 11 side-by-side sheets (comp PNG left, 390×844 build right) and lists every deviation in layout order, copy, token role, icon, component presence or size > 4 px. Threshold: **0 unlisted deviations**, and every listed deviation is either fixed or owner-accepted. The 360×800 set has no horizontal scroll, no clipped or ellipsised safety text, and the dock/slot stay fixed | `cd mobile && npm run screens` (Playwright); checker side-by-side sheets in `artifacts/factory/v2c/compare/`; deviation list in the checker report |
| V2C-C3 | Only synced theme tokens | 0 matches of `#[0-9a-fA-F]{3,8}\b`, `rgba?\(`, `hsla?\(` and CSS named colours in `mobile/**/*.{ts,tsx,css,mjs}` outside `mobile/app/theme.css` (node_modules/.next excluded). `mobile/app/theme.css` is byte-identical to `web/app/theme.css`. `scripts/sync_theme.sh` recreates it. Manifest `theme_color`/`background_color` equal token values (test-read from theme.css) | `mobile/tests/theme.test.ts` (grep + sha256 equality + manifest check); checker runs `scripts/sync_theme.sh && git diff --exit-code mobile/app/theme.css` |
| V2C-C4 | Consent gates recording | "เปิดหน้าบันทึก" is disabled for all 4 combinations except (patient selected AND consent ticked). The consent control is a native `<input type=checkbox>` with the exact §5 label. Unticking re-disables. No `POST /api/voice/sessions` and no `getUserMedia` before both hold | `start.test.tsx` (parametrised), fetch/getUserMedia spies |
| V2C-C5 | Red flag cannot be missed | On a turn response with `nurse_attention:true`: an element with `role="alert"` containing the `triangle-alert` icon **and** the heading text "พบสัญญาณที่ต้องประเมินเร่งด่วน"; `document.activeElement` is the heading; **no transcript text** (final or partial) in the DOM outside the quoted words; the prompt slot and any `suggested_question_th` are absent; recording state unchanged and "ยังบันทึกอยู่" shown; "จบการบันทึก" does not finish, focuses the alert and shows "รับทราบสัญญาณเร่งด่วนก่อนจบการบันทึก"; pause still works. After "รับทราบ": the strip with "รับทราบเมื่อ HH:MM น." stays on recording and review, and transcript lines received during the alert reappear. No animation on the alert (computed `animation-name: none`, `transition-duration: 0s`). The red flag is never downgraded by a later response without `nurse_attention` | `redflag.test.tsx`; Playwright `redflag` state for focus and computed style |
| V2C-C6 | Missing is never negative | For each state in {no fact, MISSING, UNKNOWN, REFUSED, KNOWN present, `allergy_conflict:true`, `extraction_error:true`, unknown value}: the allergy row (recording and review) matches neither `/ไม่แพ้/` nor `/ไม่มีประวัติแพ้/`; only `KNOWN`+`none` shows the negative and the "ยืนยันว่าไม่มีประวัติแพ้ยา" button. Every MISSING row shows "ยังไม่มี" (recording) / tag "ไม่มีข้อมูล" (review), never blank, "-", "ไม่มี" alone or a negative | `facts-display.test.tsx` (table-driven over all 6 fields × all states) |
| V2C-C7 | Completed items only, exactly once, in order, across reconnect | With a mocked `RTCPeerConnection`/data channel: deltas cause 0 POSTs; each `completed` causes exactly 1 POST; duplicate `completed` → 0 extra; out-of-order completion is posted in commit order; a failed item is skipped without blocking; a 15 s stuck item is skipped. Script: 3 items → forced disconnect with 1 item committed-not-completed → reconnect → 2 more items + a late duplicate from the old connection. Expect the POST sequence to equal the expected item order, with no repeats and no lost completed items. The ambiguous-failure case (network error, turn already stored) posts 0 extra | `transport.test.ts`, `turn-queue.test.ts` (fake timers) |
| V2C-C8 | The client never makes the model speak | Over every transport test, the set of frames sent on the data channel ⊆ `{"input_audio_buffer.clear"}`. Calling the sender with `response.create`, `response.cancel`, `conversation.item.create`, `session.update`, `transcription_session.update` throws and sends nothing. 0 `<audio>`/`<video>` elements after `ontrack`. `response.*` events received from the vendor render nothing. Static: `grep -rE "response\.create\|conversation\.item\.create\|session\.update" mobile/{app,components,lib}` matches only the deny-list/test code | `realtime.test.ts`; grep in `static.test.ts` |
| V2C-C9 | Every failure has a visible state and a recovery | Mic denied → `permission_denied` notice + "ขอสิทธิ์อีกครั้ง"; mint 503 and config disabled → `error` + voice-unavailable notice, no auto-retry; mint 409 → `error` + session-ended notice, "จบการบันทึก" reaches review; mint 403 → access-code notice, returns to start with the field focused; disconnect → `reconnecting` "(ครั้งที่ n จาก 3)" → success returns to `listening`, or 3 failures → `error` with the 3-attempts copy and "ลองอีกครั้ง" reconnects. In every case, captured facts and posted turns are still shown | `errors.test.tsx` (one test per row of T7); Playwright `reconnecting` and `error` states |
| V2C-C10 | No secrets or vendor SDK in the client | Build with `OPENAI_API_KEY=sk-SENTINELv2c0000` and `VOICE_ACCESS_CODE=CODESENTINELv2c` in the env: `mobile/.next/static/**` has 0 matches of `\bsk-[A-Za-z0-9_-]{10,}`, `SENTINEL`, `ek_[A-Za-z0-9]{8,}`, `OPENAI_API_KEY`. `mobile/package.json` + lockfile contain no `livekit`, `openai` or other speech/LLM SDK. No `api.openai.com` or `openai` string in `mobile/{app,components,lib,public}` (the vendor comes only from `connect_url`/`vendor_label`) | `npm run build && npm run scan-bundle`; `static.test.ts` |
| V2C-C11 | Installable, touch-safe, motion-safe PWA | `manifest.webmanifest`: `name`, `short_name`, `lang:"th"`, `start_url:"/"`, `scope:"/"`, `display:"standalone"`, `orientation:"portrait"`, icons 192, 512 and 512 maskable (files exist, sizes match). `navigator.serviceWorker.getRegistration()` is truthy on the production build; `sw.js` contains no `caches`, no `cache.put` and no `/api` handling. Every visible interactive element (button, link, input, `[role=radio]`, checkbox label row) is ≥ 44×44 CSS px in every C2 state at both viewports, and primary/record/secondary/review/patient-row sizes equal §1.5 (56/72/48/44/64). With `reducedMotion:"reduce"`: level-meter bars are static and loaders do not rotate (computed `animation-name: none` or duration 0) | `pwa.test.ts`; Playwright `pwa.spec.ts`, `touch.spec.ts`, `motion.spec.ts` |
| V2C-C12 | Standalone, brand-true project | 0 imports or path aliases resolving into `../web` (grep `from ["'].*\.\./web` and tsconfig `paths`). Fonts: only SCBXBeta2 via the synced `theme.css` `@font-face` (files in `mobile/public/fonts/`); no `next/font`, no Google Fonts, no other `font-family` literal. Wordmark is text "Med"+"X" with `aria-label="MedX"`; 0 occurrences of the SCBX logo or name in UI files | `static.test.ts`; `wordmark.test.tsx` |
| V2C-C13 | Accessibility | axe-core: **0 serious/critical** violations in each of the 22 C2 screenshots' states. Unit tests assert the §4 roles: record `aria-label` per the 3.1 table for all 9 states, status `role="status"`, slot `aria-live="polite"`, patient list `role="radiogroup"`, fact glyph labels, `lang="th"` on `<html>`. Focus ring visible (computed outline ≥ 2 px, `--primary`) on every control in keyboard traversal. Tab order equals §4 Order | Playwright `a11y.spec.ts` (axe + tab order); `a11y.test.tsx` |
| V2C-C14 | Claim boundary and exact copy | Every §5 string used by an implemented state appears byte-exact (table-driven test over a copy module `mobile/lib/copy.ts`, compared with a fixture extracted from §5). The limitation label "ข้อมูลสังเคราะห์ · ต้นแบบเพื่อการวิจัย" is the last text on every screen. 0 occurrences in UI strings of `วินิจฉัย`, `อัจฉริยะ`, `AI-powered`, `Submit`, `OK`, `Cancel`, `Retry`. Transcript lines carry no speaker label | `copy.test.ts`; `static.test.ts` |
| V2C-C15 | Review never pretends success | Submit disabled until 6/6 decided. `submitReview` 404/405/501 → not-yet-connected notice, 0 renders of "ส่งเข้าเคสแล้ว"; 500/network → Submit error, decisions kept; only 2xx → submitted screen. `finish` is called exactly once per submit before `submitReview`, and its 409 is treated as done. After `finish`, "บันทึกต่อ" is hidden. Edited rows show "ระบบได้ยินว่า: <original>". `review.ts` contains `TODO(v2d)` | `review.test.tsx`, `review-client.test.ts` |
| V2C-C16 | Privacy and time validity | Spies show 0 writes to `localStorage`, `sessionStorage`, `indexedDB`, `caches` during a full scripted session. 0 `MediaRecorder` references in `mobile/`. The SDP POST has only the SDP body and the `Authorization`/`Content-Type` headers (no `patient_ref`, no `credentials:"include"`). Every posted turn has ISO-8601 `started_at`/`ended_at` with an offset, `started_at ≤ ended_at ≤` the request time, and non-decreasing `started_at` across the session. Playwright runs make 0 requests to non-local hosts | `privacy.test.ts`; `turn-queue.test.ts`; Playwright request guard |
| V2C-C17 | Nurse-only access | Non-nurse `GET /api/me` → the "Wrong role" copy + logout, no session start. 401 from any call → login screen with in-memory state cleared. `NEXT_PUBLIC_PUBLIC_DEMO=1` → one-click `POST /api/auth/demo-login {role:"nurse"}`; otherwise username/password → `POST /api/auth/login`; 401 / other / network → the three §5 login copies | `login.test.tsx` |
| V2C-C18 | Lifecycle | Wake lock requested on entering `listening` and released on every exit (paused, reconnecting, error, finishing, unmount). `hidden` while listening → `paused` + System pause copy, and visible does not auto-resume. Resume after the connection died while paused → `connecting` + one mint. `offline` while listening → `reconnecting`; `online` → an attempt within 100 ms. Planned rollover at `max_session_seconds` produces 0 duplicate and 0 lost completed items. At most 1 open peer connection at any moment | `lifecycle.test.ts` (fake timers, mocked `wakeLock`, `document.visibilityState`, `navigator.onLine`) |
| V2C-C19 | Scope held | `git diff --stat <base> -- backend casegraph schemas web requirements.in requirements.lock pyproject.toml` is empty. Changes are limited to `mobile/`, `scripts/sync_theme.sh`, `Makefile` and `slices/v2c/`. Existing isolation tests (`test_isolation_hygiene.py`, `backend/tests/voice/test_api_audit.py`) pass unmodified | checker `git diff`; `make test` |

## 13. Required test cases (mobile vitest unless marked Playwright)

| File | Cases (minimum) |
|---|---|
| `theme.test.ts` | theme byte-equality; colour-literal grep; manifest colours = tokens |
| `static.test.ts` | no `../web` import; no `livekit`/`openai` dep or string; no `MediaRecorder`; allowed-event grep; banned-word grep; no ad-hoc `font-family`; no SCBX name |
| `login.test.tsx` | password login ok / 401 / 500 / network; demo one-click; wrong role; 401 mid-session |
| `start.test.tsx` | consent × patient matrix (C4); `SYN-` validation and non-synthetic copy; access-code field shown only if `access_code_required`; code kept out of storage; patient list skeleton/empty/no-match states |
| `realtime.test.ts` | handshake order and headers (T1); https-only `connect_url`; send allowlist (C8); no media element on `ontrack`; `response.*` ignored |
| `turn-queue.test.ts` | delta → 0 POST; completed → 1 POST with exact body; duplicate; out-of-order; failed; 15 s timeout; >2000-char split; T5 409/422/5xx reconcile-then-retry; timestamps (C16) |
| `transport.test.ts` | the C7 reconnect script; mid-flight POST during reconnect; late event from a closed connection |
| `errors.test.tsx` | one case per T7 row (C9) |
| `lifecycle.test.ts` | wake lock, visibility, online/offline, rollover, single peer connection (C18) |
| `prompt-slot.test.tsx` | priority red flag > complete > listening > other; slot colour role by state; `aria-live`; question text only from `suggested_question_th`; extraction-unavailable notice keeps the last question on the neutral slot; complete slot swaps the one filled primary |
| `redflag.test.tsx` | all C5 assertions, including partial-delta hiding and post-acknowledgement transcript restore |
| `facts-display.test.tsx` | C6 table (6 fields × every state) |
| `review.test.tsx` / `review-client.test.ts` | confirm / edit / reject-with-reason / add / unknown; decided collapse and "เปลี่ยน"; 6/6 gate; C15 submit outcomes; edit shows the original |
| `copy.test.ts`, `a11y.test.tsx`, `wordmark.test.tsx`, `pwa.test.ts` | C14, C13, C12, C11 static parts |
| Playwright `screens.spec.ts` | 22 screenshots (C2) plus the access-code variant and the not-yet-connected variant at 390×844 |
| Playwright `a11y.spec.ts`, `touch.spec.ts`, `motion.spec.ts`, `pwa.spec.ts` | C13, C11 |

Playwright runs against `next build && next start` on 127.0.0.1 with `page.route("/api/**")` fixtures and an init script that fakes `getUserMedia`, `RTCPeerConnection`, the data channel and `wakeLock`. It blocks and fails on any non-local request.

## 14. Clinical, privacy and product risks

| Risk | Mitigation in v2c | Residual |
|---|---|---|
| The model speaks to the patient, or model text is shown as a question | T2 send allowlist + C8; no media element; questions only from `suggested_question_th` (allowlist) | none known |
| Red flag missed on a busy screen | C5: full-bleed alert, `role=alert`, focus, transcript hidden, prompts suppressed, finish blocked, no motion | acknowledgement is audited only once v2d exists (D-V2C-4) |
| Missing or uncertain allergy shown as "no allergy" | C6 table-driven test; negative only for KNOWN `none` | depends on v2a's allergy guard for the fact itself |
| Lost or duplicated turns around reconnects produce wrong or duplicate facts | T4–T6, C7, C18; single peer connection | speech during a disconnect is not transcribed; the reconnecting copy says so and the fields stay "ยังไม่มี" |
| Silent loss of a segment (transcription failed, POST failed) | failed-segment count in the transcript sheet (D-V2C-2); field stays MISSING, so the nurse is prompted again | a lost segment is not re-transcribed |
| Facts reach the case without human review | review requires 6/6 decisions; submit never fakes success (C15) | v2d owns the actual write |
| Recording without telling the patient | consent checkbox gates the record flow (C4) | the tick is not audited until v2d (D-V2C-4) |
| Audio bypasses the Model Gateway (owner-accepted deviation from Proposal §3.1) | secret minted and audited server-side; vendor URL only from the server; no vendor SDK or key in the client (C10) | disclosed in the slice report and final documentation (DECISIONS 2026-09-30) |
| Real patient data sent to the vendor | synthetic-only copy and `SYN-` ids; only audio + SDP go to the vendor; no patient ref to the vendor (C16) | the app cannot technically stop a real person speaking; the owner's approval covers synthetic role-play only |
| Transcript persisted on a shared phone | T11 memory only; SW without caches (C16, C11) | screen content is visible to bystanders by design (patient present) |

## 15. Decisions (the builder proceeds with the default; the reviewer or owner confirms)

- **D-V2C-1 (default: bundled roster).** The patient list is a bundled synthetic roster plus typed `SYN-` ids, because no backend endpoint lists waiting patients. A real queue endpoint is a later slice.
- **D-V2C-2 (default: proposed copy; owner confirms).** New strings not in the approved §5. The builder keeps them in `mobile/lib/copy.ts` under a `PROPOSED_V2C` key so the reviewer can find them:
  - access-code label "รหัสเข้าใช้บันทึกเสียง" and error "รหัสเข้าใช้ไม่ถูกต้อง ↵ ตรวจรหัสแล้วลองอีกครั้ง";
  - voice unavailable "ระบบบันทึกเสียงยังไม่พร้อมใช้งาน ↵ ข้อมูลที่ได้ยังอยู่ครบ จบเพื่อตรวจทานได้";
  - session ended "การบันทึกนี้ปิดไปแล้ว ↵ จบเพื่อตรวจทาน หรือเริ่มผู้ป่วยใหม่";
  - failed segments "ถอดข้อความไม่ได้ n ช่วง";
  - slot after an acknowledged red flag "คำถามแนะนำหยุดไว้ในการบันทึกนี้ ↵ ให้ประเมินผู้ป่วยตามแนวปฏิบัติของหน่วยงาน";
  - not yet connected "ยังส่งเข้าเคสไม่ได้ ↵ ส่วนเชื่อมต่อกับเคสยังไม่พร้อมในต้นแบบนี้ ข้อมูลที่ตรวจแล้วยังอยู่ในหน้านี้".
- **D-V2C-3 (default: finish at submit).** The backend `finish` is called at submit, not when leaving recording, so the approved "บันทึกต่อ" back link works on an active session. v2d must accept an already-finished session at submit.
- **D-V2C-4 (v2d).** Server-side audit of the consent tick and the red-flag acknowledgement belongs to v2d. Until then, both are client-local and are sent in the `TODO(v2d)` payload.
- **D-V2C-5 (clinical-safety-reviewer / D4).** v2a makes nurse-attention handoff sticky, so after "รับทราบ" no suggested question appears for the rest of the session. This is conservative and not a downgrade; confirm it is acceptable.
- **D-V2C-6 (integration).** Until v2a (`speaker:"unknown"`, `mode:"ambient"`, `next_action.kind`) and v2t (`purpose:"ambient"`, `ambient_supported`) are merged, the real backend rejects the mobile calls. v2c is accepted on mocks; an end-to-end check against the merged backend is a separate integration step, run by the integration-auditor.

## 16. Run commands (from the worktree root)

```bash
scripts/sync_theme.sh && git diff --exit-code mobile/app/theme.css      # C3
make test                                                                 # C1 (pytest + web vitest + mobile vitest + tsc)
cd mobile && npm test && npm run typecheck                                # C1, C4–C9, C12–C18 unit parts
cd mobile && OPENAI_API_KEY=sk-SENTINELv2c0000 VOICE_ACCESS_CODE=CODESENTINELv2c npm run build && npm run scan-bundle   # C10
cd mobile && npx playwright install chromium && npm run screens          # C2 -> artifacts/factory/v2c/screens/
cd mobile && npx playwright test                                          # C2, C11, C13, C16 browser parts
make mobile-dev                                                           # API :8000 + mobile :3002 (MOBILE_PORT), BACKEND_URL=http://127.0.0.1:8000
git diff --stat $(git merge-base HEAD main) -- backend casegraph schemas web requirements.in requirements.lock pyproject.toml   # C19: expect empty
```

Microphone capture on a phone needs HTTPS or localhost; phone testing through a tunnel or deployment is out of scope (D5).

The builder's evidence must contain: the `make test` tail, the mobile vitest and tsc output, the bundle-scan output, the 22 screenshot paths, the Playwright summary, and the C19 diff. The slice report states the Proposal §3.1 deviation (direct vendor WebRTC, audio outside the gateway, owner-accepted 2026-09-30).
