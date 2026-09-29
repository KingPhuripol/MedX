# U5 — MedX web UI made usable for clinical work (layout, hierarchy, navigation, density, states)

Owner request (2026-09-29): the system works, but the layout, placement and organisation of the web UI are "very, very
bad". Keep the existing routes and information architecture. Make it usable for real nurse, physician and pharmacist
work. Evidence and the shared layout contract: `slices/u5/AUDIT.md` (read §3 findings, §5 target layouts and **§6
contract** before starting). Before-screenshots: `artifacts/factory/u5/before/`.

Roles: planner/UI lead = this spec. Builders = three Sonnet workers (WP-A, WP-B, WP-C) in parallel, each on its own
branch/worktree (`factory/u5-a`, `factory/u5-b`, `factory/u5-c`). The lead reviews. Scope is about 60–75 minutes per
WP. **Do the numbered items in order.** The top 3 alone must give a big visible win. Stretch items only after
acceptance passes.

## Global rules (all WPs)

1. **Routes unchanged.** No new routes, no redirects changed, no backend changes. `web/lib/*` API calls unchanged.
2. **Colours are token-only** (`var(--x)` from `web/app/theme.css`). No hex/rgb/hsl/named colours or color-mix
   anywhere else. Only WP-A edits `web/app/theme.css` and `web/app/globals.css`. B and C use only tokens present at
   HEAD 0b20999 (list in AUDIT §6.1). `web/e2e/theme.spec.ts` and `web/tests/theme.test.ts` enforce this.
3. **Type and spacing scale:** 14/16/20/28 px, weights 400/700; spacing 4/8/16/24/32/48/64; radius 8/12; controls
   ≥44px. B and C styles go in co-located `*.module.css`. The exception is `pharma.css`, which keeps its **global**
   class names because e2e selects `ol.issue-list`, `.issue`, `.sources`.
4. **Safety invariants (never regress):** research disclaimer first on every page. Red flags and screening render
   before any suggestion (DOM order and visual order). Confirm stays disabled until every red flag is
   acknowledged; on **care review** also the incomplete/not-performed screening banner (existing behaviour). Triage
   review has no screening acknowledgement in its API or UI today — U5 must not add one (review note 2026-09-29;
   question logged for clinical-safety-reviewer). Abstention shows no Confirm and lists missing information.
   Missing is never shown as negative. RBAC 403 (`data-testid="forbidden"`, h1 contains "403"). Human confirmation
   happens before anything is recorded as care-facing. Never claim diagnosis or treatment: keep "suggestion for review" labels.
5. **One h1 per page.** Do not add `role="status"` elements: several tests use `getByRole("status")` in strict mode.
   Do not add new `h3` on the reconcile page (a unit test expects a single h3 in one fixture).
6. **Keep every load-bearing selector** listed in your WP: test ids, label texts, button/link accessible names,
   heading texts, `id`s. If you must change one, update the spec/test in the same change so it asserts the **same
   behaviour**, and say so in your report.
7. **Accessibility:** axe 0 serious/critical at 1280×800 and 768×1024 on every page you touch. Visible focus ring.
   Keyboard order equals visual order. Every checkbox or radio sits in a clickable label row ≥44px.
8. **No horizontal page overflow** at 1280, 768 and 390 (`scrollWidth - clientWidth <= 0`). Wide tables go in a
   scroll wrapper.
9. **Verification before reporting:** `cd web && npx vitest run && npx tsc --noEmit`; `make test` green; run your
   WP's e2e specs on your own ports (below). The only known e2e failure is `voice-intake.spec.ts` "nurse runs a
   synthetic Thai intake…" (evidence 2 vs 7, slices/int2/SPEC.md:130). Save after-screenshots of every page you own at
   1280×800, 768×1024 and 390×844 to `artifacts/factory/u5/<a|b|c>/after/<page>-<width>.png`, with the same names as
   `before/`.
10. Do not commit secrets, do not read `.env`, and do not touch other WPs' files. Commit on your branch only.

### Running servers (all WPs)

