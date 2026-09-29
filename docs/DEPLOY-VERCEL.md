# Deploy the MedX public demo to Vercel

The owner approved this on 2026-09-29 (`docs/DECISIONS.md`, "Public Vercel demo: two links"). The demo uses the mock provider and synthetic data only, and it has no password. Deploying is done by the owner. Slice: `slices/d1/SPEC.md`.

## 1. Stage (from a clean checkout of the commit to publish)

```bash
git checkout <commit>                  # T1 grey/purple: main; U4 blue: factory/u4 after it passes
scripts/vercel_stage.sh ~/medx-vercel/t1    # outdir must be outside the repo; runs `make data` if missing
```

## 2. Deploy (Vercel builds remotely; do not use `--prebuilt` from macOS, because the vendored wheels would be for the wrong platform)

```bash
cd ~/medx-vercel/t1
vercel link --yes --scope kingphuripol --project medx-demo-t1
openssl rand -base64 48 | vercel env add SESSION_SECRET production
printf 1 | vercel env add PUBLIC_DEMO production
printf 1 | vercel env add NEXT_PUBLIC_PUBLIC_DEMO production    # build-time: the login page becomes the role picker
vercel deploy --prod
```

For the second link, repeat with `~/medx-vercel/u4` and `--project medx-demo-u4`. Use a different `SESSION_SECRET` for each project.

Env vars: `SESSION_SECRET` (at least 32 characters, required), `PUBLIC_DEMO=1` (`api/index.py` forces it anyway), `NEXT_PUBLIC_PUBLIC_DEMO=1`. Never set `GATEWAY_PROVIDER`, `GATEWAY_EXTERNAL_ENABLED` or `EXTERNAL_*`: the function refuses to start if any of them is set.

Smoke test after deploying:
- `curl https://<url>/api/health` should show `"default_provider":"mock"`.
- Open `/login`, choose Physician, then check that `/physician/care` lists `SYNE-*` cases and that `/pharmacist` shows 403.

## 3. Take down

```bash
vercel project rm medx-demo-t1      # removes the project and all its deployments (the owner does this, or on request)
```

## Verify locally before deploying (no Vercel account needed)

```bash
STAGE=/tmp/medx-stage; scripts/vercel_stage.sh $STAGE && cd $STAGE
python3.12 -m venv .venv-slim && .venv-slim/bin/pip install -r requirements.txt uvicorn
npm ci && NEXT_PUBLIC_PUBLIC_DEMO=1 API_ORIGIN=http://127.0.0.1:8117 npm run build
SESSION_SECRET=$(openssl rand -base64 48) DATABASE_URL=sqlite:///$STAGE/local.db \
  .venv-slim/bin/uvicorn --app-dir api index:app --host 127.0.0.1 --port 8117 &
API_ORIGIN=http://127.0.0.1:8117 npx next start -H 127.0.0.1 -p 3117 &
# from the repo's web/:
PUBLIC_DEMO_E2E=1 BASE_URL=http://127.0.0.1:3117 npx playwright test e2e/public-demo.spec.ts
```

`vercel build` also works without linking: create `.vercel/project.json` containing `{"projectId":"_local","orgId":"_local","settings":{"framework":"nextjs"}}`, then run it with `python3.12` and `pip3.12` on PATH.

## Limits

- State lives in each instance's `/tmp` SQLite. The cases, reviews, pharma runs and audit rows created in one instance may not appear in another, and they are lost when the instance is recycled.
- Sessions are signed cookies, so they survive an instance switch. An invalid or expired cookie sends the user back to the role picker.
- A session cannot be revoked before it expires (8 h). Rotating `SESSION_SECRET` ends all sessions.
