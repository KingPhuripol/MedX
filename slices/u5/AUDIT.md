# U5 UI/UX audit — MedX Clinical Front Door (research prototype, synthetic data)

Status: COMPLETE (UI/UX lead, 2026-09-29, HEAD 0b20999). Work packages: `slices/u5/SPEC.md`.

Screenshots: `artifacts/factory/u5/before/<page>-<width>.png` (gitignored, 84 captures). Per-page metrics (page height,
h1 and button y-positions, nav height, overflow, axe) are in `artifacts/factory/u5/before/metrics.json`.

## 1. Method

- Walked the live app at 1280×800, 768×1024 and 390×844 with Playwright as nurse1, physician1 and pharmacist1:
  login, empty queue, `/demo` → start run, queue, all 7 case sections, `/nurse/triage` + SYN-S4-002 review,
  `/nurse/intake` (short Thai session, then finish), `/physician/care` + SYNE-0011 T2 (red flags) + SYNE-0071 T1
  (abstains), `/pharmacist/reconcile` demo-01, nurse on `/physician/care` (403), `/403`, 404. Axe at 1280 and 768.
  The full nurse → physician → pharmacist hand-off was run in the case workspace.
- Backend: isolated sqlite DB in the scratchpad with the dev seed; web `next dev`, DEMO_MODE=1.
- Read every file in `web/app`, `web/components`, `web/lib`, the CSS, and every e2e/vitest selector.
- Rubric: 6-pillar (copy, visuals, colour, type, spacing, experience) from `gsd-ui-review`, plus hierarchy, density
  and state rules.

## 2. What already holds (keep)

- No horizontal overflow on any page at any viewport. Axe reports 0 serious/critical at 1280 and 768 on every page.
- Token-only colours, SCBXBeta2, one MedX wordmark, disclaimer first on every page.
- The safety logic is right: alerts come before suggestions in the DOM, confirm stays disabled until every alert
  (and incomplete screening) is acknowledged, abstention lists missing information, and a reviewer and time are
  recorded. The problem is **presentation and placement**, not logic.

## 3. Ranked findings

Height = full page height in px. "Confirm@y" = y-position of the primary review button.

