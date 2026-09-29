---
phase: U1-U3
slug: medx-clinical-operations-rebuild
status: approved
shadcn_initialized: true
preset: "New York; neutral base; CSS variables; RSC; Lucide"
created: 2026-09-28
reviewed_at: 2026-09-28
---

# MedX Clinical Operations — UI Design Contract

> สัญญาการออกแบบกลางสำหรับเดโม synthetic journey ตั้งแต่ Nurse → Physician → Pharmacist อ้างอิง `docs/UI-REVIEW.md` และข้อกำหนดความปลอดภัยเดิมของโครงการ

## Product frame

- MedX เป็น **research prototype สำหรับข้อมูลสังเคราะห์เท่านั้น** ไม่ใช่เครื่องมือวินิจฉัย รักษา หรือสั่งยา
- ทุกหน้าหลังเข้าสู่ระบบต้องทำให้ผู้ใช้ระบุ case, stage, owner, safety state และ next action ได้ภายใน 5 วินาที
- patient/case context ต้องคงอยู่ใน shared case workspace; บทบาทเปลี่ยนงาน ไม่ใช่เปลี่ยนเป็นคนละผลิตภัณฑ์
- red flags มาก่อน suggestions เสมอ; uncertainty สูงต้อง abstain/escalate; ทุกข้อเสนอมี human confirmation และ audit identity/time
- ภาษาไทยเป็นชั้นหลัก ส่วน English, code, evidence ID, model/provider/version และศัพท์มาตรฐานเป็น metadata ชั้นรอง

## Design System

| Property | Value |
|---|---|
| Tool | Tailwind CSS + shadcn/ui official components |
| Preset | New York density, neutral base, CSS variables, RSC |
| Component library | Radix UI primitives; no third-party registry |
| Icon library | Lucide; meaningful icons always paired with text or accessible label |
| Font | SCBXBeta2, system sans-serif fallback |
| Corner / shadow | 8px controls, 12px cards; borders before shadows; one subtle elevation level only |
| Motion | 150–200ms for disclosure/navigation; none for safety alerts; respect reduced motion |

Official building blocks: Button, Badge, Card, Input, Label, Textarea, Select, Dialog, AlertDialog, Tabs, Tooltip, Popover, Command, ScrollArea, Separator, Skeleton, Table and Sheet/Drawer. Product composites: `AppShell`, `WorkQueue`, `CaseHeader`, `CaseSectionNav`, `SafetyBanner`, `Timeline`, `EvidenceDrawer`, `SuggestionCard`, `ReviewBar`, `SearchablePicker` and responsive data views.

## Spacing Scale

Only these layout values are permitted. The 44px minimum control size is an accessibility target, not a spacing token.

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | icon gap, metadata separation |
| sm | 8px | compact control group, badge padding |
| md | 16px | standard field/card gap |
| lg | 24px | section/card padding |
| xl | 32px | page column and major group gap |
| 2xl | 48px | major section break |
| 3xl | 64px | page-level breathing room |

Exceptions: none. Borders may be 1px and radii may be 8/12px because they are not layout spacing.

## Typography

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Body / metadata | 14px | 400 | 1.5 |
| Primary body / control | 16px | 400 or 700 | 1.5 |
| Section heading | 20px | 700 | 1.3 |
| Page heading / display | 28px | 700 | 1.3 |

- Maximum four sizes and two weights. Labels use 14px/700; no all-caps Thai.
- IDs and clinical codes may use tabular numerals but remain in SCBXBeta2/system fallback.
- Thai text must wrap naturally; no fixed-height content containers and no ellipsis for safety-critical text.

## Color

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `#F5F8FB` | app background and broad canvas |
| Secondary (30%) | `#FFFFFF`; navigation `#E7F0F7` | cards, panels, sidebar and top navigation |
| Accent (10%) | `#0B5CAD` | primary CTA, active navigation, links and focus ring only |
| Critical / destructive | `#B42318` | red flags, destructive action and irreversible confirmation |
| Warning | `#B54708` | stale/partial/attention states |
| Success | `#067647` | reviewed/complete/confirmed states |
| Primary ink | `#12212F` | high-emphasis text |
| Muted ink | `#526577` | metadata and secondary copy |
| Border | `#C9D6E2` | boundaries and table rules |

