# MedX Clinical Front Door — UI Review & Redesign Blueprint

**Audited:** 2026-09-28  
**Target:** `factory/int-e1proj`  
**Baseline:** `docs/PROPOSAL.md`, implemented slice contracts (`s0`, `s3`, `s4`, `s6`, `t1`) and abstract 6-pillar UI standards  
**Target experience:** Thai-first clinical-operations demo; research prototype; synthetic data only  
**Screenshots:** 27 captures at 1280×800, 768×1024 and 390×844 in `.planning/ui-reviews/repository-20260928/` (git-ignored)

> Verdict: **ยังไม่พร้อมใช้เป็น end-to-end clinical-operations demo** แม้ safety controls ระดับโค้ดจะมีวินัยดี หน้า UI ปัจจุบันสะท้อนโครงสร้างการพัฒนาแบบแยก slice มากกว่า workflow ของผู้ใช้จริง ผู้ใช้เสีย case context ระหว่างหน้า, role home ยังเป็น placeholder, nurse เข้า intake จาก home ไม่ได้, pharmacist ไม่มี workflow และหน้าทบทวน physician ยาวถึง 4,214 px บน desktop / 7,480 px บน mobile

---

## Pillar Scores

| Pillar | Score | Key finding |
|---|---:|---|
| 1. Copywriting | **2/4** | Safety language ถูกต้อง แต่ English-first, technical และแสดง internal codes มากกว่าภาษางานของบุคลากร |
| 2. Visuals | **1/4** | Login มี visual direction แต่หน้าทำงานหลักเป็น raw lists/forms ไม่มี dashboard hierarchy หรือ case workspace |
| 3. Color | **3/4** | Token, contrast และ accent discipline ดี แต่มี semantic state เพียง warning palette เดียว จึงแยก urgency/status ไม่ได้ |
| 4. Typography | **2/4** | ฟอนต์ไทย/อังกฤษอ่านได้และ heading ชัด แต่ data-heavy screens ไม่มี typographic hierarchy สำหรับ scan ข้อมูล |
| 5. Spacing | **1/4** | ไม่มี spacing/component rules สำหรับ list, table, select, textarea และ review form; mobile เกิดการชนและความยาวเกินใช้งาน |
| 6. Experience Design | **1/4** | ไม่มี workflow ต่อเนื่อง, global navigation, patient context, assignment/handoff หรือ pharmacist task completion |

**Overall: 10/24**

### What is already solid

- Research disclaimer อยู่ก่อน content ทุกหน้าและแสดงทั้ง EN/TH (`web/app/layout.tsx:20-25`, `web/components/Disclaimer.tsx`).
- สีรวมศูนย์ใน `theme.css`, focus ring ชัด, contrast pairs ถูก test และใช้ purple เป็น accent อย่างมีวินัย (`web/app/globals.css:16-24`, `174-205`).
- Red flags มาก่อน suggestion และ review actions ถูก block จน acknowledge ตาม safety contract (`web/components/TriageReview.tsx:58-109`, `web/components/CareReview.tsx:105-156`, `239-304`).
- Loading, error, abstained และ reviewed states มีอยู่ใน source แม้ presentation ยังไม่เหมาะกับงานจริง.

---

## Top 3 Priority Fixes

1. **[BLOCKER] สร้าง shared app shell และ case workspace** — ปัจจุบันแต่ละ role/slice เป็นปลายทางแยกและ header ไม่มี navigation (`web/app/layout.tsx:22-26`) — ใช้ work queue → persistent case header → role task tabs → evidence/timeline เป็นโครงหลักเดียวกัน.
2. **[BLOCKER] เปลี่ยน list/review pages จาก raw document เป็น task-oriented UI** — triage 40 รายการยาว 2,032 px และ care review ยาว 4,214 px บน desktop — เพิ่ม queue table/cards, filters, status, progressive disclosure, sticky safety/action regions และ evidence drawer.
3. **[BLOCKER] ปิด workflow gaps ระหว่าง role** — nurse home ลิงก์เฉพาะ triage ไม่ลิงก์ intake (`web/app/nurse/page.tsx:8-14`) และ pharmacist home ไม่มี feature (`web/app/pharmacist/page.tsx:7-8`) — ออกแบบ handoff/state model และ medication-review entry point ก่อน polish เพิ่มเติม.

---

## Evidence from Rendered UI

### Desktop contact sheet