| # | Pri | Page | Evidence | Impact |
|---|---|---|---|---|
| F1 | **P0** | `/login` (local, non-public) | `web/app/login/page.tsx:3,26` imports `PUBLIC_DEMO` from the `"use client"` module `DemoLogin.tsx`; on the server that import is a client-reference object (truthy), so the **role picker always renders** and the password form never does. Locally, `/api/auth/demo-login` → 404 → "Sign-in failed" (`login-1280.png`, `login-rolepicker-error-1280.png`). Vitest misses it because jsdom ignores `"use client"`. | Nobody can sign in on `make dev` unless the backend also runs PUBLIC_DEMO=1. Every e2e `login()` helper fills the password form, so the whole e2e suite fails locally. |
| F2 | **P0** | `/physician/care/:id` | Height 5,424 at 1280, 6,321 at 768, 10,553 at 390. Confirm@2,523 (1280) and @5,700 (390). The edit form lists the whole vocabulary as about 45 checkboxes (`CareReview.tsx:29-60,255-277`). Evidence refs are inline on every line. `physician-care-review-redflag-1280.png`. | The physician scrolls 3 screens to reach Confirm and loses sight of the alerts they acknowledged. Edit means hunting in a 2,500-px checkbox wall. |
| F3 | **P0** | `/nurse/triage/:id` | Screening scope + 8 raw vital lines render **before** the red-flag alerts (`TriageReview.tsx:59`, alerts start at y≈700). Acknowledge checkboxes are 13 px with the label on the next line. Confirm@1,727 (1280), @3,197 (390). Three stacked forms with three identical disabled blue buttons. `nurse-triage-review-redflag-1280.png`. | Red flags are not the first thing the nurse sees. There is no visible "what unblocks me", and the primary action is below the fold. |
| F4 | **P0** | Shell at 768 and 390 | `.clinical-shell` is a one-column grid with `min-height` and auto rows, so the free height is shared between the nav row and the main row (`globals.css:136-140`, `:634-650`). Nav height: 450 px (empty queue, 768), 305–388 (768), 296 (390). h1 at y=533 (768 empty queue), 435 (physician queue 768), 442–498 (390). At 390, `nav-links {order:3}` puts **sign-out above the navigation** (`nurse-case-triage-390.png`). | On tablets and phones the first screen is mostly empty nav. The page title and primary action start below the fold. |
| F5 | **P1** | Domain pages: triage list, triage review, intake, care list, care review, reconcile | Role layouts wrap every page in one `.card.domain-panel` (`app/nurse/layout.tsx:10`, physician, pharmacist). Inside it, raw `<h1>/<p>/<ul>`, a global `button{margin:4px}`, and English-only copy. There is no page header, section or card hierarchy (`nurse-triage-list-1280.png`). | The pages read as one long document. The new MedX shell stops at the sidebar. |
| F6 | **P1** | `/nurse/triage` | A 40-row `<ul>` with inline "Assess" buttons that follow ragged text; no columns, search or row-busy state. 2,409 px at 1280, 3,920 at 390. The "Back to nurse home" link goes to a route that only redirects. | Hard to scan or find a case. The button moves with the complaint length. |
| F7 | **P1** | `/physician/care` | 40 cases × 2 buttons labelled with raw ISO timestamps, e.g. `T1 (2030-05-27T09:02:32+07:00)`. 2,433 px at 1280, 4,666 at 768, 7,672 at 390 (`physician-care-list-1280.png`). | Too dense, with nothing to scan by. The timestamps crowd out the case ID. |
| F8 | **P1** | `/pharmacist/reconcile` | 4,985 px at 1280. A scope essay sits above the run form (Run check @783). Confirm **and** Dismiss are both blue primary buttons (`PharmaReconcile.tsx:171,190`). Each issue has a 6-column table. The page stops at 60rem with empty space to the right (`pharmacist-reconcile-run-1280.png`). | Dismiss has the same weight as Confirm, so an accidental dismissal is easy. The run form is not the focal point. |
| F9 | **P1** | `/nurse/intake` | Single column: controls → facts table (centred headers, raw `KNOWN`, raw ISO `2026-09-29T06:20:34.630000Z`) → missing → transcript → full-width Finish. The banners reuse the `.disclaimer` class (`VoiceIntake.tsx:180,191`). `nurse-intake-session-1280.png`. | The nurse cannot see the conversation and the extracted facts side by side. Missing fields do not stand out. |
| F10 | **P1** | `/app/cases/:id/*` | The red-flag banner with its **acknowledge checkbox** shows on every tab for every role, including the pharmacist on Medications, where it gates nothing (`CaseWorkspace.tsx:216-231`). The acknowledgement resets on each tab switch because the page remounts. The Intake tab embeds VoiceIntake with a **second h1** (`metrics.json`: nh1=2 at 1280/768). Overview has no primary action for the role's task. Tabs do not mark which one is "my task". | Mixed signals about what must be acknowledged, a broken heading outline, and no "go to my task" path. |
| F11 | **P1** | `/app/queue` | Task label and next action repeat the same text (`WorkQueue.tsx:139-141`). Both a warning row and a critical row use the same triangle icon. There are no links to role tools, so without a demo run the queue is a dead end for the triage, care and reconcile work (`nurse-queue-empty-1280.png`). | The queue does not work as a start page for real work. |
| F12 | **P2** | `/403`, 404, Forbidden-in-shell | A slide-deck `PageFrame` (eyebrow/claim/next-step) in English only. The only way out is "Go to sign in", even when signed in (`403-1280.png`, `nurse-on-physician-page-403-1280.png`). | The dead end sends a signed-in user to the login page. |
| F13 | **P2** | Loading | Two loaders in sequence: AppShell "กำลังตรวจสอบสิทธิ์…", then RoleGuard "Checking access…", then page "Loading cases…". Mixed languages and no skeleton (`RoleGuard.tsx:38`, `TriageCaseList.tsx:59`). | The layout jumps and the copy switches language. |
| F14 | **P2** | Type and spacing | `pharma.css` uses rem sizes (0.8–1.1rem) and 17px selects. Inline `style={{…}}` spacing appears in WorkQueue and CaseWorkspace. Nav labels mix Thai and English and wrap to 2 lines in 240px ("รับข้อมูลด้วยเสียง · Voice intake"). | Breaks the 4-size scale and spacing tokens in UI-SPEC. |
| F15 | **P2** | Disclaimer | 59 px desktop, 122 px at 390 (2 paragraphs, centred). Required, but the padding could be tighter. | Takes 15% of the phone viewport. It must stay visible, first, and ≥14px, so only compact it. |

