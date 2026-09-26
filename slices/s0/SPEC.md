# Slice s0 — Project skeleton

- Owner (Gantt): ภูริณัฐ
- Source of truth: `docs/PROPOSAL.md` (v8). Sections used: 1.3.1 (Clinical Dashboard: role permissions, record of who acted and when), 1.3.4 (research prototype, not for real patients; external providers get synthetic or agreement-permitted data only), 2.2 Table 2.1 (stack), 3.1 (Model Gateway: fixed input/output format, logs every call, enforces data policy, provider swappable without changing clients), 3.2.1 (typed evidence with event time, available-at time, source).
- Status: PLAN. Written by the planner. This slice builds no clinical features.

## Scope

1. **Monorepo layout**
   - `backend/`: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x.
   - `casegraph/`: a Python package.
   - `web/`: Next.js (App Router) with TypeScript.
   - Root files: `Makefile`, `docker-compose.yml`, `.env.example`, `.gitignore`.
   - Commit lockfiles for Python and npm.
2. **Database**
   - The app reads `DATABASE_URL`.
   - When it is unset, the default is `sqlite:///./backend/dev.db`. Tests use a temporary SQLite file.
   - `docker-compose.yml` defines a `postgres:16` service for dev/manual use. It is optional because the Docker daemon may not be running.
   - Schema is created by one module that runs on both dialects, including the append-only triggers.