![Desktop audit contact sheet](../.planning/ui-reviews/repository-20260928/desktop-contact.png)

### Mobile contact sheet

![Mobile audit contact sheet](../.planning/ui-reviews/repository-20260928/mobile-contact.png)

### Measured page lengths

| Screen | Desktop | Tablet | Mobile | Observation |
|---|---:|---:|---:|---|
| Triage list | 2,032 px | 2,055 px | 3,215 px | 40 cases ไม่มี search/filter/status/pagination |
| Care list | 2,136 px | 3,923 px | 7,012 px | decision points ถูก render เป็นปุ่มต่อกันทั้งหมด |
| Triage review | 1,414 px | 1,533 px | 2,005 px | safety alert ดี แต่ action area ไม่มี persistent context |
| Care review | 4,214 px | 4,684 px | 7,480 px | vocabulary ทุกตัวถูกแสดงพร้อมกันใน checkbox form |

Representative evidence:

- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-login.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-triage-list.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-triage-review.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-care-list.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-care-review.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-voice-intake.png`
- `.planning/ui-reviews/repository-20260928/{desktop,tablet,mobile}-pharmacist-home.png`

Binary screenshots are intentionally git-ignored; this report and `.planning/ui-reviews/.gitignore` are the durable review artifacts.

---

## Findings by Failure Layer

### A. Clinical workflow

| ID | Severity | Routes / roles | Evidence | User impact | Recommendation |
|---|---|---|---|---|---|
| WF-01 | **BLOCKER** | All roles | Proposal requires one Clinical Dashboard with queue, timeline, draft summary, suggestions and role confirmation (`docs/PROPOSAL.md:46`), but current UI has isolated role/slice routes | ผู้ใช้ไม่เห็นว่าเคสอยู่ขั้นไหน ใครรับผิดชอบ และต้องทำอะไรต่อ | Introduce one case lifecycle and persistent case workspace |
| WF-02 | **BLOCKER** | Nurse | Home exposes only `/nurse/triage`; `/nurse/intake` is unreachable from UI (`web/app/nurse/page.tsx:8-14`) | Intake และ triage ไม่เป็น workflow เดียวกัน; demo ต้องพิมพ์ URL เอง | Nurse queue row should open intake, then triage, then handoff in one case context |
| WF-03 | **BLOCKER** | Pharmacist | Pharmacist route renders only shared placeholder (`web/app/pharmacist/page.tsx:7-8`) | หนึ่งในสาม target roles ทำงานใด ๆ ไม่ได้ | Add medication queue, discrepancy summary and pharmacist review concept before claiming end-to-end coverage |
| WF-04 | **BLOCKER** | Nurse → physician → pharmacist | No handoff or assignment UI; route map contains only role home/list/detail links | ไม่มี visible ownership or cross-role continuity | Add assignment, handoff status, timestamps and next responsible role to case header/timeline |
| WF-05 | WARNING | Reviewer roles | Review actions are rendered below long evidence/vocabulary documents | ต้อง scroll หลายพันพิกเซลและอาจสูญเสีย alert context ก่อน confirm/edit/reject | Use sticky review bar, compact acknowledged-safety summary and progressive disclosure |

### B. Information architecture

| ID | Severity | Routes / roles | Evidence | User impact | Recommendation |
|---|---|---|---|---|---|
| IA-01 | **BLOCKER** | Global | Header contains only wordmark and tagline (`web/app/layout.tsx:22-25`) | ไม่มี queue navigation, current role, case breadcrumb, notifications หรือ sign-out ใน task pages | Add responsive app shell with role-scoped primary nav and account menu |
| IA-02 | **BLOCKER** | Queue pages | Cases are plain `<ul>` collections (`TriageCaseList.tsx:60-70`, `CareCaseList.tsx:63-80`) | scan, sort, prioritize และ resume work ไม่ได้ | Replace with structured work queue: priority, patient/case, task, state, owner, updated time and primary action |
| IA-03 | WARNING | Case detail | Case ID exists only in page title; no persistent demographics/status/context | เสี่ยง review ผิดเคสเมื่อต้อง scroll หรือสลับ section | Sticky case header with synthetic badge, identifiers, current stage, assignment and latest timestamp |
| IA-04 | WARNING | Care review | All vocabulary options are expanded into fieldsets (`CareReview.tsx:275-296`) | cognitive load สูงและค้นหารายการช้า | Searchable command/select dialog with chosen items summarized separately |
| IA-05 | WARNING | Mobile | Only login has a media query (`web/app/globals.css:155-159`) | core screens are merely narrowed desktop documents | Define mobile-specific queue cards, section navigation and bottom review actions |

### C. Component system

| ID | Severity | Evidence | User impact | Recommendation |
|---|---|---|---|---|
| DS-01 | **BLOCKER** | CSS styles only `input`, `button`, links and alert; no rules for `select`, `textarea`, `table`, `fieldset` (`globals.css:161-205`) | native controls look inconsistent and hierarchy disappears | Build shared form, table, fieldset, badge, card, banner and drawer primitives |
| DS-02 | WARNING | Same yellow `[role="alert"]` styling is used for urgent red flags, validation errors and incomplete screening (`globals.css:198-205`) | distinct meanings look identical | Keep text/glyph semantics and add clinically reviewed state tokens: critical, warning, incomplete, success, neutral |
| DS-03 | WARNING | Busy state disables every list button but shows no row-level progress (`TriageCaseList.tsx:29-41`, `CareCaseList.tsx:27-42`) | ผู้ใช้ไม่รู้ว่า action ใดกำลังทำงาน | Use row-level pending indicator, preserve unrelated actions and announce completion/error |
| DS-04 | WARNING | Empty arrays render empty `<ul>` with no empty-state guidance | หน้าขาว/ว่างดูเหมือนโหลดผิดพลาด | Add role-specific empty states with cause, next step and refresh/retry where appropriate |
| DS-05 | WARNING | Role homes use a slide-like `PageFrame` grammar (`RoleHome.tsx:20-37`) | design language ของ presentation ถูกใช้กับ operational workspace | Limit editorial/marketing grammar to login/about; use dashboard shell for authenticated routes |

### D. Cosmetic and content presentation

| ID | Severity | Evidence | User impact | Recommendation |
|---|---|---|---|---|
| UI-01 | WARNING | English labels surround Thai clinical content throughout review screens | ผู้ใช้ไทยต้อง context-switch ต่อเนื่อง | Thai-first labels and actions; show English/code as secondary metadata |
| UI-02 | WARNING | Raw ISO timestamps, evidence IDs, rule IDs and enum values are rendered inline (`TriageReview.tsx:53-55`, `74-78`, `118-124`) | information density สูงและอ่านยาก | Localized date/time; human label first; technical metadata in expandable evidence panel |
| UI-03 | WARNING | Global `h1` 36 px and page max-width rules suit sparse pages but not dense operations (`globals.css:56-98`) | headings consume space while task data remains undifferentiated | Introduce operational type scale and data typography for labels, values and metadata |
| UI-04 | WARNING | Buttons wrap into complaint text in mobile triage list | touch targets compete with case content and create accidental-action risk | Whole-row/card affordance with one trailing primary action, minimum 44×44 px target |
| UI-05 | WARNING | Disclaimer repeats two full lines at the top of every mobile view | safety copy remains visible but consumes a large part of the initial viewport | Preserve exact prominent wording; use compact sticky/collapsible treatment after acknowledgement without hiding prototype status |

---

## Detailed 6-Pillar Assessment

### 1. Copywriting — 2/4

**Strengths**

- Claim boundary is consistently explicit: “suggestion for review”, “research prototype”, synthetic-only and mandatory human confirmation.
- Red-flag copy states priority clearly and avoids implying diagnosis or autonomous care.
- Abstention and missingness copy correctly avoid treating unknown as negative (`CareReview.tsx:199-220`).

**Findings**

- **[WARNING] English-first operational copy conflicts with the selected Thai-first experience.** Page titles, actions, errors and field labels remain English while complaint/evidence content may be Thai.
- **[WARNING] Copy exposes implementation language rather than action language.** Examples: `partially_evaluated`, `MOCK baseline — not calibrated`, rule IDs, evidence refs and raw missing-input keys.
- **[WARNING] Generic errors are not recoverable.** “Please try again” does not explain whether data was saved, whether retry is safe, or where to return (`TriageCaseList.tsx:41`, `RoleGuard.tsx:37`).
- **[WARNING] Placeholder copy is visible in all three role homes** (`RoleHome.tsx:24-32`), undermining demo credibility.

**Direction**

- Use Thai action-first labels: “เริ่มซักประวัติ”, “ทบทวนการคัดกรอง”, “ส่งต่อแพทย์”, “ยืนยันข้อเสนอ”, “ขอข้อมูลเพิ่ม”.
- Technical IDs remain available in an “หลักฐานและรายละเอียดระบบ” disclosure.
- Errors specify consequence and recovery: what failed, whether work was saved and the exact next action.

### 2. Visuals — 1/4

- **[BLOCKER] The visual system stops at branding.** Login has a considered cover treatment, but authenticated screens are plain documents/lists/forms.
- **[BLOCKER] No operational focal point.** Queues do not surface urgent/pending/assigned work; details do not summarize case state or next action.
- **[WARNING] Dense screens lack grouping and progressive disclosure.** Care review displays the complete option vocabulary before edit/reject controls.
- **[WARNING] Visual hierarchy is driven mainly by HTML heading size, not clinical priority, state or task sequence.**

### 3. Color — 3/4

**Strengths**

- Centralized tokens and WCAG-oriented contrast are strong (`theme.css`; `theme.test.ts`).
- Purple remains an accent and is not incorrectly used as urgency color.
- Focus and warning boundaries are visible.

**Findings**

- **[WARNING] One warning palette carries too many meanings:** research disclaimer, validation error, allergy conflict, incomplete screening and urgent red flag.
- **[WARNING] Queue/status semantics have no visual tokens.** Pending review, reviewed, abstained, error and handoff cannot be distinguished at scan speed.

**Direction**

- Add semantic tokens only after safety review; never rely on color alone. Pair every state with label, icon/glyph and accessible text.

### 4. Typography — 2/4

**Strengths**

- SCBXBeta2 renders Thai and Latin consistently with self-hosted fonts.
- Major headings and body copy are readable at tested sizes.

**Findings**

- **[WARNING] Editorial scale is reused for operational data.** There is no compact but accessible hierarchy for patient identifiers, timestamps, source labels, values and action metadata.
- **[WARNING] Long bilingual vocabulary labels become dense paragraphs with codes appended inline.**
- **[WARNING] Raw identifiers and timestamps visually compete with clinical content.**

### 5. Spacing — 1/4

- **[BLOCKER] No spacing/layout contract exists for core task components.** Lists, tables, fieldsets, textareas and selects inherit browser layout.
- **[BLOCKER] Mobile list items and buttons collide.** The 390 px triage capture visibly interleaves complaint text and `Assess` buttons.
- **[WARNING] Full-page forms reach 7,480 px on mobile** with no section index, accordion, sticky context or action summary.
- **[WARNING] Desktop content uses only part of the available width while long lists grow vertically.**

### 6. Experience Design — 1/4

- **[BLOCKER] End-to-end task completion is impossible across all target roles.** Pharmacist has no task UI and cross-role handoff is absent.
- **[BLOCKER] Case context does not persist.** Users navigate between role home, list and detail without a shared timeline or patient workspace.
- **[BLOCKER] Mobile is not a focused companion.** It receives the same large document/forms as desktop.
- **[WARNING] Loading and error states exist, but no skeleton/context-preserving retry or offline/reconnect guidance exists.**
- **[WARNING] Empty queues are not handled.**
- **Positive safety finding:** confirm/edit/reject are disabled until required acknowledgements, and alerts precede suggestions.

---

## Redesign Blueprint

### Design principles

1. **งานก่อนข้อมูล:** ทุกหน้าตอบได้ทันทีว่า “เคสไหน, อยู่ขั้นไหน, ต้องทำอะไรต่อ, ใครรับผิดชอบ”.
2. **หนึ่งเคส หนึ่ง context:** intake, triage, care และ medications อยู่ใต้ case workspace เดียว.
3. **Safety remains visible:** red flags and incomplete screening stay above suggestions and persist in compact form near review actions.
4. **Thai first, evidence on demand:** ภาษางานเป็นไทย; code, model metadata และ raw evidence เปิดดูชั้นรอง.
5. **Progressive disclosure:** สรุปก่อน รายละเอียดและ provenance เปิดเมื่อจำเป็น.
6. **Responsive by task:** desktop = full workspace, tablet = full task flow, mobile = focused companion.

### Proposed information architecture

```text
/login
/app
├── /queue                         role-scoped work queue
├── /cases/:caseId                 shared case overview
│   ├── /intake                    nurse intake + transcript/facts
│   ├── /triage                    nurse alert + department review
│   ├── /care                      physician suggestion review
│   ├── /medications               pharmacist reconciliation review
│   ├── /timeline                  clinical/evidence timeline
│   └── /activity                  human actions + handoffs + audit summary
└── /account                       role/session/sign out
```

The route proposal is conceptual. Existing backend routes remain unchanged in this audit.

### Existing-to-proposed route mapping

| Existing route | Proposed destination | Notes |
|---|---|---|
| `/nurse` | `/app/queue?task=intake,triage` | Replace placeholder with assigned/pending nurse tasks |
| `/nurse/intake` | `/app/cases/:caseId/intake` | Keep current session/fact API behind shared case context |
| `/nurse/triage` | `/app/queue?task=triage` | Replace fixture list with queue presentation |
| `/nurse/triage/:assessmentId` | `/app/cases/:caseId/triage` | Assessment becomes task state within the case |
| `/physician` | `/app/queue?task=care` | Replace placeholder with assigned care reviews |
| `/physician/care` | `/app/queue?task=care` | Group decision points under each case |
| `/physician/care/:assessmentId` | `/app/cases/:caseId/care` | Compact summary + evidence drawer + review bar |
| `/pharmacist` | `/app/queue?task=medications` | New product surface; backend contract still required |

### Role flows

```text
NURSE
Queue → Open case → Intake → Review extracted facts
      → Triage alerts + department suggestion → Confirm/edit/reject
      → Handoff to physician → Case remains traceable in timeline

