# Slice d1: public Vercel demo packaging

- Branch: `factory/d1` from `main` b0f668c. Tier 0 only: CPU, synthetic data, mock provider, offline tests.
- Basis: `docs/DECISIONS.md` 2026-09-29, "Public Vercel demo: two links". The owner approved uploading code to Vercel and one-click login with no password for the synthetic demo accounts.
- Deploying is the owner's act. This slice only builds and verifies the deployable bundle (`docs/DEPLOY-VERCEL.md`).

## Scope

1. `PUBLIC_DEMO=1` backend mode. It is off by default.
   - Any external provider configuration is refused at startup: a non-mock `GATEWAY_PROVIDER`, `GATEWAY_EXTERNAL_ENABLED`, `EXTERNAL_BASE_URL` or `EXTERNAL_API_KEY`. The same check runs in `Settings.__post_init__`, so it also applies to settings built in code.
   - `SESSION_SECRET` must be at least 32 characters.
   - The database defaults to `sqlite:////tmp/medx-demo.sqlite3` (`DATABASE_URL` can override it).
   - On every cold start the schema is created and the three synthetic users are seeded. This is idempotent, and it retries when several processes start on the same file at once.
   - `POST /api/auth/demo-login {role}` exists only in demo mode. Password login returns 404 in demo mode.
   - Sessions are stateless HMAC-SHA256-signed cookies `{username, role, exp}`. A cookie that is invalid, expired, forged, signed with a rotated secret, names an unknown user or has a mismatched role is treated as no session (401). The web then sends the user to the role picker.
   - RBAC and audit are unchanged. Audit is written to the demo database.
2. Web: when built with `NEXT_PUBLIC_PUBLIC_DEMO=1`, `/login` shows the Nurse/พยาบาล, Physician/แพทย์ and Pharmacist/เภสัชกร buttons instead of the password form. The disclaimer is unchanged. On Vercel, `/api/*` is rewritten to the Python function; locally it still goes to 127.0.0.1:8000.
3. Packaging:
   - `deploy/vercel/` holds `api/index.py` (forces `PUBLIC_DEMO=1`), `vercel.json`, `.vercelignore` and a slim `requirements.txt` (fastapi, pydantic, sqlalchemy, httpx).
   - `scripts/vercel_stage.sh <outdir>` assembles the web app, backend/app, casegraph, and the synthetic v1 inputs and manifest. Gold labels are not copied.

## Acceptance

| ID | Criterion | Evidence |
|---|---|---|
| D1-A01 | Demo login is absent when PUBLIC_DEMO is off | `test_demo_login_absent_when_disabled` |
| D1-A02 | External provider config and a weak secret are refused | `test_public_demo_refuses_unsafe_config` (6 cases), `..._direct_settings` |
| D1-A03 | Cold start seeds 3 users; the provider is mock; concurrent cold starts on one file succeed | `test_cold_start_seeds_and_uses_mock`, `test_concurrent_cold_starts_same_file` |
| D1-A04 | Each role logs in with one click; it reaches only its own home; the nurse gets 403 on the care and pharma APIs | `test_demo_login_each_role_and_rbac`, `test_nurse_denied_physician_and_pharmacist_apis` |
| D1-A05 | A signed session works on a fresh database/app instance with the same secret, and fails (401) after a secret rotation | `test_signed_session_survives_instance_switch` |
| D1-A06 | An invalid, expired, forged or unknown session gives 401, never a 500 | `test_unknown_or_invalid_session_is_401_not_crash` (7 cases), `test_tampered_payload_rejected` |
| D1-A07 | Demo login is audited | `test_demo_login_is_audited` |
| D1-A08 | Role picker in demo builds; password form otherwise | `web/tests/demo-login.test.tsx` (4) |
| D1-A09 | The staged bundle runs from the slim requirements in a clean venv: the app imports and the full role flow passes | local smoke (see DEPLOY-VERCEL.md) |
| D1-A10 | Staged bundle: `next build` and `vercel build` both succeed; the browser flow passes | `web/e2e/public-demo.spec.ts` with `PUBLIC_DEMO_E2E=1` |
| D1-A11 | `make test` passes | |

## Known limits (accepted in the decision)

- Each serverless instance has its own `/tmp`. Sessions survive an instance switch, but the cases, reviews, pharma runs and audit rows created in one instance are not visible in another, and they are lost when the instance is recycled.
- A stateless session cannot be revoked server-side before `exp`. Logout clears the cookie. Rotating `SESSION_SECRET` ends every session.
