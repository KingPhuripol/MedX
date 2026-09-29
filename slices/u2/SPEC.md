# U2 — Nurse and Physician Workflows

## Goal

รวม intake, triage review และ care review ใน case workspace เดียว พร้อม human confirmation และ cross-role handoff

## Delivered

- Case section navigation, persistent safety banner, evidence panel and review bar
- confirm/edit/reject events, required reasons, red-flag acknowledgement gate and immutable duplicate protection
- Nurse → Physician และ Physician → Pharmacist handoff with actor, role, timestamp and version
- compatibility redirects จาก `/nurse/*` และ `/physician/*`

## Safety invariants

- red flag precedes suggestion and blocks review until acknowledged
- edit/reject requires a reason; no review overwrites an earlier review
- suggestion copy never claims diagnosis, treatment or autonomous action