3. **Authentication and roles**
   - The seed creates three dev-only synthetic users: `nurse1`, `physician1`, `pharmacist1`.
   - Roles come from a closed enum: `nurse | physician | pharmacist`.
   - Passwords are stored hashed (stdlib `hashlib.scrypt` or an equivalent). The seed reads dev passwords from env and falls back to documented dev defaults.
   - Sessions use an opaque token with server-side expiry.
   - Endpoints: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/me`, `GET /api/home/{role}`. `/api/home/{role}` returns a placeholder payload for the caller's own role only and 403 for any other role.
4. **Web app**
   - Routes: `/login`, `/nurse`, `/physician`, `/pharmacist`, plus a 403 page and a 404 page.
   - After login, the user is redirected to their own role home.
   - Visiting another role's home shows the 403 page.
   - A visitor with no session is redirected to `/login`.
   - Role homes are placeholders: a role name and "features arrive in later slices". They contain no clinical content.
5. **Research-prototype disclaimer**
   - Rendered by the root layout on every page as `data-testid="research-disclaimer"` with `role="note"`.
   - Required text, in English and Thai: "Research prototype — not for clinical use. Outputs are suggestions for review and require confirmation by a clinician." / "ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง ผลลัพธ์เป็นข้อเสนอที่ต้องให้บุคลากรยืนยัน".
   - `GET /api/health` returns `research_prototype: true`.
6. **Model Gateway** (`backend/app/gateway/`)
   - Stable Pydantic contract (`contract_version = "0.1.0"`):
     - `GatewayRequest {task, inputs, data_class}`. `data_class` is a required enum `synthetic | mimic | hospital | real | unknown` and has no default.
     - `GatewayResponse {status: ok|rejected|error, provider, model_version, contract_version, output|null, reason|null, latency_ms, request_sha256}`.
   - The `Provider` protocol has two implementations:
     - **MockProvider** is the default. It is deterministic: the output is a pure function of the canonical request hash. Its output is visibly labelled `MOCK — not clinical`. It makes no network or randomness calls.
     - **OpenAICompatibleAdapter** uses plain `httpx` against `EXTERNAL_BASE_URL`. It is disabled unless `GATEWAY_EXTERNAL_ENABLED=true`. Before any network I/O it rejects every request whose `data_class != "synthetic"` (`status=rejected`, `reason=policy_non_synthetic`). A timeout, HTTP error, or invalid/unschema'd response gives `status=error, output=null`. No provider SDK is imported. Provider-native objects never leave the adapter.
   - Provider selection comes from config (`GATEWAY_PROVIDER=mock` by default). Clients call only `POST /api/gateway/invoke`, which requires authentication.
7. **Append-only audit log**
   - Stored in the `audit_events` table: `id, ts_utc, actor_id|null, actor_role|null, action, target, outcome, details_json, request_id`.
   - Written for:
     - every login attempt, successful or failed;
     - every logout;
     - every role-home access denial;
     - every gateway invocation, whatever its status.
   - Gateway details contain `provider, model_version, contract_version, data_class, request_sha256, status, reason, latency_ms`. They never contain raw inputs, passwords, or tokens.
   - DB triggers reject `UPDATE` and `DELETE` on SQLite and PostgreSQL. No API route mutates or deletes audit rows.
8. **`casegraph/` package**
   - Contains only typed Pydantic base classes: `TypedData`, `EvidenceItem` (`data_type, patient_ref, event_time, available_at_time, source, provenance, version`, all required), `NodeType` (enum placeholder), `Node` (abstract: `node_type, input_types, output_types, provider`).
   - No Compiler, no Executor, and no node implementations. Those are slice S2.
9. **Makefile**
   - `make test` installs dependencies idempotently into a local `.venv` and `web/node_modules`, then runs pytest (backend + casegraph) and web unit tests (Vitest + Testing Library). Network access is blocked during pytest.
   - `make dev` starts uvicorn at `127.0.0.1:8000` and `next dev` at `127.0.0.1:3000`, with the seed applied.
   - `make e2e` runs Playwright against `make dev`.
   - `make test-pg` runs the DB/audit tests against compose PostgreSQL and skips with a clear message if Docker is unavailable.

## Out of scope

- All clinical features: intake, Voice Agent, department suggestion, care suggestions, Pharma Agent, red-flag rules, dashboard patient list, human checkpoint/confirmation of outputs, and Medical Passport.
- Case Graph Compiler/Executor/Output Store/Replay (S2), and any real model, vLLM, or team model.
- Any real external API call. The adapter exists but stays disabled, and tests use `httpx.MockTransport` only.
- Any real, MIMIC, or hospital data. Seeded users are synthetic.
- Production auth (SSO, MFA, password reset), deployment, HTTPS, object storage, and Alembic migration history.
- An audit viewer UI and an admin role.

## Acceptance

| ID | Criterion | Threshold | How measured |
|---|---|---|---|
| S0-A01 | `make test` passes from a clean clone | Exit code 0; 0 failed, 0 errors; skips only for the documented Docker-dependent tests | `git clone` the branch into an empty temp dir (no `.venv`, `node_modules`, `dev.db`, `.env`), then run `make test` with only Python 3.11+ and Node 20+ preinstalled. Record the output. |
| S0-A02 | `make dev` serves the API health endpoint and the web app | Within 90 s of start: `GET 127.0.0.1:8000/api/health` returns 200 with `{"status":"ok","default_provider":"mock","research_prototype":true}`, and `GET 127.0.0.1:3000/login` returns 200 with the disclaimer. Both services bind to 127.0.0.1 only. | e2e-tester starts `make dev` and polls with `curl`. The Playwright smoke test `e2e/health.spec.ts` checks the same. |
| S0-A03 | Each of the three roles can log in and lands on its own home page | 3/3 roles | pytest `test_login_each_role` (API) and Playwright `e2e/roles.spec.ts` (browser: log in, URL `== /{role}`, heading shows the role) |
| S0-A04 | Each role sees only its own home page | 9/9 cells of the role x home matrix correct: own home returns 200/renders; other homes return API 403 and show the UI 403 page. Unauthenticated access to 3/3 homes returns API 401 and redirects to `/login`. | pytest `test_role_home_matrix` (parametrized 3x3 plus unauthenticated) and Playwright `e2e/roles.spec.ts` |
| S0-A05 | Bad credentials are rejected with no session | 100% of cases (wrong password, unknown user, empty fields): 401, no token issued, no session cookie | pytest `test_login_rejects_bad_credentials` |
| S0-A06 | Gateway external adapter rejects non-synthetic payloads (tested) | For `data_class` in {mimic, hospital, real, unknown}: 4/4 give `status=rejected, reason=policy_non_synthetic`. A missing `data_class` gives 422. The MockTransport records **0** outbound requests in all 5 cases, including with `GATEWAY_EXTERNAL_ENABLED=true`. | pytest `test_external_adapter_rejects_non_synthetic` (parametrized) and `test_missing_data_class_is_422` |
| S0-A07 | External adapter is off by default | With default config, a synthetic request routed to the external adapter gives `status=rejected, reason=adapter_disabled` and 0 outbound requests. The default provider is `mock`. | pytest `test_external_adapter_disabled_by_default`, `test_default_provider_is_mock` |
| S0-A08 | The mock provider is deterministic and offline | Two identical requests give byte-identical `output`. The whole pytest run completes with socket connections blocked (0 network attempts). | pytest `test_mock_deterministic`. Network blocking is done by a conftest fixture (e.g. `pytest-socket --disable-socket --allow-unix-socket`) |
| S0-A09 | Provider failure fails safe | Timeout, HTTP 5xx, and a malformed/schema-invalid body from the (MockTransport) external provider each give `status=error, output=null`, HTTP 200 from `/api/gateway/invoke` with no stack trace. 3/3. | pytest `test_external_adapter_fail_safe` (parametrized) |
| S0-A10 | Provider coupling is isolated | 0 imports of any provider SDK (`openai`, `anthropic`, and so on) in the repo. 0 references to `gateway.adapters` outside `backend/app/gateway/`. 0 provider names or adapter types in `web/`. | pytest `test_provider_isolation` (AST/grep scan) |
| S0-A11 | Every login writes an audit record | For N scripted attempts (success, wrong password, unknown user) plus logouts: audit row count increases by exactly N. Each row has UTC `ts_utc`, `action`, `outcome`, and `actor_id`/`actor_role` when known. Rows contain 0 occurrences of the password sentinel. | pytest `test_audit_login_events` |
| S0-A12 | Every gateway call writes an audit record | For each of ok, rejected (policy), rejected (disabled), and error: exactly 1 audit row per call, with `provider, model_version, contract_version, data_class, request_sha256, status, latency_ms`. A sentinel string placed in `inputs` appears in 0 audit rows. | pytest `test_audit_gateway_events` (parametrized) |
| S0-A13 | The audit log is append-only | `UPDATE` and `DELETE` on `audit_events` raise at the DB level on SQLite (2/2). The route inventory has 0 PUT/PATCH/DELETE routes on audit. On PostgreSQL: 2/2 when Docker is available, otherwise reported as SKIPPED (non-gating). | pytest `test_audit_append_only_sqlite`, `test_no_audit_mutation_routes`; `make test-pg` → `test_audit_append_only_pg` |
| S0-A14 | The research-prototype disclaimer is visible on every page | 6/6 pages (`/login`, `/nurse`, `/physician`, `/pharmacist`, 403, 404) render `data-testid="research-disclaimer"` with the exact English and Thai text, visible in the viewport without scrolling on 1280x800 and on a tablet (768x1024). `/api/health` returns `research_prototype: true`. | Vitest `layout.test.tsx`; Playwright `e2e/disclaimer.spec.ts` (`toBeVisible` and `toBeInViewport` for each page and viewport) |
| S0-A15 | `casegraph` provides typed base classes only | The package imports. `EvidenceItem` raises `ValidationError` when any of `available_at_time, source, provenance, version` is missing (4/4). `Node` cannot be instantiated directly. There is no `compile`/`execute` symbol. | pytest `casegraph/tests/test_types.py` |
| S0-A16 | DB config uses DATABASE_URL, with SQLite as default | Unset gives a SQLite engine. A set value is honored. `docker-compose.yml` passes `docker compose config` when Docker is present (skipped otherwise). | pytest `test_database_url_default_and_override`; `make test-pg` |
| S0-A17 | Accessibility baseline | 0 axe violations of severity serious or critical on `/login` and the 3 role homes. Login inputs have associated labels. Login and logout work with the keyboard alone. | Playwright `e2e/a11y.spec.ts` with `@axe-core/playwright` |
| S0-A18 | No secrets and no clinical claims | 0 committed secrets (`.env` gitignored; only `.env.example`; the external key is read from env only). The UI copy has 0 occurrences of "diagnos", "prescrib", or "treat" outside the disclaimer. | pytest `test_repo_hygiene` (gitignore check, regex scan for key patterns and forbidden claim terms in `web/app/**`) |

The e2e-tester has no clinical gold labels for s0. The evaluation set for this slice is the fixed scenario list above: 3 roles, a 3x3 matrix, 5 data_class cases, 3 failure modes, and 6 pages.

## Required test cases

These are backend and casegraph tests, run by `make test`:
- `test_health`
- `test_login_each_role`
- `test_login_rejects_bad_credentials`
- `test_role_home_matrix`
- `test_default_provider_is_mock`
- `test_mock_deterministic`
- `test_external_adapter_disabled_by_default`
- `test_external_adapter_rejects_non_synthetic[mimic|hospital|real|unknown]`
- `test_missing_data_class_is_422`
- `test_external_adapter_fail_safe[timeout|http_5xx|malformed]`
- `test_external_adapter_synthetic_happy_path` (MockTransport; asserts that `provider`/`model_version` come from the adapter and no SDK types leak)
- `test_gateway_requires_auth`
- `test_provider_isolation`
- `test_audit_login_events`
- `test_audit_gateway_events[ok|policy|disabled|error]`
- `test_audit_append_only_sqlite`
- `test_no_audit_mutation_routes`
- `test_database_url_default_and_override`
- `test_repo_hygiene`
- `casegraph/tests/test_types.py`

These are web unit tests, run by `make test`:
- `layout.test.tsx` (disclaimer present)
- `login.test.tsx` (labels, error message on 401)
- `role-guard.test.tsx` (wrong role gives 403 view, no session redirects)

These are browser tests, run by `make e2e`:
- `health.spec.ts`
- `roles.spec.ts`
- `disclaimer.spec.ts`
- `a11y.spec.ts`

`make test-pg` runs `test_audit_append_only_pg`. It is skipped if Docker is unavailable.

## Clinical and safety risks (s0)

| Risk | Mitigation in this slice |
|---|---|
| Someone mistakes the prototype or mock output for clinical advice | Disclaimer on every page (A14). Mock output is labelled `MOCK — not clinical`. Role homes carry no clinical content (A18). |
| Patient data leaks to an external API | The adapter is disabled by default, allows synthetic data only, the check runs before any I/O, and 0 network calls are made in tests (A06–A08). Allowing agreement-permitted data requires a recorded human approval and is out of scope. |
| The gateway fabricates output on failure | Fail-safe `status=error, output=null` (A09). |
| Role leakage: a user sees another role's work surface | Server-side 403 plus UI guard, with a 3x3 matrix test (A04). |
| Audit tampering or incompleteness weakens accountability | DB-level append-only triggers. Exactly one row per event (A11–A13). |
| Sensitive data or credentials land in the audit log | Only hashes and references are stored, verified by sentinel tests (A11, A12). |
| Weak dev credentials are exposed on a network | Services bind to 127.0.0.1. Dev users are seeded only by the dev seed and documented as synthetic/dev-only. |

## Run commands

```bash
make test        # install deps if needed, then pytest (backend + casegraph) + web unit tests; offline after install
make dev         # API on http://127.0.0.1:8000 (GET /api/health), web on http://127.0.0.1:3000/login
make e2e         # Playwright against make dev (roles, disclaimer, a11y, health)
make test-pg     # optional: docker compose up postgres; audit append-only on PostgreSQL
```

Default dev logins are `nurse1`, `physician1`, and `pharmacist1`. Their passwords come from `.env.example` (dev-only, synthetic).

## Decisions needed (none blocking)

- Session transport (httpOnly cookie vs bearer header): this is the engineer's choice, provided A03–A05 hold.
- Whether agreement-permitted non-synthetic data can ever reach the external adapter: this needs a future human approval plus a DECISIONS.md entry, and is not part of s0.