## 4. Role walks (summary)

### Nurse
Queue (OK at 1280, pushed down at 768/390) → case workspace (header, red-flag banner, tabs, review bar all reasonable;
the sticky review bar works at 1280/768) → triage list (F6) → triage review (F3) → intake (F9). The hand-off to the
physician works. Main pain: the real triage and intake pages look nothing like the case workspace.

### Physician
The queue shows 1 task after the nurse hand-off. The case care tab is fine. The care list (F7) and care review (F2)
are the worst screens in the product. The abstain case (SYNE-0071 T1) correctly shows no Confirm and lists the missing
information, but that list sits at y≈1,900 below the whole screening block (4,272 px page).

### Pharmacist
Queue → case Medications works, but shows an unrelated red-flag acknowledgement (F10). Reconcile (F8): the check works
and the decisions record, but the hierarchy is flat and Dismiss looks like the primary action.

## 5. Target layout per page (routes unchanged)

```text
SHELL ≥1024:  [disclaimer]
              [nav 240 | main: PageHeader → content (max 1180) ]
SHELL <1024:  [disclaimer]
              [topbar: MedX · role chip ............ user · ออกจากระบบ]   ≤ 64px
              [nav tabs row, one line, horizontal scroll]                 ≤ 56px
              [main]
```

- **Login**: ≥768 cover | form (as now). <768: compact brand band ≤140px, then the form. The submit button is above
  the fold at 390. Password form locally; role picker only when NEXT_PUBLIC_PUBLIC_DEMO=1 (F1).
- **Queue**: PageHeader(role title, run chip, action "เริ่มรอบเดโมใหม่" secondary) → DataTable of tasks (priority chip
  | case | task + next step | owner | [รับเคสนี้] [เปิดเคส]) → "เครื่องมือของบทบาท" cards (links to /nurse/triage,
  /nurse/intake | /physician/care | /pharmacist/reconcile). Empty (no run): EmptyState with CTA to /demo **plus** the
  role tool cards.
- **Demo**: PageHeader + journey card (as now, fine).
- **Case workspace**: CaseHeader card → SafetyBanner (acknowledge checkbox only on the tab it gates: nurse on Triage,
  physician on Care) → tabs (own task tab marked "งานของคุณ") → section content in 2 columns (work | evidence) →
  sticky ActionBar. Overview gets a primary "ไปที่งานของคุณ" link. Intake tab: VoiceIntake with h2.
- **Triage list**: PageHeader("Triage cases", count) → filter input → DataTable (case | chief complaint | evidence as-of
  | Assess). Cards <768.
- **Triage review**:
  ```text
  PageHeader: Triage review — SYN-S4-002 · "Suggestion for nurse review" · as-of · rules
  [CRITICAL] Red-flag alerts (n) — each alert: name TH/EN, message, evidence, [☐ I have seen alert X] (44px row)
  [WARNING/INFO] Screening: banner or count; not-evaluated line; <details> readings
  [Department suggestion: ranked list + uncertainty chip]   (2-col ≥1024 with missing info)
  [Review: Confirm | Edit | Reject as 3 equal cards ≥1024, stacked <1024]
  ActionBar (sticky): "Acknowledge k/n alerts" status + Confirm department (form= attribute)
  ```
- **Intake**: ≥1024 two columns — left: agent question card, chat-style transcript, add-turn row (speaker | text | Add
  turn); right: facts DataTable (localised time, state chip), missing-fields warning chips, Finish intake. <1024 stacked.
- **Care list**: PageHeader → filter → DataTable (case | T1 button "T1 · 13 พ.ค. 11:07" | T2 button). Keep the aria-labels.
- **Care review**: PageHeader (case at T, output label, provenance quiet) → red-flag section (alerts critical, then
  screening) → suggestion in 2 columns (case summary | next information + pathway options), evidence refs muted →
  missing information (warning chips) → review panel (acknowledgements, Confirm, Edit with a **filterable, scrollable
  picker** max 320px per vocabulary, Reject) → sticky ActionBar with Confirm.