Accent is reserved for primary CTA, active navigation, links and focus ring. Status is never communicated by color alone: every status includes Thai text plus a Lucide glyph. Secondary actions are neutral outline/ghost; destructive actions never use the blue accent.

## Visual hierarchy and focal points

1. **Case identity and safety** — sticky `CaseHeader` plus `SafetyBanner` are first in reading/tab order.
2. **Next safe action** — one blue primary action per working surface; alternatives are neutral.
3. **Current evidence/work** — cards, timeline or responsive data view beneath the header.
4. **Metadata and model provenance** — visually quieter, disclosed on demand in `EvidenceDrawer`.

Desktop uses a 240px app navigation, flexible work canvas and optional 360px evidence drawer. Tablet collapses navigation to a top/rail control while retaining full task capability. Mobile shows a focused queue, alerts, case summary and safe confirmation/handoff; transcript and large-vocabulary editing display “ทำงานนี้ต่อบนแท็บเล็ตหรือเดสก์ท็อป” while preserving `runId`, `caseId` and draft state.

## Information architecture and routes

| Route | Purpose | Primary roles |
|---|---|---|
| `/demo` | choose seeded journey and create an isolated presenter run; enabled only when `DEMO_MODE=1` | signed-in synthetic users |
| `/login` | synthetic account sign-in | all |
| `/app/queue` | role-aware work queue and ownership | all |
| `/app/cases/:caseId/overview` | shared case summary, stage, owner, safety and next action | all |
| `/app/cases/:caseId/intake` | voice intake and transcript review | nurse |
| `/app/cases/:caseId/triage` | triage suggestion review | nurse |
| `/app/cases/:caseId/care` | care suggestion review | physician |
| `/app/cases/:caseId/medications` | medication sources and discrepancy review | pharmacist |
| `/app/cases/:caseId/timeline` | clinical-operational timeline | all |
| `/app/cases/:caseId/activity` | append-only review/handoff audit | all |

Legacy role homes `/nurse`, `/physician` and `/pharmacist` redirect to `/app/queue`. The domain work pages `/nurse/triage`, `/nurse/triage/:assessmentId`, `/nurse/intake`, `/physician/care`, `/physician/care/:assessmentId` and `/pharmacist/reconcile` stay at their routes inside the `AppShell` (role links in the navigation), each behind its own RoleGuard; they are not redirected into the seeded demo case, whose header shows a different synthetic patient (slice U4, pending owner confirmation).

## Role journeys

- **Nurse:** คิวงาน → รับเคส → บันทึก intake → ตรวจ triage → ยืนยัน/แก้ไข/ปฏิเสธ → ส่งต่อแพทย์
- **Physician:** เคสที่ได้รับมอบหมาย → patient timeline/evidence → ตรวจ care suggestion → ยืนยัน/แก้ไข/ปฏิเสธ → ส่งต่อเภสัชกร
- **Pharmacist:** คิวยา → medication source comparison → discrepancy/provenance → ยืนยัน/แก้ไข/ปฏิเสธ → ปิด review
- Cross-role handoff always shows destination role, current stage, unresolved alerts and a required note when an unresolved warning exists.

## Copywriting Contract

### Fixed actions

| Context | Copy |
|---|---|
| Login | `เข้าสู่ระบบเดโม` |
| Create run | `เริ่มรอบเดโมใหม่` |
| Open case | `เปิดเคส` |
| Claim task | `รับเคสนี้` |
| Save intake | `บันทึกข้อมูลรับเข้า` |
| Run triage | `ประเมินการคัดกรอง` |
| Confirm suggestion | `ยืนยันข้อเสนอแนะ` |
| Edit suggestion | `แก้ไขก่อนยืนยัน` |
| Reject suggestion | `ปฏิเสธข้อเสนอแนะ` |
| Handoff | `ส่งต่อให้แพทย์` / `ส่งต่อให้เภสัชกร` |
| Open evidence | `ดูหลักฐานและที่มา` |
| Sign out | `ออกจากระบบ` |
| Neutral dismissal | `กลับไปตรวจสอบ` — never “ยกเลิก/Cancel” alone |