Login is fixed on main (F1, done by the orchestrator before dispatch): `PUBLIC_DEMO` now lives in `web/lib/publicDemo.ts`,
so the password form renders locally and all e2e `login()` helpers work on every WP branch.
To start servers without `.env` (which may set demo flags), from the repo root:

```bash
S=<your scratch dir>; export PYTHONPATH=$PWD/backend:$PWD DATABASE_URL=sqlite:///$S/u5.db DEMO_MODE=1
.venv/bin/python -m app.seed && .venv/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port $API_PORT &
cd web && DEMO_MODE=1 API_ORIGIN=http://127.0.0.1:$API_PORT npx next dev -H 127.0.0.1 -p $WEB_PORT &
# e2e reuses running servers: WEB_PORT=$WEB_PORT API_PORT=$API_PORT npx playwright test e2e/<spec>
```

Ports: WP-A 8161/3161, WP-B 8162/3162, WP-C 8163/3163. Stop your servers when done.

---

## WP-A — Shell, foundation, login, queue, demo, 403/404

**Files (exclusive):** `web/app/globals.css`, `web/app/theme.css`, `web/app/layout.tsx`, `web/app/login/page.tsx`,
`web/app/not-found.tsx`, `web/app/403/page.tsx`, `web/app/app/layout.tsx`, `web/app/app/queue/page.tsx`,
`web/app/demo/page.tsx`, `web/app/page.tsx`, `web/components/clinical/AppShell.tsx`,
`web/components/clinical/WorkQueue.tsx`, `web/components/clinical/DemoLauncher.tsx`, `web/components/ui/*` (all
primitives), `web/components/LoginForm.tsx`, `web/components/DemoLogin.tsx`, `web/components/Forbidden.tsx`,
`web/components/RoleGuard.tsx`, `web/components/PageFrame.tsx` (may delete), `web/components/Disclaimer.tsx`,
`web/components/Wordmark.tsx`, `web/lib/demo.ts`, `web/lib/copy.ts`, `web/lib/utils.ts`, tests/specs for these
(`web/tests/{login,demo-login,layout,role-guard,theme,wordmark}.test.tsx`,
`web/e2e/{roles,disclaimer,theme,a11y,health,public-demo,clinical-operations,helpers}.ts` — for
clinical-operations, only the queue/shell parts).

**Changes, in priority order:**

1. **A1 DONE on main** (F1 login fix, `web/lib/publicDemo.ts`). Optional: add an e2e assertion in `roles.spec.ts` that `#username` is visible.
2. **A2 Shell responsive fix (F4).** Below 1024 use `grid-template-rows: auto 1fr` (root cause of the 200–450px nav).
   Top bar row: wordmark + role chip on the left, username + `ออกจากระบบ` on the right. Second row: nav links on one
   line with horizontal scroll inside the bar (no page overflow). Sign-out must never come before the nav links in
   the visual order. Shorten nav labels to Thai-first single lines, keeping the English in the accessible name where
   tests need it: the pharmacist link name must still contain "Medication reconciliation"; the queue link must
   contain "คิวงาน". At ≥1024 keep the 240px sidebar, with the sidebar background full height.
3. **A3 Primitives + global CSS.** Implement every primitive in AUDIT §6.2 with the exact names and props, and their
   `ui-*` CSS in `globals.css`. Add `html { scroll-padding-bottom: 96px }`. Keep the old classes (`.domain-panel`,
   `.state-panel`, `.review-bar`, `.case-*`, `.queue-table`, `.card`, `.badge`, …): B and C still use them on
   their branches. Mark them `/* legacy — remove after U5 merge */`.
4. **A4 Queue (F11).** Use PageHeader + DataTable. Priority column uses StatusChip (critical "เร่งด่วน" with
   AlertOctagon; warning "ต้องตรวจทาน" with Clock). Show `next_action` only when it differs from `label`. Owner
   column. Actions: `รับเคสนี้` secondary + `เปิดเคส` primary; below 768 the card has a full-width `เปิดเคส`. **Keep
   server order** (e2e clicks `เปิดเคส` `.nth(1)` = triage task). Add a "เครื่องมือของบทบาท" Section with link cards to
   the role's work pages (nurse: /nurse/triage, /nurse/intake; physician: /physician/care; pharmacist:
   /pharmacist/reconcile). Show it on both the empty and populated queue. The no-run EmptyState keeps its
   `/demo` CTA.