PHYSICIAN
Assigned queue → Open handed-off case → Review alert/screening state
               → Read compact summary → Inspect evidence as needed
               → Confirm/edit/reject care suggestion → Handoff/status update

PHARMACIST
Medication queue → Open case → Compare source medication lists
                 → Review discrepancy cards + provenance
                 → Confirm/edit/reject issues → Complete/handoff
```

---

## Low-Fidelity Wireframes

### 1. Login

```text
┌──────────────────────────────────────────────────────────────┐
│ ต้นแบบเพื่อการวิจัย · ข้อมูลสังเคราะห์ · ไม่ใช้กับผู้ป่วยจริง │
├───────────────────────────────┬──────────────────────────────┤
│ MedX                          │ เข้าสู่ระบบ                  │
│ AI Clinical Front Door       │ ชื่อผู้ใช้  [_____________]  │
│                               │ รหัสผ่าน    [_____________]  │
│ Human-reviewed clinical      │ [ เข้าสู่ระบบ ]              │
│ decision-support prototype   │                              │
└───────────────────────────────┴──────────────────────────────┘
```

### 2. Role dashboard / work queue

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ MedX | คิวงาน | เคสของฉัน | [Nurse] [บัญชีผู้ใช้]                     │
├──────────────┬──────────────────────────────────────────────────────────┤
│ คิวงาน       │ งานที่ต้องดำเนินการ                           12 รายการ │
│ • ทั้งหมด 12 │ [ค้นหาเคส] [สถานะ▼] [ความเร่งด่วน▼] [ผู้รับผิดชอบ▼]     │
│ • เร่งด่วน 3 │ ┌──────────────────────────────────────────────────────┐ │
│ • รอฉัน 5    │ │ ⚠ ต้องทบทวน | SYN-S4-001 | เจ็บแน่นหน้าอก          │ │
│ • ส่งต่อแล้ว │ │ Intake ครบ · Triage รอยืนยัน · อัปเดต 5 นาทีที่แล้ว │ │
│              │ │ ผู้รับผิดชอบ: คุณ                         [เปิดเคส] │ │
│              │ └──────────────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────────┘
```

