# Clinical Front Door — slice s0 skeleton. Research prototype — not for clinical use.
SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
PG_URL = postgresql+psycopg://frontdoor:$${POSTGRES_PASSWORD:-frontdoor_dev_only}@127.0.0.1:55432/frontdoor
export PYTHONPATH := $(CURDIR)/backend:$(CURDIR)

.PHONY: install test dev e2e test-pg clean

install: $(VENV)/.installed web/node_modules/.installed

$(VENV)/.installed: requirements.lock
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ required")'
	@test -x $(PY) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
	@touch $@

web/node_modules/.installed: web/package-lock.json web/package.json
	cd web && npm ci --no-audit --no-fund
	@touch $@

## Unit/contract tests: pytest (backend + casegraph, sockets blocked) + web Vitest.
test: install
	$(PY) -m pytest -q -rs
	cd web && npm test

## API on 127.0.0.1:8000, web on 127.0.0.1:3000 (dev seed applied; loads .env if present).
dev: install
	@set -a; if [ -f .env ]; then . ./.env; fi; set +a; \
	$(PY) -m app.seed || exit 1; \
	$(VENV)/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 & API_PID=$$!; \
	trap 'kill $$API_PID 2>/dev/null' EXIT INT TERM; \
	cd web && npm run dev

## Browser tests (Playwright) against `make dev` (started automatically if not running).
e2e: install
	cd web && npx playwright install chromium && npx playwright test

## Optional: audit append-only on docker-compose PostgreSQL. Skips if Docker is unavailable.
test-pg: install
	@if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then \
	  echo "SKIPPED test_audit_append_only_pg: Docker daemon unavailable (non-gating)"; exit 0; fi; \
	docker compose config -q && docker compose up -d --wait postgres || exit 1; \
	TEST_PG_URL="$(PG_URL)" $(PY) -m pytest -q -rs -m pg; rc=$$?; \
	docker compose down; exit $$rc

clean:
	rm -rf $(VENV) web/node_modules web/.next backend/dev.db