5. **A5 Loading and guard states (F13).** AppShell loading keeps the shell frame (skeleton nav + LoadingState).
   RoleGuard uses LoadingState `กำลังตรวจสอบสิทธิ์…` and an error Notice (Thai + English short line, `role="alert"`).
6. **A6 403/404 (F12).** Replace PageFrame with EmptyState (`headingLevel={1}`). Forbidden keeps
   `data-testid="forbidden"` and h1 `403 — ไม่มีสิทธิ์เข้าถึงหน้านี้ (Not your role's page)`. Actions: `กลับไปคิวงาน`
   (primary, /app/queue) and `เข้าสู่ระบบด้วยบัญชีอื่น` (/login). 404 h1 `404 — ไม่พบหน้านี้ (Page not found)` with the same
   actions. Delete `PageFrame.tsx` and its CSS if nothing else uses it.
7. **A7 Login at 390.** The cover panel becomes a compact band ≤140px below 768. Password fields and
   `เข้าสู่ระบบเดโม` are fully visible without scrolling at 390×844. The DemoLogin buttons use `Button` (secondary,
   full width) and Thai-first copy, keeping the button names `Nurse · พยาบาล` etc.
8. **A8 Demo page.** Use PageHeader + Section. When demo mode is off, show EmptyState. No other change.

**Load-bearing selectors (keep):** labels `ชื่อผู้ใช้สังเคราะห์`, `รหัสผ่าน`; button `เข้าสู่ระบบเดโม`;
`#login-error[role=alert]` with the text `ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง` and critical tokens; role-picker buttons
`Nurse · พยาบาล` / `Physician · แพทย์` / `Pharmacist · เภสัชกร`; headings `คิวงานตามบทบาท` (before the user loads) and
`คิวรับเข้าและคัดกรอง` / `เคสที่รอตรวจโดยแพทย์` / `คิวทบทวนข้อมูลยา`; the text `รอบ <8 hex>` visible on the queue; links
`/เปิดเคส/` in server order; button `/เริ่มรอบเดโมใหม่/`; button `ออกจากระบบ`; `getByRole("navigation")` containing
link `/คิวงาน/`; nav link name containing `Medication reconciliation`; classes `.nav-link`, `a.ui-button`, `.wordmark`,
`.wordmark-x` (≥24px, 700); one visible `role=img name=MedX`; `data-testid` `research-disclaimer` (first body child,
`role=note`, warning tokens, 2 `<p>` ≥14px), `wordmark`, `forbidden`; h1 contains `403` / `404`; `<main>` count 1;
titles use the MedX template.

**Acceptance (measured with the walk script or e2e, 3 viewports):**
- A-1 Password login works on local dev (`#username` visible when NEXT_PUBLIC_PUBLIC_DEMO≠1). The role picker is shown only when it is `1`.
- A-2 On `/app/queue` at 768×1024: nav/top-bar block height ≤128px and h1 top ≤260px (before: 305–450 / 388–533). At 390×844: h1 top ≤340px (before 442–498). The sign-out button's y is ≥ the last nav link's y, or it sits in the top bar row.
- A-3 Populated queue at 1280 and 768: the first `เปิดเคส` is fully inside the first viewport. At 390 each task renders as a card with a full-width `เปิดเคส`.
- A-4 The queue shows role tool links for each role (nurse 2, physician 1, pharmacist 1), with and without a run.
- A-5 403 and 404 offer `กลับไปคิวงาน`. No English-only loading or error copy remains in the shell or RoleGuard.
- A-6 Primitives exist at the exact paths and props in AUDIT §6.2, each with a minimal vitest render test (one file, `web/tests/ui-primitives.test.tsx`).
- A-7 e2e green on 8161/3161: roles, disclaimer, theme, a11y, health, clinical-operations. vitest + tsc + `make test` green.