### 3. Shared case workspace — desktop

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ MedX | คิวงาน > SYN-S4-001                         Nurse · ออกจากระบบ │
├─────────────────────────────────────────────────────────────────────────┤
│ SYN-S4-001  [ข้อมูลสังเคราะห์]  ขั้น: ทบทวน Triage  ผู้รับผิดชอบ: คุณ │
│ 54 ปี · หญิง · เจ็บแน่นหน้าอก · อัปเดต 09:10                       │
├────────────┬───────────────────────────────────────┬────────────────────┤
│ ภาพรวม     │ ⚠ Red flag: Acute chest pain          │ หลักฐาน            │
│ Intake     │ ต้องส่งต่อบุคลากรทันที                 │ Timeline            │
│ Triage ●   │ [✓ รับทราบ alert]                      │ • 09:03 Intake      │
│ Care       ├───────────────────────────────────────┤ • 09:05 Vitals      │
│ Medications│ แผนกที่ระบบเสนอ                       │ • 09:08 Rule match  │
│ Activity   │ Cardiology · ความไม่แน่นอนต่ำ          │ [ดูรายละเอียด]      │
│            │ (MOCK — not calibrated)               │                    │
│            │                                       │                    │
│            │ [ยืนยัน] [แก้ไข] [ปฏิเสธ]             │                    │
└────────────┴───────────────────────────────────────┴────────────────────┘
```

### 4. Intake workspace

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Case header: SYN-... · Intake กำลังดำเนินการ · ผู้รับผิดชอบ: Nurse    │
├─────────────────────────────────────┬───────────────────────────────────┤
│ บทสนทนา                             │ ข้อมูลที่สกัดได้                 │
│ Agent: เริ่มมีอาการเมื่อไรคะ          │ ✓ อาการสำคัญ                     │
│ Patient: เริ่มเมื่อเช้านี้...         │ ✓ ระยะเวลา                       │
│                                     │ ! ประวัติแพ้ยา ต้องยืนยัน         │
│ ผู้พูด [ผู้ป่วย▼]                    │ ○ ยาที่ใช้อยู่ ยังขาด             │
│ [พิมพ์ข้อความ____________________]  │                                   │
│ [เพิ่มข้อความ]                       │ [จบการซักประวัติและทบทวน]        │
└─────────────────────────────────────┴───────────────────────────────────┘
```

