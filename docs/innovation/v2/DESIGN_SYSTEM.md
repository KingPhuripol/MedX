# Clinical Front Door design system 2.0

## Context and goals

The interface must help staff complete a synthetic intake workflow without learning internal event, revision or agent terminology. Its visual language is a calm clinical-operations workspace: warm neutral canvas, white working surfaces, deep navy structure and restrained teal actions. It must not display a BDMS logo or imply BDMS endorsement.

The system must use semantic tokens for all components. Teams should extend an existing component or token before adding a local visual exception.

## Design tokens and foundations

The implementation source of truth is `innovation/workspace/src/shared/tokens.css`.

### Brand identity

The product mark is a teal rounded square containing a doorway and a small signal star. The doorway represents a calm clinical entry point; the star identifies the JARVIS assistant. The reusable implementation is `innovation/workspace/src/shared/ui/BrandLogo.tsx`, and the browser favicon is `innovation/workspace/public/favicon.svg`. The mark must always be paired with the “Clinical Front Door” wordmark in the full sidebar and login lockup. The compact mark may stand alone in dense contexts. The interface must not use a BDMS logo, name or endorsement language.

| Token family | Required behavior |
|---|---|
| Brand primitives | Semantic navy, teal, warm-neutral and feedback colors are defined only in `tokens.css`; component styles must not introduce local color values. |
| Surfaces | Brand areas must use `surface-brand`. Operational content should use `surface-canvas`, `surface-panel`, `surface-subtle` and `surface-selected`. |
| Text | White text must be limited to a passing dark surface. `primitive-reference-gray` must not be normal text on white. |
| Feedback | Info, success, warning and danger must combine color with a written label or symbol. |
| Typography | Prompt must be bundled locally. Body must use 16px/24px. The scale must remain 12, 13, 14, 15, 16, 18, 24 and 48px. |
| Spacing | Components must use 3, 5, 6, 8, 12, 16 or 24px tokens. |
| Shape | Controls use 8–10px and primary panels use 14px. A pill radius is limited to status badges and circular controls. |
| Motion | Motion must use 150, 250 or 500ms and must honor `prefers-reduced-motion`. |

Component CSS must not contain raw hex values. Raw colors belong only in the token source.

## Composition (DEC-0017, TASK-0036)

The two apps are designed separately. Nothing below overrides the safety content rules: the research-prototype label, the red-flag banner and the human-confirmation step stay the most prominent things on any screen that shows them.

**Why this section exists.** The 18 Sep build wrapped every region in the same bordered, shadowed card, used a 520px voice orb as the nurse screen's centrepiece, a persona name, an emoji label and a sparkle glyph as decoration. The baseline is in `docs/innovation/v2/baseline/`. The rules below replace that composition.

### Structure over containers

- Group with space and a single 1px `--border-subtle` rule, not with cards. A card (surface plus border) is used only for something the user can pick up or dismiss: a side sheet, a dialog, a toast.
- Shadows only on overlays (side sheet, dialog, menu). Page regions have none.
- Radius: 6px on controls and badges, 8px on overlays. Nothing else is rounded.
- One primary action per region. Secondary actions are text buttons.
- No decorative glyphs: no sparkle, orb, persona name, emoji or gradient. An icon appears only where it names an action or a state.

### Type and space

- Type scale: 13 (meta, table), 15 (body), 17 (section title), 20 (page title in a dense app), 24 and 32 (reserved for empty and sign-in states). Section titles are 17 semibold; body is 15 regular. Eyebrow labels are removed except to name the research-prototype status.
- Spacing steps 4, 8, 12, 16, 24, 32, 48. Related items 8–12 apart, sections 32–48 apart. Density is the platform's default; the nurse app uses the same scale with larger touch targets (min 44px).

### Nurse Intake (`/nurse`)

One job: take a history by voice or text, confirm what the assistant heard, hand off. Top to bottom:

