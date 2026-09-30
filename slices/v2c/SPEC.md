# Slice v2c: MedX mobile scribe app (`mobile/`)

Status: **design section only, awaiting owner approval of the comps.** The build section (API wiring, LiveKit, PWA, tests, acceptance) is added after approval. The builder does not start until the owner approves the comps in `slices/v2c/comp/png/`.

Source of truth: Proposal v8 §1.3.1 (Voice Agent), §2.1.6, §3.5; `docs/DECISIONS.md` 2026-09-30 (ambient + prompt scribe, separate `mobile/` PWA); `docs/UI-SPEC.md` (tokens, copy rules); `web/app/theme.css` (the only colours).

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
| `listening` | LiveKit room joined | pause · หยุดชั่วคราว · "หยุดบันทึกชั่วคราว" | `--primary-deep` with 2px `--primary` ring | outline | level meter · กำลังฟัง · clock runs |
| `paused` | tap in `listening`, or page hidden (system pause) | mic · บันทึกต่อ · "บันทึกต่อ" | filled `--primary` | outline | pause · หยุดชั่วคราว · clock frozen |
| `reconnecting` | unexpected disconnect; up to 3 automatic attempts | spinning loader · กำลังเชื่อมต่อ | disabled | outline | wifi-off · ขาดสัญญาณ |
| `error` | 3 attempts failed, or token/room error | rotate-ccw · ลองอีกครั้ง · "ลองเชื่อมต่ออีกครั้ง" | filled `--primary` | outline | mic-off · หยุดบันทึก |
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