### 5. Physician care review

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Case header + handoff: Nurse → Physician · รอทบทวน                    │
├─────────────────────────────────────────────────────────────────────────┤
│ ⚠ Screening incomplete: 8 rules not evaluated [รับทราบ] [ดูทั้งหมด]   │
├───────────────────────────────┬─────────────────────────────────────────┤
│ สรุปเคส                      │ หลักฐาน / Timeline                      │
│ • อาการและระยะเวลา           │ เลือกรายการเพื่อดู source + timestamp   │
│ • Vitals ล่าสุด               │                                         │
│ • Allergy / medications       │                                         │
├───────────────────────────────┴─────────────────────────────────────────┤
│ ข้อมูลที่ควรเก็บเพิ่ม [ + เพิ่มรายการ ]                               │
│ Care-pathway options [ + เพิ่มรายการ ]                                │
├─────────────────────────────────────────────────────────────────────────┤
│ Sticky review bar: [ยืนยันข้อเสนอ] [แก้ไข] [ปฏิเสธ]                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6. Pharmacist medication review

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Medication review · SYN-... · รอเภสัชกรทบทวน                         │
├─────────────────────┬─────────────────────┬─────────────────────────────┤
│ ยาเดิม              │ จาก Voice Intake   │ คำสั่งยาปัจจุบัน             │
│ Drug A · dose · freq │ Drug A · dose ?    │ Drug A · new dose            │
├─────────────────────┴─────────────────────┴─────────────────────────────┤
│ ประเด็นที่พบ                                                         │
│ ! ขนาดยาไม่ตรงกัน    แหล่ง A ↔ C          [ยืนยัน] [แก้ไข] [ไม่ใช่]  │
│ ! ข้อมูลความถี่หาย    แหล่ง B              [ยืนยัน] [แก้ไข] [ไม่ใช่]  │
├─────────────────────────────────────────────────────────────────────────┤
│ [เสร็จสิ้นการทบทวนและส่งต่อ]                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7. Mobile focused companion

