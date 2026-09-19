# Supervised synthetic usability pilot

## Purpose and stop conditions

This pilot measures whether staff can operate the software with synthetic scenarios. It does not measure clinical accuracy and does not authorize patient data, autonomous referral, treatment or HIS integration.

Stop the session if a participant enters real identifying information, another workspace becomes visible, the wrong draft revision can be confirmed, or an audit trail is missing. Record the issue and do not continue with that environment until it is resolved.

## Environment preparation

1. Build the React workspace and start one FastAPI process with a persistent pilot SQLite database.
2. Use `FRONT_DOOR_AUTH_MODE=token` and an untracked principals file with a distinct account for every participant.
3. Keep the default mock provider unless a live adapter has separately passed connectivity, contract and smoke checks.
4. Open `/nurse` and `/platform` on the target desktop and tablet. Confirm Prompt loads with network access disabled.
5. Create a timestamped backup and verify `/ready`, `/v2/readiness` and `/v2/capabilities`.
6. Prepare scenario cards containing only invented case IDs, adult ages and synthetic histories.

If the application is accessed beyond loopback, terminate TLS at an approved local reverse proxy. Do not place tokens or API keys in the scenario cards, browser bookmarks or repository.

## Participant tasks

The facilitator gives the scenario and observes without explaining button locations.

1. Sign in and state whether the system is using mock or verified live capability.
2. Create a synthetic case and complete the no-identifying-data attestation.
3. Send an intake message and explain whether the returned proposal is confirmed.
4. Edit and accept multiple proposed facts.
5. Correct one confirmed fact and verify the earlier value remains in history.
6. Prepare a draft, inspect evidence and identify outstanding information.
7. Edit the draft, explain why confirmation is disabled, save the new version and confirm it.
8. Refresh while an unsent message exists and recover the message.
9. Open system readiness and explain which capabilities remain unverified.

For the hospital-pilot concept study, use the full two-round interview and usability
protocol in `docs/innovation/USER_RESEARCH_PLAN.md`. In the Voice intake task, the
participant must edit and explicitly send the transcript; transcription must never
submit clinical text automatically.

## Observation form

Record participant role, device, task completion, assistance required, time per task, observed misunderstanding, accessibility barrier and any data/review integrity issue. Do not record names or patient information in the application database.

Internal release requires all five team accounts to complete every critical task without developer coaching, zero wrong-revision confirmations, zero duplicate writes after retry, zero cross-workspace access and zero lost unsent text. Staff pilot results must report the participant count and observed results without converting mock behavior into a clinical score.

## End of session

Export only aggregated observations. Save application logs without payloads or secrets, create a final database backup, and record code/data/configuration versions. Mark Thai live-model quality, ASR quality and clinical usefulness as pending unless those capabilities were actually evaluated.
