# Slice t1 — MedX web theme (SCBX R&D visual system)

- Owner (Gantt): ธัญรดา (task 15, ออกแบบส่วนติดต่อผู้ใช้)
- Source of truth: `docs/PROPOSAL.md` (v8), sections 1.3.1 (Clinical Dashboard), 1.3.4 (research prototype, not for real patients), and the s0 spec `slices/s0/SPEC.md` (S0-A14 disclaimer, S0-A17 accessibility, S0-A18 claim hygiene).
- Visual reference (read only): `scbx-rd-template-deck/starter/deck.html` and `references/01-slide-grammar.md`. We reuse the tokens, type and page grammar. We do not copy the SCBX logo.
- Status: PLAN. Written by the planner. This is a visual change only. It changes no behaviour, API or clinical content.

## Scope

1. **Tokens: `web/app/theme.css`.** This file is the only place colours are defined.
   - Brand: `--grey-1 #E6E8E8`, `--grey-2 #D6DADB`, `--grey-3 #AEB3B4`, `--grey-4 #606769`, `--grey-5 #363F42`, `--grey-6 #212628`, `--grey-7 #15191A`, `--purple-1 #8F47BF`, `--purple-2 #6C2993`, `--purple-3 #3C1D5D`.
   - Surface: `--white #FFFFFF`, used for input fields and cards.
   - Warning, for the disclaimer and for `role="alert"` messages only: `--warn-bg #FFF4CE`, `--warn-border #8A6D00`, `--warn-fg` = `var(--grey-7)`.
   - `--type: "SCBXBeta2", system-ui, sans-serif`.
   - `globals.css` and components use `var(--…)` only. Tints use `color-mix()` over tokens.
   - Target usage is about 85% grey and 15% purple. Purple is an accent: the wordmark X, the eyebrow, the arrow, the primary button, links and focus rings.
2. **Font.** Copy `SCBXBeta2-Light.otf`, `-Regular.otf` and `-Bold.otf` byte-for-byte from the template's `assets/fonts/` into `web/public/fonts/`.
   - Declare three `@font-face` rules (weights 300/400/700, `font-display: swap`, `src: url("/fonts/…otf")`) in `theme.css`.
   - Use one family for Thai and Latin. No `next/font/google` and no remote font URLs.
   - Verified at planning time: SCBXBeta2 covers every glyph of the EN and TH disclaimer and the em dash. It **lacks `→` (U+2192)**. The arrow falls back to `system-ui` through the font stack, and that fallback is accepted.
3. **Wordmark.** `components/Wordmark.tsx` renders the text "Med" + `<span class="wordmark-x">X</span>`.
   - The X is `--purple-1`. The text is at least 24px bold so it is large text. The accessible name is "MedX".
   - It appears in a header on every page, below the disclaimer.
   - Page titles use the Next metadata template `%s · MedX — AI Clinical Front Door (research prototype)`. The default is `MedX — AI Clinical Front Door (research prototype)`.
   - No SCBX logo image, file or reference anywhere in `web/`.
4. **Page grammar** on `/nurse`, `/physician`, `/pharmacist`, `/403` and the 404 page, in this fixed order:
   1. `[data-testid=eyebrow]`: a small chip with a purple-1 dot (decorative) and a `--purple-2` label.
   2. The existing `h1`, kept so the S0 tests still find the role, "403" or "404".
   3. `h2[data-testid=claim]`: one claim sentence ending with a period.
   4. The body.
   5. `[data-testid=next-step]`: the bottom strip. It has a top border in `--grey-2`, text in `--grey-5`, one `<em>` key phrase in `--grey-7`, and `<span class="arrow" aria-hidden="true">→</span>` in `--purple-1` that is at least 19px bold.

   The copy stays non-clinical. Role homes keep "features arrive in later slices".
5. **Login as the cover.** Two columns at 1280 px wide:
   - A decorative panel `[data-testid=cover-panel]` with `aria-hidden="true"`. It has a `linear-gradient` from `--grey-7` through `--purple-3` to `--purple-2`, and a large faint "x" motif. The motif is a text glyph or an inline SVG, in `--purple-1`, with opacity 0.20 or less. It is not the SCBX logo asset.
   - The login form sits on `--grey-1` next to the panel.
   - At 768 px the panel stacks above the form or collapses. The form and the disclaimer stay usable and in view.
   - Any text in the panel is `--white` or `--grey-1` over stops no lighter than `--purple-2`.