**Stretch:** queue summary counts (เร่งด่วน / รอผู้รับผิดชอบ / ทั้งหมด) in PageHeader meta; mobile nav as a sheet;
compact the disclaimer at 390 (keep both paragraphs, ≥14px, first, fully visible).

---

## WP-B — Nurse pages and the case workspace

**Files (exclusive):** `web/components/clinical/CaseWorkspace.tsx` (+ `CaseWorkspace.module.css`),
`web/app/app/cases/**`, `web/components/voice/VoiceIntake.tsx` (+ module css), `web/components/TriageCaseList.tsx`,
`web/components/TriageReview.tsx`, `web/components/TriageReviewLoader.tsx` (+ module css), `web/app/nurse/**`,
`web/lib/triage.ts`, `web/lib/voice.ts` (display helpers only), tests `web/tests/{triage-review,TriageReview.screening,voice-intake,voice-display}.test.*`,
`web/e2e/{triage,voice-intake}.spec.ts`, and the case-workspace parts of `clinical-operations.spec.ts`. Uses
`ScreeningBlock` read-only (WP-C owns it).

**Changes, in priority order:**

1. **B1 Triage review (F3).** Wrap in `page-stack` with PageHeader (h1 `Triage review — {case_ref}`; subtitle
   `Suggestion for nurse review.` + localised as-of + rules version as muted meta). Then **red-flag alerts first**:
   `alerts-section` as `Section tone="critical"` (keep `role="alert"` when alerts exist). Each alert is a card
   (name TH + EN, message EN + TH, evidence muted) with its acknowledge row directly below as a full-width
   `<label>` row ≥44px (checkbox 20px + text), keeping ids `ack-{rule_id}` and label text `I have seen alert {id}`.
   `not-evaluable` stays inside. Next comes `<ScreeningBlock>` (moved **after** alerts, before the department).
   Then the department suggestion (`department-section`): ranked list with the score as text, uncertainty as a
   StatusChip, and missing information as a warning Notice when abstained. Review area: three equal cards
   (Confirm / Edit / Reject) in a 3-column grid at ≥1024, stacked below. Reject uses `Button variant="danger"`,
   Edit secondary. Add an `ActionBar` (sticky) with the summary `รับทราบ red flag แล้ว k/n` and the Confirm department
   button bound via `form="confirm-form"`. Keep exactly **one** element named "Confirm department": move it, do not
   duplicate it. The review result is a success Notice (keep `role="status"` + `data-testid="review-result"`).
2. **B2 Triage list (F6).** PageHeader (`Triage cases`, count chip). Remove "Back to nurse home". A search `Field`
   filters by ref or complaint. `DataTable testId="case-list"` with columns: case ref | chief complaint (Thai wraps,
   "not recorded" muted) | evidence as of (formatThaiTime) | action `Assess` (Button secondary, `aria-label="Assess
   {ref}"`, pressed row shows `กำลังประเมิน…`). Error → Notice, loading → LoadingState. Cards below 768.
3. **B3 Case workspace (F10).** (a) The acknowledge checkbox in the safety banner renders only when the current tab
   has a review it gates (nurse on `triage`, physician on `care`). Elsewhere the banner shows the alert and the chip
   `ต้องให้บุคลากรประเมินโดยตรง` without a checkbox. The label text must still match `/รับทราบ red flag/` where it renders.
   (b) Tabs: add `aria-current="page"` on the active tab. Mark the role's own task tab with a StatusChip `งานของคุณ`
   (nurse→triage, physician→care, pharmacist→medications). Keep class `case-tab` and the link names (`กิจกรรม`, etc.).
   (c) Overview: primary link `ไปที่งานของคุณ →` to the role's tab. (d) The Intake tab renders VoiceIntake with a new
   prop `embedded` (h2 instead of h1) → exactly one h1. (e) Replace inline `style={{…}}` with module CSS. Replace
   `.review-bar` with `ActionBar`, `.state-panel` with EmptyState, and evidence badges with a muted list.