```text
┌──────────────────────────────┐
│ MedX   คิวงาน        [บัญชี]│
│ SYN-S4-001 · สังเคราะห์      │
│ Triage · รอฉันทบทวน          │
├──────────────────────────────┤
│ ⚠ Acute chest pain           │
│ ต้องส่งต่อบุคลากรทันที        │
│ [รับทราบ alert]              │
├──────────────────────────────┤
│ สรุปเคส                      │
│ เจ็บแน่นหน้าอก ร้าวแขนซ้าย   │
│ Vitals ล่าสุด 09:05          │
│ [ดูหลักฐานและ timeline]      │
├──────────────────────────────┤
│ แผนกที่เสนอ: Cardiology      │
│ MOCK · not calibrated        │
├──────────────────────────────┤
│ [ยืนยัน] [แก้ไข] [ปฏิเสธ]   │ ← sticky bottom actions
└──────────────────────────────┘
```

Mobile supports queue triage, alerts, summary, evidence lookup and safe confirmation/handoff. Large vocabulary editing and full transcript work should move users to tablet/desktop with a clear handoff, not squeeze the full desktop form into 390 px.

---

## Shared Component System

| Component | Responsibility | Required states |
|---|---|---|
| `AppShell` | Global navigation, role/account, prototype status | desktop sidebar, tablet rail, mobile header/bottom nav |
| `WorkQueue` | Search/filter/sort/group actionable cases | loading, empty, error, stale, paginated |
| `QueueItem` | Case/task summary with one primary action | priority, assigned, waiting, completed, blocked |
| `CaseHeader` | Persistent synthetic badge, identifiers, stage, owner, updated time | compact/sticky/mobile |
| `CaseSectionNav` | Intake/Triage/Care/Medications/Activity | role-disabled, pending badge, completed |
| `SafetyBanner` | Red flag, incomplete screening, allergy conflict | critical, warning, incomplete; text + icon + label |
| `StatusBadge` | Workflow status only, never clinical meaning by color alone | pending, in-progress, handoff, reviewed, abstained, error |
| `Timeline` | Time-valid evidence and human actions | grouped, filtered, empty |
| `EvidenceDrawer` | Human-readable evidence with raw refs on demand | loading, missing source, future-invalid blocked |
| `SuggestionCard` | Summary, uncertainty and provenance | suggested, abstained, provider error, reviewed |
| `ReviewBar` | Acknowledgements and confirm/edit/reject | blocked reason, busy, success, conflict/409 |
| `SearchablePicker` | Replace huge checkbox vocabularies | search, max-selected, no match, selected summary |
| `ResponsiveDataView` | Table on desktop, cards on narrow screens | keyboard, touch, overflow-safe |