6. **Safety chrome is kept.**
   - The disclaimer stays first in `<body>`, with the exact EN and TH text, in the warning tokens, at 14px or larger.
   - Focus rings: `:focus-visible` outline of 2px or more in `--purple-2`, with an offset of 2px.
   - Error (`role="alert"`) messages use `--warn-fg` on `--warn-bg` with a `--warn-border` edge. They never use purple.
   - Axe must report no serious or critical violations (0).
7. **Tests.**
   - Add `web/tests/theme.test.ts` (Vitest).
   - Add `web/e2e/theme.spec.ts` (Playwright).
   - Extend `a11y.spec.ts` to cover all 6 pages at both viewports.
   - Existing tests change only where a title or copy string legitimately changed.

## Out of scope

- Any backend, API, gateway, audit or casegraph change.
- New features, clinical content, dark mode, a language toggle, and PDF/PPTX export.
- Changing the disclaimer text.
- Urgency and red-flag colour semantics. The grey/purple palette has no alarm colours. A later slice must define urgency tokens with Safety Reviewer sign-off, and must not reuse purple to mean urgency.
- Any SCBX logo or co-branding. Publishing the repository or the font.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| T1-A01 | Unit and contract suites green | `make test` exit 0. 0 failed, 0 errors. The pytest and Vitest test counts are at least the S0 baseline (recorded before the first change) plus the new theme tests. | Run `make test` before and after the change. Record both summaries. |
| T1-A02 | Browser suite green | `make e2e` exit 0. 0 failed. All S0 specs (`health`, `roles`, `disclaimer`, `a11y`) and `theme.spec.ts` pass. | Run `make e2e` and record the summary. |
| T1-A03 | S0-A14 still holds; disclaimer stays prominent | 6/6 pages x 2 viewports (1280x800, 768x1024). The disclaimer shows the exact EN and TH text, `role=note`, `toBeVisible` and `toBeInViewport` (fully), and is the first child of `body`. Computed `background-color` equals the resolved `--warn-bg`, and font-size is at least 14px. | `e2e/disclaimer.spec.ts` (existing) plus the `theme.spec.ts` prominence checks. |
| T1-A04 | Axe clean on every page | 0 serious or critical axe violations on 6/6 pages x 2 viewports (12 scans), including `color-contrast`. | `e2e/a11y.spec.ts`, extended to `/403`, the 404 page and both viewports. |
| T1-A05 | Every text/background pair meets WCAG AA | Every pair in the contrast table below passes: normal text ≥ 4.5:1; large text (≥ 24px, or ≥ 18.66px bold) ≥ 3:1; non-text UI (focus ring, input border, warning border, arrow) ≥ 3:1. The forbidden pairs are not used for normal text. | `tests/theme.test.ts` parses the hex values in `theme.css` and computes WCAG 2.x ratios for the declared pair list. T1-A04 axe `color-contrast` confirms the rendered pages. |
| T1-A06 | Tokens exact and centralised | `theme.css` defines all 10 brand tokens with exactly the listed hex values, plus `--white` and the `--warn-*` tokens. `layout.tsx` imports `theme.css` before `globals.css`. | `tests/theme.test.ts`. |
| T1-A07 | No hard-coded colours outside `theme.css` | 0 matches of `#[0-9a-fA-F]{3,8}\b`, `rgba?\(`, `hsla?\(` or CSS named colours in colour properties, across `web/**` (css/ts/tsx/mjs). Exclusions: `node_modules`, `.next`, `public/fonts`, `package-lock.json`, `theme.css`. | `tests/theme.test.ts` (file walk and regex). Cross-checked with the grep in Run commands, which must print nothing. |
| T1-A08 | About 85/15 grey/purple usage | Across `web/app/**/*.css` and inline styles, `var(--purple-*)` references are 8–25% of all `var(--grey-*|--purple-*)` references. Reviewer visual check of the T1-A15 screenshots: purple reads as an accent only. | `tests/theme.test.ts` (reference count) and a human/reviewer look at the screenshots. |
| T1-A09 | Font self-hosted and identical to the template | The 3 `.otf` files in `web/public/fonts/` match the template sha256 (3/3). There are 3 `@font-face` rules for weights 300/400/700 with same-origin `/fonts/` URLs. `--type` starts with `"SCBXBeta2"`. 0 imports of `next/font/google` and 0 `fonts.googleapis`/`fonts.gstatic`/`http(s)://` font URLs. | `tests/theme.test.ts` (sha256 and CSS parse). |
| T1-A10 | SCBXBeta2 renders Thai and Latin text | On `/login` and `/nurse`, `document.fonts` has SCBXBeta2 faces with `status==="loaded"` for at least weights 400 and 700. CDP `CSS.getPlatformFontsForNode` shows `familyName` SCBXBeta2 for 100% of glyphs in the TH disclaimer `<p lang="th">`, the EN disclaimer `<p lang="en">` and the `h1`. The next-step text excluding the arrow is ≥ 95% SCBXBeta2. | `e2e/theme.spec.ts` (Chromium CDP session). |
| T1-A11 | No network font loading | While visiting all 6 pages, 0 requests go to any origin other than `127.0.0.1:3000` or `127.0.0.1:8000`. Every font request is `/fonts/SCBXBeta2-*.otf` with status 200. | `e2e/theme.spec.ts` (`page.on("request")` collector). |
| T1-A12 | No SCBX logo | 0 files in `web/` whose sha256 equals `logo-black.png` or `logo-white.png`. 0 files named `*logo*`. The case-insensitive string `scbx` appears in `web/` source only as `SCBXBeta2` (font family and font filenames). User-visible text has 0 `SCBX`. | `tests/theme.test.ts` (hash and name scan, allowlisted regex). `theme.spec.ts` checks that `document.body.innerText` does not contain `SCBX`. |
| T1-A13 | MedX wordmark and titles | The wordmark is on 6/6 pages with accessible name "MedX". The `X` computed colour equals `--purple-1`, and it is at least 24px bold. `document.title` contains `MedX — AI Clinical Front Door (research prototype)` on 6/6 pages. 0 occurrences of the old `"Clinical Front Door (research prototype)"` title without `MedX` in `web/app`. | Vitest `wordmark.test.tsx`, `e2e/theme.spec.ts`, and `tests/theme.test.ts` (grep). |
| T1-A14 | Page grammar | On 5/5 non-login pages: exactly 1 eyebrow, 1 `h1`, 1 `h2[data-testid=claim]` whose trimmed text ends with `.`, and 1 next-step strip containing an `aria-hidden` `.arrow` in `--purple-1` and at least 1 `<em>`. DOM order is eyebrow < h1 < claim < next-step. On login: `cover-panel` is `aria-hidden`, has a gradient `background-image`, and the motif opacity is ≤ 0.20. At 1280 the panel and form boxes do not overlap horizontally. | `e2e/theme.spec.ts`. |
| T1-A15 | Screenshots saved | 12 PNGs exist: `artifacts/factory/t1/{login,nurse,physician,pharmacist,403,404}-{1280x800,768x1024}.png`, from the final `make e2e` run. `artifacts/` is gitignored, so `make e2e` regenerates them. | `e2e/theme.spec.ts` writes them. The checker lists the files with timestamps. |
| T1-A16 | Visible keyboard focus | For every focusable element on `/login`, `/nurse` and `/403`: when reached by Tab, the computed `outline-style` is not `none`, `outline-width` is at least 2px, and the outline colour is at least 3:1 against the page background. Keyboard login and logout (S0-A17) still pass. | `e2e/theme.spec.ts` and `e2e/a11y.spec.ts`. |
| T1-A17 | No clinical claims or behaviour change | `test_repo_hygiene` passes: 0 occurrences of `diagnos`, `prescrib` or `treat` in `web/app` or `web/components` outside the disclaimer. The role x home matrix (S0-A04) and bad-credential behaviour (S0-A05) are unchanged. `git diff` touches no files under `backend/` or `casegraph/`. | pytest, `e2e/roles.spec.ts`, and `git diff --stat main...factory/t1`. |