1. **Case bar**, 56px: case ID and synthetic age, revision, the research-prototype tag, the case switcher and a text link to the Central Platform.
2. **Red-flag banner**, only when a flag is TRIGGERED or UNKNOWN. It sits above everything else and names the flag in text.
3. **Two columns.** Left, flexible: the transcript as plain rows (speaker, time, text), newest at the bottom, with the composer pinned under it. The microphone is a 44px control inside the composer, not a hero. Right, 360px: *Confirmed* facts as label–value rows, *Waiting for you* proposals with confirm/edit, and *Still missing* required information.
4. **Handoff bar**, pinned to the bottom: what will be sent, and one primary button, "ส่งให้แพทย์ตรวจ".

### Central Platform (`/platform`)

Review, decide, audit, evaluate. A 220px navigation rail (label only, no subtitles), then:

- **Queue** is a table, not a list of cards: case, age, urgency floor, red flags, facts, draft status, updated. Rows needing attention carry a text status, not only a colour.
- **Case review** is a split view: the deterministic screen (urgency floor and every red flag with its state) first, the draft below it with evidence references, and a decision rail on the right with CONFIRM, MODIFY, REJECT and ESCALATE and the required reason.
- **Audit and trace** is a timeline: time, actor, event, references. Agent trace lives here, not in the clinical flow.

## Component-level rules

### Focused clinical workspace

The case workspace must use three focused steps: **รับข้อมูล**, **ตรวจข้อมูล** and **ตรวจร่าง**. A persistent case context bar must show the synthetic case identifier, current revision and draft status. Step navigation should show completed, active, attention and not-started states, while the backend remains the authority for permissions and revision decisions.

The intake view must keep the composer attached to the conversation and show assistant proposals as pending review cards. The facts view must separate pending proposals, confirmed facts and consistency conflicts. The draft view must show only the latest draft in the primary flow, with evidence, outstanding items and older versions available through progressive disclosure.

### Side sheet, notification and metric cards

A side sheet must trap keyboard focus, close with Escape, provide a labeled close action and return focus to the control that opened it. It must remain usable at tablet width and must not hide unsaved changes. Notification cards should describe the next safe action, such as “มีข้อมูลจากผู้ช่วยรอตรวจ” and link to the facts step.

Metric cards should show one number, a short Thai label and an optional status icon. They must not be the only place where a blocking state is explained. Queue, readiness and experiment metrics must use the same spacing, border and type tokens.

### Experiment stepper and version timeline

The Agent Design workspace must expose the sequence **ค้นหา → ตรวจ validation → ตรึงแบบ → ประเมิน held-out**. The active stage and completed stages must be readable without color. Technical identifiers, raw JSON and trace details must stay behind a disclosure control and must be visible only to evaluator roles.

Draft history should use a version timeline. Each version must show its revision, status and creation time; selecting an older version must never make it confirmable when it is stale or superseded.

### Buttons and links

Buttons must have default, hover, focus-visible, active, disabled, loading and error guidance. A primary button must identify the next workflow action. Secondary and text buttons should support review or navigation without competing with the primary action. Disabled controls must keep a readable label and the surrounding text must explain why an important action is unavailable.

Buttons must activate with pointer, touch, Enter and Space. Links must navigate and activate with Enter. Touch targets must be at least 44×44px.

### Inputs and forms

Every input must have a persistent programmatic label. Required state must use native validation or `aria-required`. Error state must use `aria-invalid` and a written correction message. A failed request must keep the entered value. Long text must wrap, and text areas must remain vertically resizable.

### Navigation and app shell

The Central Platform uses a light, persistent operations rail with a written active state and teal edge marker. Tablet navigation becomes a drawer with a labeled backdrop; closing it must restore focus to the menu button. The Nurse Intake surface uses a compact horizontal product bar and does not expose the platform navigation. The active destination must use `aria-current="page"`. Staff must see only destinations allowed by their backend role.

### Case list and workspace

The case list must expose search, workflow status and attention state without opening each case. It must support loading, empty, no-results and pagination states. Long case IDs must wrap or truncate without covering status.

The workspace must separate conversation, proposed information, confirmed facts and draft review. A conversation must never visually imply that proposed information has already been confirmed.