### Visual system additions

- Keep current neutral/purple brand tokens and SCBXBeta2.
- Add an operational spacing scale and density modes; do not style core controls ad hoc.
- Add semantic state tokens only after clinical safety review. Every state includes visible text and glyph.
- Separate page title typography from data typography (`label`, `value`, `metadata`, `code`, `timestamp`).
- Standardize control height and touch target at **≥44×44 px** on touch layouts.

---

## Responsive Contract

### Desktop ≥ 1024 px

- Persistent side navigation and 2–3 column case workspace.
- Queue uses table-like rows with sticky header, filters and pagination/virtualization.
- Evidence/timeline may remain visible beside the active task.
- Review bar remains visible while scrolling without obscuring content.

### Tablet 600–1023 px

- Collapsible navigation rail.
- One primary work column plus slide-over evidence drawer.
- All core actions remain available; tables convert to compact rows/cards before horizontal overflow.
- Review controls remain sticky and touch-friendly.

### Mobile < 600 px

- Focused companion only: queue, alerts, compact summary, evidence lookup, acknowledgement, confirmation and handoff.
- Full transcript editing and large vocabulary editing show “ทำต่อบน tablet/desktop” with preserved case/task state.
- No inline action may collide with text; no horizontal scrolling at 390 px.
- Technical metadata is collapsed by default.

---

## Backend and Data Gaps

These are **concept requirements, not claims about existing APIs**. No backend contract is changed by this review.

| Gap | Why the redesign needs it | Minimum concept response |
|---|---|---|
| Unified case lifecycle | Current APIs expose slice-specific assessments only | case id, current stage, task statuses, latest activity, synthetic/data class |
| Role work queue | Role homes cannot show actionable workload | task id/type, case id, priority reason, status, assignee, updated time |
| Assignment/claiming | Users cannot see ownership | assignee, claimed/released timestamps, optimistic conflict behavior |
| Cross-role handoff | Nurse → physician → pharmacist continuity is absent | from/to role, reason/category, status, actor and timestamp |
| Unified timeline | Evidence and actions are spread across modules | time-valid evidence refs plus human review/handoff events |
| Compact audit summary | Full raw audit data is not appropriate in primary UI | action label, actor role/id, timestamp and linked immutable record |
| Pharmacist queue/review | No pharmacist task API/UI is present | medication sources, discrepancies, review actions and provenance |
| Human-readable dictionaries | Raw enum/code strings dominate UI | localized labels/descriptions for fields, rules, statuses and codes |

Any new write operation must preserve append-only audit behavior, role enforcement, synthetic-data boundary and human-confirmation rules.

---

## Prioritized Remediation Backlog

### P0 — Workflow and safety blockers

1. Define unified case/task/handoff state model and role permissions.
2. Specify pharmacist workflow and minimum API contract before claiming end-to-end coverage.
3. Design shared case header and persistent safety/review state.
4. Make intake reachable from nurse workflow and preserve context into triage.
5. Replace full-page care vocabulary form with progressive, searchable selection.

