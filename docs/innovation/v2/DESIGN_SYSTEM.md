# Clinical Front Door design system 1.0

## Context and goals

The interface must help staff complete a synthetic intake workflow without learning internal event, revision or agent terminology. It uses the supplied BDMS-inspired black, white and blue primitives while retaining the Clinical Front Door identity. It must not display a BDMS logo or imply BDMS endorsement.

The system must use semantic tokens for all components. Teams should extend an existing component or token before adding a local visual exception.

## Design tokens and foundations

The implementation source of truth is `innovation/workspace/src/tokens.css`.

### Brand identity

The product mark is a blue rounded square containing a doorway and a small signal star. The doorway represents a calm clinical entry point; the star identifies the JARVIS assistant. The reusable implementation is `innovation/workspace/src/components/BrandLogo.tsx`, and the browser favicon is `innovation/workspace/public/favicon.svg`. The mark must always be paired with the “Clinical Front Door” wordmark in the full sidebar and login lockup. The compact mark may stand alone in dense contexts. The interface must not use a BDMS logo, name or endorsement language.

| Token family | Required behavior |
|---|---|
| Brand primitives | Black `#000000`, white `#ffffff`, link blue `#0000ee`, brand blue `#005cb9` and reference gray `#919eab` must retain their supplied values. |
| Surfaces | Brand areas must use `surface-brand`. Operational content should use `surface-canvas`, `surface-panel`, `surface-subtle` and `surface-selected`. |
| Text | White text must be limited to a passing dark surface. `primitive-reference-gray` must not be normal text on white. |
| Feedback | Info, success, warning and danger must combine color with a written label or symbol. |
| Typography | Prompt must be bundled locally. Body must use 16px/24px. The scale must remain 12, 13, 14, 15, 16, 18, 24 and 48px. |
| Spacing | Components must use 3, 5, 6, 8, 12, 16 or 24px tokens. |
| Shape | Controls and panels must use 8px. A 50px radius must be limited to pills and circular marks. |
| Motion | Motion must use 150, 250 or 500ms and must honor `prefers-reduced-motion`. |

Component CSS must not contain raw hex values. Raw colors belong only in the token source.

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

The desktop navigation must remain visible in a black rail. Tablet navigation must become a drawer with a labeled backdrop; closing it must restore focus to the menu button. The active destination must use `aria-current="page"`. Staff must see only destinations allowed by their backend role.

### Case list and workspace

The case list must expose search, workflow status and attention state without opening each case. It must support loading, empty, no-results and pagination states. Long case IDs must wrap or truncate without covering status.

The workspace must separate conversation, proposed information, confirmed facts and draft review. A conversation must never visually imply that proposed information has already been confirmed.

The selected case must begin with one compact overview containing identity, confirmed-fact count, pending-review count and latest-draft state. A three-step tracker must expose the current position from intake through draft confirmation. The tracker must supplement the underlying status and must not become the authority for review decisions.

The conversation composer must remain visually attached to the conversation, preserve unsent text and expose one primary send action. Only the newest draft should appear in the operational flow; older drafts must remain available through progressive disclosure or history.

### Proposal and draft review

Proposal review must show selection, editable values, data type and measurement unit before one atomic save. A stale response must show that the case changed and must not silently retry with a new revision.

Draft review must show the version, source case revision, status, evidence and earlier versions. Unsaved edits must disable confirmation. A modified draft must become a new version and must require a separate confirmation.

### Voice and asynchronous work

Voice controls must expose idle, recording, transcribing, ready and error states in text. A transcript must remain editable and must never submit automatically. Failure must immediately leave typed input available.

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
- `/workspace` is the primary UI. `/ui/v2` remains a temporary recovery fallback and should be removed only in a later compatibility release.

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
