# Clinical Front Door — slice s0 skeleton. Research prototype — not for clinical use.
SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
API_PORT ?= 8000
WEB_PORT ?= 3000
PG_URL = postgresql+psycopg://frontdoor:$${POSTGRES_PASSWORD:-frontdoor_dev_only}@127.0.0.1:55432/frontdoor
export PYTHONPATH := $(CURDIR)/backend:$(CURDIR)

.PHONY: install test dev e2e test-pg clean data audit eval-voice research-dry-run

SEED ?= 20260926
OUT ?= data/synthetic/v1

install: $(VENV)/.installed web/node_modules/.installed

$(VENV)/.installed: requirements.lock
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ required")'
	@test -x $(PY) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
	@touch $@

web/node_modules/.installed: web/package-lock.json web/package.json
	cd web && npm ci --no-audit --no-fund
	@touch $@

## Unit/contract tests: pytest (backend + casegraph + data_factory, sockets blocked) + web Vitest.
test: install
	$(PY) -m pytest -q -rs
	cd web && npm test

## Research (s9): validate manifests + both Tier-0 CPU dry runs (synthetic, offline). No GPU, no downloads.
research-dry-run: install
	$(PY) scripts/validate_manifest.py research/manifests/*.json
	$(PY) -m research.train --config research/configs/stage2_connector.yaml --manifest research/manifests/dryrun-s2.json --dry-run
	$(PY) -m research.train --config research/configs/stage3_lora.yaml --manifest research/manifests/dryrun-s3.json --dry-run

## API on 127.0.0.1:$(API_PORT) (default 8000), web on 127.0.0.1:$(WEB_PORT) (default 3000); dev seed applied; loads .env if present.
dev: install
	@set -a; if [ -f .env ]; then . ./.env; fi; set +a; \
	$(PY) -m app.seed || exit 1; \
	$(VENV)/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port $(API_PORT) & API_PID=$$!; \
	trap 'kill $$API_PID 2>/dev/null' EXIT INT TERM; \
	cd web && API_ORIGIN=http://127.0.0.1:$(API_PORT) npx next dev -H 127.0.0.1 -p $(WEB_PORT)

## Browser tests (Playwright) against `make dev` (started automatically if not running).
e2e: install
	cd web && npx playwright install chromium && WEB_PORT=$(WEB_PORT) API_PORT=$(API_PORT) npx playwright test

## Optional: audit append-only on docker-compose PostgreSQL. Skips if Docker is unavailable.
test-pg: install
	@if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then \
	  echo "SKIPPED test_audit_append_only_pg: Docker daemon unavailable (non-gating)"; exit 0; fi; \
	docker compose config -q && docker compose up -d --wait postgres || exit 1; \
	TEST_PG_URL="$(PG_URL)" $(PY) -m pytest -q -rs -m pg; rc=$$?; \
	docker compose down; exit $$rc

## Synthetic case factory (slice s1): deterministic for a given SEED; output is gitignored.
## OUT must resolve strictly inside data/ or the temp dir; replacement happens in Python after that check.
data: $(VENV)/.installed
	$(PY) -m data_factory generate --seed $(SEED) --out "$(OUT)" --replace

## Leakage audit + schema + gold separation + identifier scan + manifest hashes + snapshot_items_after_T over OUT.
## Both steps always run; a STEP line is printed per step; exit is non-zero if either failed.
audit: $(VENV)/.installed
	@rc=0; \
	if $(PY) scripts/temporal_leakage_audit.py --dataset "$(OUT)"; then echo "STEP leakage: PASS"; else echo "STEP leakage: FAIL"; rc=1; fi; \
	if $(PY) -m data_factory audit --dataset "$(OUT)"; then echo "STEP factory: PASS"; else echo "STEP factory: FAIL"; rc=1; fi; \
	exit $$rc

## Voice intake system evaluation (mock rules, synthetic fixtures) -> slices/s3/eval/voice_intake_eval.json
eval-voice: install
	$(PY) -m app.voice.eval

clean:
	rm -rf $(VENV) web/node_modules web/.next backend/dev.db