The selected case must begin with one compact overview containing identity, confirmed-fact count, pending-review count and latest-draft state. A three-step tracker must expose the current position from intake through draft confirmation. The tracker must supplement the underlying status and must not become the authority for review decisions.

The conversation composer must remain visually attached to the conversation, preserve unsent text and expose one primary send action. Only the newest draft should appear in the operational flow; older drafts must remain available through progressive disclosure or history.

### Proposal and draft review

Proposal review must show selection, editable values, data type and measurement unit before one atomic save. A stale response must show that the case changed and must not silently retry with a new revision.

Draft review must show the version, source case revision, status, evidence and earlier versions. Unsaved edits must disable confirmation. A modified draft must become a new version and must require a separate confirmation.

### Voice and asynchronous work

Voice controls must expose idle, recording, transcribing, ready and error states in text. The primary record control may be circular for recognition, but must not use decorative AI orbs, gradients or ambient animation. A transcript must remain editable and must never submit automatically. Failure must immediately leave typed input available.

Queued and running jobs must use an `aria-live` status. Cancellation must retain the conversation text. A reconnect must recover durable job status.

### Status, tables and technical detail

Status badges must combine a symbol and Thai label. Tables must use header cells and a caption or accessible name. Technical identifiers, JSON and trace detail must stay behind progressive disclosure and be restricted to relevant roles.

## Accessibility acceptance criteria

- Every workflow action must be reachable and operable with keyboard only.
- Focus-visible must be at least 3px and must not be obscured by a sticky region.
- Normal text must reach 4.5:1 contrast; large text and UI boundaries must reach 3:1.
- Browser zoom at 200% must not lose content or actions.
- The 768×1024 layout must not create page-level horizontal overflow.
- Axe must report zero critical or serious violations after the confirmed-draft flow.
- Screen-reader labels must name case search, status filter, synthetic attestation, message input and every draft action.
- Status and errors must remain understandable in grayscale.

Automated checks must be combined with keyboard and screen-reader inspection before a supervised pilot.

## Content and tone standards

Labels must name the action and object: “ยืนยันร่างฉบับนี้”, “บันทึกเป็นฉบับใหม่” and “โหลดข้อมูลล่าสุด”. Labels such as “ตกลง”, “ทำต่อ” or “Submit” must not appear in the staff workflow.

Errors must state what happened and the next safe action. For example: “ข้อมูลเคสเปลี่ยนแล้ว กรุณาโหลดข้อมูลล่าสุดและทบทวนก่อนบันทึก”. Provider errors must not expose stack traces, credentials or raw payloads.

Clinical limitations must remain direct: “ยังไม่ผ่าน clinical validation” and “ข้อมูลสังเคราะห์เท่านั้น”. Mock results must not be described as model quality evidence.

## Anti-patterns and migration notes

- Components must not use raw hex colors, one-off spacing or radius values.
- Status must not rely on color alone.
- Staff screens must not expose enums, event IDs, tokens or JSON in the primary flow.
- Transcripts and agent proposals must not become confirmed facts without review.
- Hero imagery, decorative animation and dense technical dashboards must not displace operational information.
- `/platform` is the central case-review and evaluator UI; `/nurse` is the staff-assisted intake UI. They share the same API and audit history but must not mix their primary navigation. `/workspace` remains a compatibility entry point, and `/ui/v2` remains a temporary recovery fallback.

## QA checklist

- [ ] Prompt loads with the network disabled.
- [ ] Tokens contain every raw color used by components.
- [ ] Primary, secondary, danger and text buttons expose all states.
- [ ] Loading, empty, error and recovery states render for every page.
- [ ] Desktop and tablet critical flows pass Playwright.
- [ ] Axe reports zero critical or serious violations.
- [ ] Keyboard focus follows reading order and returns after closing the drawer.
- [ ] Unsent text survives refresh and a failed request.
- [ ] A stale or edited draft cannot be confirmed.
- [ ] Role-based navigation agrees with API authorization.
- [ ] Synthetic-only wording appears in navigation, banner and case creation.
- [ ] Mock, live and clinical readiness labels match evidence.