### Fixed state copy

| State | Heading / message | Required solution or next step |
|---|---|---|
| Loading | `กำลังโหลดข้อมูลเคส…` | skeleton preserves final layout; disable duplicate action |
| Empty queue | `ยังไม่มีเคสที่ต้องดำเนินการ` | `ตรวจสอบบทบาทที่เข้าสู่ระบบ หรือกลับมาดูคิวอีกครั้งภายหลัง` |
| Empty evidence | `ยังไม่มีหลักฐานสำหรับรายการนี้` | `ตรวจข้อมูลต้นทางหรือส่งต่อให้ผู้ตรวจทาน` |
| Partial | `ข้อมูลบางส่วนยังไม่พร้อม` | `ตรวจรายการที่ทำเครื่องหมายไว้ก่อนดำเนินการต่อ` |
| Error | `โหลดข้อมูลไม่สำเร็จ` | `ลองอีกครั้ง หากยังพบปัญหาให้จดรหัสคำขอและแจ้งผู้ดูแลเดโม` |
| Stale | `ข้อมูลนี้มีเวอร์ชันใหม่กว่า` | `โหลดข้อมูลล่าสุดก่อนยืนยัน` |
| Abstained | `ระบบไม่เสนอคำแนะนำ` | `ข้อมูลไม่เพียงพอหรือความไม่แน่นอนสูง โปรดให้บุคลากรตรวจสอบโดยตรง` |
| Red flag | `พบสัญญาณที่ต้องประเมินเร่งด่วน` | `ตรวจ red flag และยืนยันการรับทราบก่อนดูข้อเสนอแนะอื่น` |
| Reviewed | `ตรวจทานโดยบุคลากรแล้ว` | show actor, role, localized timestamp and version |
| Busy/conflict | `มีผู้ใช้อื่นกำลังดำเนินการกับเคสนี้` | `โหลดสถานะล่าสุด หรือกลับไปเลือกเคสอื่น` |
| Mobile-limited | `ทำงานนี้ต่อบนแท็บเล็ตหรือเดสก์ท็อป` | `สถานะรอบเดโมและเคสจะยังคงอยู่` |

Destructive confirmation copy: title `ปฏิเสธข้อเสนอแนะนี้หรือไม่`; body `การปฏิเสธจะถูกบันทึกในประวัติและแก้ไขย้อนหลังไม่ได้ คุณยังเปิด review รอบใหม่ได้`; action `ปฏิเสธและบันทึกเหตุผล`; safe exit `กลับไปตรวจสอบ`.

No generic “Submit”, “Save”, “OK”, “Cancel” or bare “Retry” is permitted.

## Component contracts

- `AppShell`: role-labelled navigation, run badge, research disclaimer, user menu and sign-out; current location uses text + icon + active marker.
- `WorkQueue`: desktop table, tablet/mobile cards; filters never hide critical cases by default; zero/one/many tested.
- `CaseHeader`: case display ID, synthetic badge, stage, owner, last updated and next action; remains visible across case tabs.
- `CaseSectionNav`: Overview, Intake, Triage, Care, Medications, Timeline, Activity; unauthorized sections remain discoverable but explain role access instead of failing silently.
- `SafetyBanner`: critical before warning before clear; includes glyph, plain-language status and acknowledgement state.
- `Timeline`: chronological semantic list, localized time, actor/role, source and version; entries never rely on connector color.
- `EvidenceDrawer`: supporting evidence, source IDs and model metadata; never obscures critical alert or review bar.
- `SuggestionCard`: suggestion, uncertainty/abstention, supporting evidence and review status; cannot impersonate a diagnosis.
- `ReviewBar`: sticky on desktop/tablet, bottom sheet-safe on mobile; exactly one primary action and explicit edit/reject alternatives.
- `SearchablePicker`: typed search, keyboard navigation, no-results guidance and explicit clear selection label.

## UI Considerations