4. **B4 Voice intake (F9).** PageHeader (`Voice intake (Thai, text first)`). ≥1024 two columns. Left: the agent
   question card (the existing `role=status` p stays the only status), a chat-style transcript `<ol>` (speaker chip +
   text), and the add-turn form on one row (Speaker select | Turn text | Add turn). Right: the facts DataTable-style
   table (keep `<table data-testid="facts-table">`, `tr[data-testid=fact-row][data-field]`, `a[data-testid=source-link]`
   href `#turn-…`, `<time dateTime>` showing a localised value), a `missing-list` as warning chips/list, and `Finish
   intake` (primary). Handoff and allergy banners become Notice warning (keep test ids and `role="alert"`; drop the
   `.disclaimer` class). Keep focus moves (Turn text after start; summary heading after finish).
5. **B5 Nurse layout.** `app/nurse/layout.tsx` renders `<AppShell>{children}</AppShell>` only.

**Load-bearing selectors (keep):** triage: button `Assess {ref}`, h1 contains the ref and `Triage cases` / `Triage
review`, `alerts-section` (role=alert, above `department-section` in the DOM and on screen), `department-ranking`,
`missing-information`, `not-evaluable`, `alerts-none`, label `I have seen alert {id}`, buttons `Confirm department`
/ `Save edited department` / `Reject suggestion`, labels `Choose another department`, `Reason for the change`,
`Reason for rejecting`, `review-result`, text `Suggestion for nurse review`, `case-list` (visible). Voice: labels
`Synthetic patient ref`, `Speaker` (combobox), `Turn text`; buttons `Start intake`, `Add turn`, `Finish intake`; the
single `role=status` agent question; test ids `agent-question`, `handoff-banner`, `allergy-conflict-banner`,
`fact-row`, `source-link`, `missing-list`, `transcript`, `facts-table`, `intake-summary`; link `turn N`; h1 contains
`Voice intake`. Case workspace: heading `ทบทวนข้อเสนอการคัดกรอง`, exact text `พบสัญญาณที่ต้องประเมินเร่งด่วน`, label
`/รับทราบ red flag/`, buttons `/ยืนยันข้อเสนอแนะ/`, `/ส่งต่อให้แพทย์/`, `/ส่งต่อให้เภสัชกร/`, text
`ตรวจทานโดยบุคลากรแล้ว`, pharmacist heading `Medication reconciliation` on the medications tab, exact text `ตรวจทานแล้ว`
appearing once on the medications tab after confirm, link `กิจกรรม`, timeline texts, `.case-tab` ≥44px.

**Acceptance:**
- B-1 Triage review SYN-S4-002 at 1280×800: `alerts-section` top ≤400px (before ≈700). `Confirm department` is inside the viewport on load at 1280 and 768 (sticky ActionBar). Page height at 1280 ≤1,800 (before 2,267). Each acknowledge row ≥44px tall with the checkbox and label on one line.
- B-2 Triage list: a column table at ≥768 and cards at 390. Typing `S4-00` in the filter leaves 9 rows. No "Back to nurse home". Pressing Assess shows the row busy label.
- B-3 Case workspace: exactly 1 h1 on every section at every viewport. No acknowledge checkbox on overview/medications/timeline/activity, or for the pharmacist. The own-task tab is marked. Overview has `ไปที่งานของคุณ`. The full nurse→physician→pharmacist journey e2e passes.
- B-4 Intake session at 1280 after 2 turns: the agent question, the Turn text input and the facts table are all inside the first viewport (y <800).
- B-5 e2e green on 8162/3162: triage, voice-intake (except the known failure), clinical-operations, a11y and disclaimer for nurse pages, theme. vitest + tsc + `make test` green.

**Stretch:** a compact sticky case header on scroll; a Timeline filter (clinical vs audit); a "คัดลอกรหัสคำขอ" affordance on errors.

---

## WP-C — Physician and pharmacist pages