- **Reconcile**: PageHeader → run form card (patient | mode | Run check inline) → status line → 2 columns ≥1024:
  issues (main) | scope + notices (aside) → medication lists as read (full width, table scroll-wrapper).
- **403/404**: Centred EmptyState card: h1 "403 — …" / "404 — …", Thai explanation, primary "กลับไปคิวงาน" and
  secondary "เข้าสู่ระบบด้วยบัญชีอื่น" (403) or "ไปหน้าเข้าสู่ระบบ" (404).

## 6. Shared layout contract

This contract is binding for WP-A, WP-B and WP-C. WP-A owns the primitives. B and C import them from
`@/components/ui/*`. If a primitive is missing on their branch, they create a minimal copy at the **same path, name
and props** (WP-A's version wins at merge).

### 6.1 Tokens, type, spacing
- Colours: only `var(--token)` from `web/app/theme.css`. B and C may use only tokens that exist at HEAD 0b20999:
  background, foreground, card, nav, border, muted, muted-foreground, primary(-hover/-soft/-deep/-bright),
  critical(-fg/-border/-bg), warning(-fg/-border/-bg), success(-bg), shadow-*. No hex, rgb(a), hsl, named colours or
  color-mix in any file except theme.css.
- Type: 14 / 16 / 20 / 28 px only; weights 400 / 700; line-height 1.5 (body) and 1.3 (headings). Metadata 14px muted.
- Spacing: 4, 8, 16, 24, 32, 48, 64 px only. Radius 8 (controls) and 12 (cards). Controls ≥44px tall.
- Exactly **one h1 per page**, rendered by `PageHeader` (or CaseHeader in the case workspace). Section titles are h2;
  items inside sections are h3.

### 6.2 Primitives (web/components/ui/)
| File | Export & props | Renders / classes |
|---|---|---|
| `PageHeader.tsx` | `PageHeader({ title: ReactNode; titleId?: string; subtitle?: ReactNode; meta?: ReactNode; actions?: ReactNode; testId?: string })` | `<header class="ui-page-header">` with `<h1 id={titleId}>`, subtitle `<p class="muted">`, meta row (chips), and actions right-aligned (≥768), wrapping under the title below 768. |
| `Section.tsx` | `Section({ title?: ReactNode; titleId?: string; actions?: ReactNode; tone?: "default"\|"critical"\|"warning"; children } & HTMLAttributes<HTMLElement>)`, passing through `data-testid` and `role` | `<section class="ui-section ui-section--{tone}" aria-labelledby={titleId}>` card: 24px padding (16 below 768), 12px radius, `--card` bg, `--border` (critical: `--critical-border` + `--critical-bg`, 4px left rule `--critical`; warning likewise). Title is an h2 at 20px. |
| `StatusChip.tsx` | `StatusChip({ tone: "critical"\|"warning"\|"success"\|"info"\|"neutral"; icon?: ReactNode; children })` | `<span class="ui-chip ui-chip--{tone}">`, 14px/700, pill. critical `--critical-fg` on `--critical-bg` with border `--critical-border`; warning `--warning-fg`/`--warning-bg`/`--warning-border`; success `--success`/`--success-bg`/`--success`; info `--primary`/`--nav`/`--border`; neutral `--foreground`/`--muted`/`--border`. **Never** `role="status"`. Text is always present (never colour only). |
| `Notice.tsx` | `Notice({ tone: "critical"\|"warning"\|"info"\|"success"; title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children } & HTMLAttributes<HTMLDivElement>)`, passing through `role` and `data-testid` | `<div class="ui-notice ui-notice--{tone}">`: bordered block, 16/24 padding, icon column, and the tone tokens listed above. No default `role`: callers set `role="alert"` where the current code has it. |
| `EmptyState.tsx` | `EmptyState({ title: ReactNode; description?: ReactNode; action?: ReactNode; icon?: ReactNode; headingLevel?: 1\|2 })` | `.ui-empty`, a centred dashed-border panel (replaces `.state-panel`). `headingLevel=1` for 403/404. |
| `LoadingState.tsx` | `LoadingState({ label?: string; rows?: number })` | `rows` skeleton bars (default 2) plus `<p aria-live="polite">` label (default `กำลังโหลดข้อมูล…`). **Not** `role="status"`. |
| `DataTable.tsx` | `DataTable<T>({ columns: { key: string; header: ReactNode; render: (row: T) => ReactNode; className?: string }[]; rows: T[]; rowKey: (row: T) => string; caption?: ReactNode; testId?: string; empty?: ReactNode })` | `<table class="ui-table" data-testid={testId}>`. Each `<td data-label={header text}>`. ≥768: table with 14px muted `th` and 16px rows (8/16 cell padding). <768: rows become cards (thead hidden; td shows `data-label` via `::before`). `empty` is rendered when rows=[]. |
| `ActionBar.tsx` | `ActionBar({ summary?: ReactNode; children: ReactNode })` | `.ui-action-bar` (replaces `.review-bar`): sticky `bottom:16px` at ≥768, static full-width stacked buttons below 768. `summary` is on the left, buttons on the right. |
| `Field.tsx` | `Field({ label: ReactNode; htmlFor: string; hint?: ReactNode; error?: ReactNode; children })` | `.ui-field`: `<label htmlFor>` 14/700, the control, hint `<small id={htmlFor+"-hint"}>`, error `<p role="alert" class="ui-field-error">`. Child `input, select, textarea` get 44px min-height, 8/16 padding, `--border`, radius 8, full width. |
| `button.tsx` (exists) | `Button` variants primary / secondary / danger / ghost | unchanged API. **Rule:** at most one primary button per surface. Dismiss, Reject and Edit are never primary. |

Primitive CSS lives in `web/app/globals.css` under the `ui-` prefix (WP-A). B and C's local copies put their CSS in a
co-located `web/components/ui/<Name>.module.css` only if WP-A's classes are missing on their branch; those files
are dropped at merge.

### 6.3 Page patterns
- Page = `<div className="page-stack">` → `PageHeader` → `Section`s. Role layouts (`app/{nurse,physician,pharmacist}/layout.tsx`)
  render `<AppShell>{children}</AppShell>` only (no `.card.domain-panel` wrapper).
- Case lists = `DataTable` with a leading severity or priority column where one exists, a native
  `<input type="search">` filter in a `Field` (client-side, instant), a count in the PageHeader meta, and a row-level
  busy label on the pressed button (other rows stay enabled only where the API allows it; otherwise all disabled, as
  now).
- Review pages, top to bottom: PageHeader → **critical Notice/Section for red flags** → screening → suggestion →
  missing information → review forms → `ActionBar` with the primary action. The `form="<id>"` attribute lets the
  ActionBar button submit a form elsewhere on the page.
- Severity: red flags use `tone="critical"` plus a Lucide `AlertOctagon` and the text "Red flag"/"พบสัญญาณอันตราย". Nothing
  else on a page uses `critical` except errors and destructive buttons. Incomplete or not-performed screening, missing
  information, and hand-off/allergy banners use `warning`. Reviewed/confirmed use `success`. Suggestions are
  `info`/`neutral`, never critical.
- States: loading → `LoadingState` (keeps the header visible); error → `Notice tone="critical" role="alert"` with
  cause and next step; empty → `EmptyState` with a next step; partial/abstained → `Notice tone="warning"` listing
  what is missing.
- Timestamps shown to users use `formatThaiTime` (`web/lib/demo.ts`). The raw ISO string stays only where a test
  asserts it, inside `<time dateTime>` or in muted metadata.
- Responsive: work at 1280/768/390 with zero horizontal page overflow. Wide tables sit inside
  `<div class="ui-table-scroll">` (overflow-x:auto) when they cannot collapse to cards. Two-column grids collapse
  below 1024.
- Focus and keyboard: keep the global `:focus-visible` ring. Every checkbox or radio sits in a `<label>` row at least
  44px tall. The DOM order equals the visual order (no CSS `order` for primary content). Sticky bars must not cover
  a focused element: add `scroll-padding-bottom: 96px` on `html` (WP-A).
