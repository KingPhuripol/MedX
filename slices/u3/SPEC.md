# U3 — Pharmacist and Presentation Journey

## Goal

ปิด synthetic presentation journey ด้วย deterministic medication reconciliation และ repeatable run isolation

## Delivered

- Medication sources, frequency discrepancy, provenance and pharmacist confirm/edit/reject
- Role-gated append-only medication review; no clinical recommendation logic
- End-to-end Nurse → Physician → Pharmacist timeline and activity history
- Responsive, keyboard and axe coverage plus presenter runbook

## Acceptance

- each presenter run has independent events and never resets/deletes another run
- medication edit/reject requires a reason and confirm is explicit
- E2E covers all three roles, legacy redirects and the three target viewports