**Files (exclusive):** `web/components/CareCaseList.tsx`, `web/components/CareReview.tsx`,
`web/components/CareReviewLoader.tsx`, `web/components/ScreeningBlock.tsx`, `web/components/PharmaReconcile.tsx`
(+ co-located `*.module.css`), `web/app/pharmacist/reconcile/pharma.css` (global class names stay),
`web/app/physician/**`, `web/app/pharmacist/**`, `web/lib/care.ts`, `web/lib/pharma.ts` (display helpers only), tests
`web/tests/{care-review,care-review.screening,pharma-page}.test.tsx`, `web/e2e/{care,pharma,pharma-a11y}.spec.ts`.

**Changes, in priority order:**

1. **C1 Care review (F2).** PageHeader (h1 `Care suggestion review — {case} at {dp}`; `output-label` p stays, as a
   muted subtitle; provider/version as muted meta). `redflag-section` as `Section tone="critical"`: `alerts` (keep
   `role="alert"` and `<strong>Escalate to a clinician now.</strong>`) as one card per alert, then ScreeningBlock.
   `suggestion-section`: ≥1024 two columns. Left: case summary (`case-summary`). Right: `next-information` (keep
   `<ol>`) and `pathway-options`. Evidence refs render as 14px muted text on their own line (text content
   unchanged, e.g. `available <ISO>`). Uncertainty as a StatusChip. Abstained / status-error as a warning Notice.
   `missing-information` as a warning Notice with the list (keep `<li>` texts). Review: `acknowledgements` fieldset
   with ≥44px label rows. **Vocabulary picker:** each CodePicker gets a search `<input type="search">` filter (label
   `ค้นหา / Filter`) and a scroll container `max-height: 320px; overflow:auto`. Selected items are listed first, with a
   count `เลือก n/5`. Every checkbox stays rendered (filtering hides only non-matching, **unselected** rows) with the
   same ids and label text. Sticky `ActionBar` with the ack summary + `Confirm suggestion` (via `form=`; one element
   only). Reject uses `variant="danger"`, Save edited is secondary.
2. **C2 Care list (F7).** PageHeader (`Care suggestion cases`, count). Remove "Back to physician home". Search filter
   by case id. `DataTable testId="care-case-list"`: case | T1 | T2. Visible button text `T1 · {formatThaiTime(as_of)}`,
   with `aria-label` unchanged (`Assess {case} at {dp}`). Buttons are secondary; the busy row shows `กำลังประเมิน…`.
   Cards at 390, with T1/T2 side by side.
3. **C3 Reconcile (F8).** PageHeader (h1 `Medication reconciliation`, REVIEW_NOTE subtitle, NLM attribution muted
   meta keeping `data-testid="nlm-attribution"`). The run form comes **first** as a card (patient | mode | `Run check`
   primary, inline at ≥768). Then the single `role=status` line. ≥1024 two columns: issues (main) | aside with
   `scope` section (heading `Scope of this check` stays h2 and visible; keep `<p>Not checked:</p>` immediately
   followed by `<ul>`) and notices. Issue cards: severity as a **neutral** StatusChip with text (keep the s5 decision:
   no alarm colour for severity) plus the existing border weight; `issue-status` chip. `Confirm` = primary, `Dismiss` =
   **secondary**, with the reason Field next to Dismiss. Source tables in `.ui-table-scroll`. "Medication lists as
   read" stays visible, full width, below. Convert `pharma.css` to the px scale (14/16/20) and spacing tokens, keeping
   the class names.
4. **C4 ScreeningBlock.** Count line → StatusChip-style emphasis (keep `data-testid="screening-count"` and
   `role="status"` as is). Banner → warning Notice (keep `role="alert"`, `screening-banner`, BANNER text). Keep
   `screening-scope` and `screening-not-evaluated` visible. Put `screening-readings` inside
   `<details><summary>Vital readings used (n)</summary>`, closed by default, keeping the exact line text
   (`rr = 22, read at <ISO>, age … — fresh`). Props unchanged (TriageReview in WP-B renders it).
5. **C5 Layouts.** `app/physician/layout.tsx` and `app/pharmacist/layout.tsx` render `<AppShell>{children}</AppShell>` only.

