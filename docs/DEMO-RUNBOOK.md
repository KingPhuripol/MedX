# MedX Presentation Runbook

## Start

```bash
DEMO_MODE=1 make dev
```

Open `http://127.0.0.1:3000/login`. This flow is for synthetic data only.

## Accounts

| Role | Username | Local development password |
|---|---|---|
| Nurse | `nurse1` | `nurse1-dev-only` |
| Physician | `physician1` | `physician1-dev-only` |
| Pharmacist | `pharmacist1` | `pharmacist1-dev-only` |

Override passwords with the documented `SEED_*_PASSWORD` environment variables outside a disposable local demo.

## Eight-minute journey

1. Sign in as Nurse, open **รอบเดโม**, and choose **เริ่มรอบเดโมใหม่**.
2. In the nurse queue open **ทบทวนการคัดกรอง**. Point out case identity, stage, owner, safety and next action in the header.
3. Acknowledge the synthetic red flag, confirm the suggestion and hand off to Physician.
4. Sign out, sign in as Physician and open the care review from the same run. Confirm and hand off to Pharmacist.
5. Sign out, sign in as Pharmacist. Compare both medication sources, inspect provenance and confirm the discrepancy review.
6. Open **กิจกรรม** to show the immutable cross-role history with actor, timestamp and version.

## Presenter recovery

- If an action was already recorded, start a new run; never delete or reset the old run.
- A `409` means another action already won; reload current state before continuing.
- If demo mode is unavailable, restart the web process with `DEMO_MODE=1`.
- Mobile is a focused companion. Use tablet/desktop for transcript or large-vocabulary editing.

## Safety language

Say: “This is a research prototype using synthetic data. Suggestions require human review.” Do not claim diagnosis, treatment, prescribing, production readiness or use with real patients.
