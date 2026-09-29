# U1 — Foundation, Shell and Read-Only Case View

## Goal

สร้าง hospital-blue foundation และ shared case context ตาม `docs/UI-SPEC.md` โดยไม่เปลี่ยน contract ของ voice/triage/care เดิม

## Delivered

- Tailwind + shadcn New York configuration, Radix dependencies, Lucide and SCBXBeta2 tokens
- Thai-first login, role-aware `AppShell`, seeded `/demo`, `/app/queue` และ shared case overview
- Synthetic-only journey/run/queue/case/timeline API และ isolated append-only presenter runs
- Loading, empty, error, partial, long Thai text and responsive data behavior

## Acceptance

- `DEMO_MODE=1` controls launcher visibility; authentication and RBAC remain mandatory
- case, stage, owner, safety and next action visible in the shared header
- no horizontal overflow at 1280×800, 768×1024 and 390×844