**Load-bearing selectors (keep):** care: button `Assess {case} at {dp}`, `care-case-list`, h1 contains the case id, test ids
`redflag-section`, `suggestion-section`, `alerts` (role=alert), `no-alert`, `screening-section`, `screening-banner`
(`RED-FLAG SCREENING INCOMPLETE`/`NOT PERFORMED`), `screening-count`, `screening-scope`, `screening-not-evaluated`
(visible), `screening-readings` (text as now), `output-label`, `case-summary`, `next-information` (OL), `pathway-options`,
`missing-information` (li texts), `missing-information-none`, `abstained`, `status-error`, `acknowledgements`,
`review-result`; labels `I have seen alert {id}`, `/I have seen that red-flag screening incomplete/`, vocabulary labels
(e.g. `/Repeat full set of vital signs/`), `Reason for the edit`, `Reason for rejecting`; buttons `Confirm suggestion`,
`Save edited suggestion`, `Reject suggestion`; text `Suggestion for physician review — research prototype`;
`<strong>` `Escalate to a clinician now.`. Pharma: h1 `Medication reconciliation`, nav-reachable; label `Synthetic
patient`, `option[value]`, button `Run check`, single `role=status`; `ol.issue-list > li > article[data-type][data-severity]`
with `h3` titles; `table` > `caption` "Conflicting sources…", `th[scope=col]`, `rowheader`s; buttons `Confirm`,
`Dismiss`; label `Reason for dismissing`; the Dismiss button keeps focus after a validation error; `issue-status`,
`allergy-basis`, `unchecked-summary` (with link `Scope of this check` → `#scope-title`), `nlm-attribution`,
`source-N`, `section[aria-labelledby='scope-title'|'lists-title']` with h2 texts `Scope of this check` / `Medication
lists as read (N)`, the `Not checked:` p + ul structure; `forbidden` for other roles.

**Acceptance:**
- C-1 Care review SYNE-0011 T2: page height at 1280 ≤2,800 (before 5,424) and at 390 ≤6,000 (before 10,553). First alert top ≤500px at 1280. `Confirm suggestion` is inside the viewport on load at 1280 and 768. Each vocabulary container ≤320px tall. Filtering by `lactate` shows the lactate row. SYNE-0071 T1 (abstain): the missing-information Notice top ≤1,400px at 1280 (before ≈1,900) and no Confirm button.
- C-2 Care list: no raw ISO timestamp in visible button text. Height at 1280 ≤2,300, at 390 ≤4,500 (before 7,672). Filter `SYNE-001` leaves 2 rows (0011, 0012).
- C-3 Reconcile: `Run check` top ≤400px at 1280 (before 783) and ≤800 at 390 (before 1,203). Dismiss is not the primary variant. Run-page height at 1280 ≤4,000 (before 4,985). No page overflow at 390.
- C-4 `pharma.css` has no rem/em font sizes and no non-scale spacing.
- C-5 e2e green on 8163/3163: care, pharma, pharma-a11y, a11y and disclaimer for the physician/pharmacist pages, theme. vitest + tsc + `make test` green.

**Stretch:** a collapsible evidence line per suggestion item (`ดูหลักฐานและที่มา`); issue filter chips by status
(open/confirmed/dismissed); a summary strip on reconcile (open n · confirmed n · dismissed n).

---

## Merge plan (lead)

1. Merge WP-A first (primitives + CSS win). Then B, then C. On conflicts in `web/components/ui/*`, take WP-A's
   version and drop any `ui/*.module.css` copies.
2. Post-merge cleanup (lead or a follow-up): delete legacy classes (`.domain-panel*`, `.state-panel`, `.review-bar`,
   `.page`, `.eyebrow`, `.claim`, `.next-step`) once `grep` shows no users.
3. Re-run the walk script and the full e2e on the merged tree, then compare before/after metrics against the
   acceptance numbers above. The reviewer role goes to `clinical-safety-reviewer` (red-flag order, acknowledgement
   gating, abstention, claim boundary).

## Decisions required

- None blocking. F1 (login) is a regression fix within scope. It should also be checked on the Vercel public demo,
  where the picker is intended, and noted in `docs/DECISIONS.md` only if behaviour there changes (it should not).