Contrast table (WCAG 2.x, computed from the token hex values at planning time):

| Use | Foreground / background | Ratio | Required |
|---|---|---|---|
| Body, h1, claim h2, next-step `<em>`, wordmark "Med" | grey-7 / grey-1 | 14.40 | 4.5 |
| Secondary text, next-step body | grey-5 / grey-1 | 8.77 | 4.5 |
| Muted meta text (only on grey-1, never on grey-2) | grey-4 / grey-1 | 4.69 | 4.5 |
| Eyebrow label, links (underlined) | purple-2 / grey-1 | 7.19 | 4.5 |
| Wordmark X (≥24px bold, large text) | purple-1 / grey-1 | 4.47 | 3.0 |
| Next-step arrow (≥19px bold, large text, decorative) | purple-1 / grey-1 | 4.47 | 3.0 |
| Primary button label | white / purple-2 | 8.84 | 4.5 |
| Primary button hover | white / purple-3 | 13.76 | 4.5 |
| Input text | grey-7 / white | 17.71 | 4.5 |
| Input border (non-text) | grey-4 / white | 5.77 | 3.0 |
| Focus ring (non-text) | purple-2 / grey-1 ; purple-2 / white | 7.19 ; 8.84 | 3.0 |
| Disclaimer and alert text | grey-7 / warn-bg | 16.09 | 4.5 |
| Disclaimer border (non-text) | warn-border / warn-bg | 4.47 | 3.0 |
| Cover panel text, if any | white / purple-2 (lightest stop) ; white / grey-7 | 8.84 ; 17.71 | 4.5 |

