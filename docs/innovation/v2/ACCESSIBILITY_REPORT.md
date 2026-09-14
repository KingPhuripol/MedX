# Accessibility verification — 14 September 2026

Target: WCAG 2.2 AA for the scoped React workspace.

## Automated evidence

- Playwright critical workflow passes at 1440×900 and 768×1024.
- Axe runs after a complete create → conversation → proposal → draft edit → confirmation flow and reports zero critical or serious violations.
- Keyboard test verifies the skip link, button activation and recovery of unsent text after reload.
- Controls have a 44px minimum target, visible 3px focus ring, reduced-motion behavior and semantic labels.
- Component CSS contains no raw hex colors outside the token layer.

## Manual evidence and limits

The built desktop interface was visually inspected for hierarchy, Thai text wrapping, empty states and status clarity. Automated browser tests cover the tablet layout and prevent page-flow regressions.

VoiceOver/TalkBack comprehension, target-device microphone permission, 200% zoom on every browser and staff comprehension still require the supervised checklist. These items must not be marked complete from Axe alone. Clinical usefulness and real Thai ASR remain outside this accessibility result.