### P1 — Shared shell and information architecture

1. Implement authenticated `AppShell` with role navigation, account and sign-out on every task page.
2. Implement role-scoped `WorkQueue` and `CaseWorkspace` route structure.
3. Add case timeline/activity and cross-role handoff presentation.
4. Add Thai-first content dictionary and localized date/time formatting.

### P2 — Core component system

1. Queue rows/cards, filters, empty/error/loading states.
2. Case header, status badges and section navigation.
3. Safety banners, suggestion cards, evidence drawer and sticky review bar.
4. Styled select/textarea/fieldset/table and searchable picker.
5. Responsive primitives and touch targets.

### P3 — Role-specific workflows

1. Nurse intake + extracted-fact review.
2. Nurse triage + department review + handoff.
3. Physician care review with compact evidence and edit flow.
4. Pharmacist medication reconciliation and discrepancy review.

### P4 — Visual polish and responsive refinement

1. Operational typography and density tuning.
2. Clinically reviewed semantic state tokens.
3. Skeletons, transitions and clearer retry/confirmation feedback.
4. Visual-regression coverage across desktop, tablet and mobile.

---

## Acceptance Criteria for the Next UI Phase

### Workflow

- A nurse can enter from the queue, complete/review intake, open triage and hand off the same synthetic case without typing a URL or losing case context.
- A physician can see assigned handoffs, review safety state and complete confirm/edit/reject from the shared case workspace.
- A pharmacist can open a medication-review task and complete discrepancy review through a defined prototype flow.
- Every role sees current task status, owner, last update and next action.

### Safety

- Research/synthetic-data status remains visible on every route.
- Red flags and incomplete screening precede suggestions visually and in DOM order.
- Confirm/edit/reject remain blocked until all required acknowledgements are complete.
- Suggestions never appear as diagnosis, treatment, prescription or autonomous care.
- All writes retain role enforcement, immutable review semantics and audit identity/time.

### Responsive and visual

- No horizontal overflow or text/action collision at 390 px, 768 px or 1280 px.
- Queue pages provide search/filter/status and do not render all records as one unstructured list.
- Mobile exposes only focused-companion actions; unsupported deep edits provide a state-preserving desktop/tablet handoff.
- Interactive touch targets are at least 44×44 px on touch layouts.
- Technical metadata is subordinate to human-readable Thai content and expandable on demand.

### States and accessibility

- Every queue/workspace has explicit loading, empty, error, stale/retry and success states.
- Keyboard-only completion works for login, queue navigation, evidence disclosure and review actions.
- Focus remains visible; focus moves to meaningful content after navigation and successful actions.
- Axe reports zero serious or critical violations on the primary role flows at all three target widths.
- Visual-regression screenshots cover login, queues, case workspace, safety states, abstention, errors and reviewed results.

### Evaluation evidence

- Usability walkthrough covers one synthetic end-to-end case per role.
- A reviewer can identify case, stage, owner, top safety state and next action within five seconds on desktop/tablet.
- Mobile walkthrough confirms queue triage, alert review, case summary and safe handoff without exposing the full desktop editing workload.

---

## Files Audited

Primary implementation:

- `web/app/layout.tsx`, `web/app/globals.css`, `web/app/theme.css`
- `web/app/login/page.tsx`
- `web/app/nurse/**`, `web/app/physician/**`, `web/app/pharmacist/page.tsx`
- `web/components/RoleHome.tsx`, `PageFrame.tsx`, `RoleGuard.tsx`
- `web/components/TriageCaseList.tsx`, `TriageReview.tsx`, `TriageReviewLoader.tsx`
- `web/components/CareCaseList.tsx`, `CareReview.tsx`, `CareReviewLoader.tsx`
- `web/components/voice/VoiceIntake.tsx`
- `web/lib/copy.ts`, `triage.ts`, `care.ts`, `voice.ts`

Contracts and tests:

- `docs/PROPOSAL.md`, `docs/DECISIONS.md`, `CLAUDE.md`
- `slices/s0/SPEC.md`, `slices/s3/SPEC.md`, `slices/s4/SPEC.md`, `slices/s6/SPEC.md`, `slices/t1/SPEC.md`
- `web/tests/**`, `web/e2e/**`

Registry audit: `components.json` is absent; no shadcn or third-party component registry audit was required.