Forbidden for normal-size text: purple-1 / grey-1 (4.47), purple-1 / grey-2 (3.90), grey-4 / grey-2 (4.09), purple-1 / grey-7 (3.22).

## Required test cases

- Vitest `tests/theme.test.ts`:
  - `tokens exact`
  - `contrast pairs meet AA`
  - `no hard-coded colours outside theme.css`
  - `purple share 8-25%`
  - `fonts self-hosted, sha256 match, 3 font-faces`
  - `no remote font URLs`
  - `no SCBX logo files or references`
  - `titles use MedX template`
- Vitest `tests/wordmark.test.tsx`: accessible name "MedX", X in a `.wordmark-x` span.
- Vitest `tests/layout.test.tsx` (existing): disclaimer first. Extend it to assert that `Wordmark` renders after the disclaimer.
- Playwright `e2e/theme.spec.ts`, with each test at 1280x800 and 768x1024 where relevant:
  - `disclaimer prominence`
  - `fonts render (document.fonts + CDP platform fonts, TH + EN)`
  - `no external requests`
  - `wordmark + title on 6 pages`
  - `page grammar on 5 pages`
  - `login cover layout`
  - `focus rings visible`
  - `no SCBX in visible text`
  - `screenshots`
- Playwright `e2e/a11y.spec.ts`: extended to 6 pages x 2 viewports.
- All S0 cases (see `slices/s0/SPEC.md`) keep passing unchanged, except for title or copy string updates.

## Clinical and safety risks (t1)

| Risk | Mitigation |
|---|---|
| The restyle weakens the research-prototype disclaimer, so users mistake the prototype for a clinical tool | The disclaimer stays first, in distinct warning tokens rather than brand grey, and in view at both viewports on 6/6 pages (T1-A03). Titles say "research prototype" (T1-A13). |
| Branding implies an institutional or clinical endorsement | No SCBX logo or name in the UI (T1-A12). The product is the "MedX" wordmark only. |
| Poor contrast or tofu glyphs cause misreading, especially of Thai text | AA pair table and axe (T1-A04, T1-A05). CDP glyph check for TH and EN (T1-A10). The known `→` gap falls back to a system font. |
| Errors or alerts get lost in a low-saturation palette | Alerts use the warning tokens and `role="alert"`, never purple (Scope 6). |
| Later slices reuse purple to signal urgency or red flags | Out of scope here. Urgency tokens need a dedicated slice with Safety Reviewer sign-off. |
| Font licensing: the SCBXBeta2 `.otf` metadata reads "Copyright © 2022 … All rights reserved." Committing it redistributes it. | Allowed only for this private repo at the owner's request. **Human decision required** before any push to a public remote, release, or demo hosting that serves the font (Human Approval Policy: external upload/publication). |

## Run commands

```bash
cd /Users/king_phuripol/AI-Engineer/Workstreams/SeniorProject/Full-Agent-theme
make test        # pytest + Vitest (includes theme/wordmark tests)
make e2e         # Playwright + axe; writes artifacts/factory/t1/*.png
# T1-A07 cross-check: must print nothing
grep -rnE '#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(' web --include='*.css' --include='*.ts' --include='*.tsx' --include='*.mjs' \
  --exclude-dir=node_modules --exclude-dir=.next | grep -v 'web/app/theme.css'
# T1-A12 cross-check: only SCBXBeta2 hits allowed
grep -rniI 'scbx' web --exclude-dir=node_modules --exclude-dir=.next | grep -v 'SCBXBeta2'
ls -la artifacts/factory/t1/
```