Applicable state considerations resolved: 14 covered, 3 backstop, 0 unresolved.

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | queue, case, timeline, evidence | ✅ covered | skeletons preserve header/actions and use fixed loading copy |
| empty | queue, timeline, evidence, medication sources | ✅ covered | documented empty copy and next action render in-panel |
| error | all remote panels | ✅ covered | inline error retains navigation and provides retry plus request ID guidance |
| populated | all core surfaces | ✅ covered | demo fixture exercises complete nurse-to-pharmacist journey |
| partial | case and medications | ✅ covered | missing sections are marked warning; available content remains usable |
| abstained | triage and care | ✅ covered | no suggestion CTA until explicit human review path is chosen |
| red-flag | header, safety banner, review bar | ✅ covered | red flag precedes suggestions and requires acknowledgement |
| reviewed | suggestions and activity | ✅ covered | immutable actor/time/version summary shown |
| stale | review forms | ✅ covered | version conflict blocks write and offers refresh |
| busy/conflict | queue and claim | ✅ covered | ownership conflict copy prevents overwrite |
| zero-one-many | queue, timeline, discrepancies | ✅ covered | dedicated empty, singular labels and plural list behavior |
| overflow | tables, badges, actions | ✅ covered | desktop tables become cards below 768px; action groups wrap without overlap |
| long-text | Thai transcript, evidence, alert | 🧪 backstop | visual tests use long unbroken ID and multi-paragraph Thai copy |
| keyboard | navigation, picker, dialog, review | ✅ covered | logical order, visible focus and Radix focus management |
| responsive | 1280×800, 768×1024, 390×844 | 🧪 backstop | Playwright screenshots and overflow assertions at all viewports |
| accessibility | all canonical journeys | 🧪 backstop | axe must report zero serious/critical violations |
| touch | all controls | ✅ covered | controls are at least 44×44px without introducing new spacing tokens |

## Responsive behavior

| Surface | Desktop ≥1024 | Tablet 768–1023 | Mobile <768 |
|---|---|---|---|
| Navigation | persistent sidebar | compact top bar + section tabs | compact header + sheet navigation |
| Queue | dense table + filters | responsive cards or compact table | priority cards; primary action full width |
| Case workspace | content + optional evidence drawer | full task flow; drawer overlay | summary, alerts, confirmation/handoff only |
| Review actions | sticky lower bar | sticky lower bar | safe bottom action region, no overlap with content |
| Editing | full transcript/vocabulary | full capability | complex editing deferred with preserved state |

## Synthetic API and data contract

Namespace `/api/demo/v1` contains journey/run/queue/case/timeline/task/handoff/medication-review resources. Every record includes `data_class="synthetic"`, actor/role, timestamp and version. No PUT/PATCH/DELETE. Writes are role-gated and append audit events. Presenter runs are isolated; creating a run never resets or deletes another run. Medication discrepancies are deterministic fixtures from the proposal and must not create treatment advice.

## Acceptance gates

- Desktop, tablet and mobile have no horizontal page overflow or text/action collision.
- All interactive targets are ≥44px, have visible focus and work keyboard-only.
- Within 5 seconds the case header exposes case, stage, owner, safety state and next action.
- Red flags precede suggestions; abstention has a human path; confirmation is mandatory and audited.
- The end-to-end synthetic journey can be repeated in isolated runs.
- Existing `make test`, web unit tests, typecheck and compatibility redirect tests pass.

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | button, badge, card, input, label, textarea, select, dialog, alert-dialog, tabs, tooltip, popover, command, scroll-area, separator, skeleton, table, sheet | PASS — official registry only |
| Third party | none | PASS — prohibited |

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS — specific Thai actions; empty/error/destructive solution paths documented
- [x] Dimension 2 Visuals: PASS — four-level hierarchy, explicit focal points and labelled icon rules
- [x] Dimension 3 Color: PASS — explicit 60/30/10 palette, reserved accent list and semantic destructive color
- [x] Dimension 4 Typography: PASS — four sizes, two weights and explicit line heights
- [x] Dimension 5 Spacing: PASS — only 4/8/16/24/32/48/64px, with control-size clarification
- [x] Dimension 6 Registry Safety: PASS — shadcn official/Radix only; no third-party blocks

**Approval:** approved 2026-09-28
