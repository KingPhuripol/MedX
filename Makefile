# Clinical Front Door — slice s0 skeleton. Research prototype — not for clinical use.
SHELL := /bin/bash
PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python
API_PORT ?= 8000
WEB_PORT ?= 3000
PG_URL = postgresql+psycopg://frontdoor:$${POSTGRES_PASSWORD:-frontdoor_dev_only}@127.0.0.1:55432/frontdoor
API_ORIGIN ?= http://127.0.0.1:$(API_PORT)
export PYTHONPATH := $(CURDIR)/backend:$(CURDIR)
# Ports are overridable (slice s4 uses API_PORT=8104 WEB_PORT=3104); defaults unchanged.
API_PORT ?= 8000
WEB_PORT ?= 3000
MOBILE_PORT ?= 3002
export API_PORT WEB_PORT MOBILE_PORT

.PHONY: install test dev mobile-dev e2e e2e-pharma pharma-eval test-pg clean data audit eval-voice research-dry-run triage-eval eval-e1-dev eval-e1-test eval-i2-dev eval-i2-test care-eval

SEED ?= 20260926
OUT ?= data/synthetic/v1

install: $(VENV)/.installed web/node_modules/.installed mobile/node_modules/.installed

$(VENV)/.installed: requirements.lock
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ required")'
	@test -x $(PY) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
	@touch $@

web/node_modules/.installed: web/package-lock.json web/package.json
	cd web && npm ci --no-audit --no-fund
	@touch $@

mobile/node_modules/.installed: mobile/package-lock.json mobile/package.json
	cd mobile && npm ci --no-audit --no-fund
	@touch $@

## Unit/contract tests: pytest (backend + casegraph + data_factory, sockets blocked) + web Vitest + mobile Vitest/tsc.
test: install
	$(PY) -m pytest -q -rs
	cd web && npm test
	cd mobile && npm test && npm run typecheck

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
	cd web && API_ORIGIN=$(API_ORIGIN) npx next dev -H 127.0.0.1 -p $(WEB_PORT)

## v2c mobile scribe PWA: API on 127.0.0.1:$(API_PORT) + mobile on 127.0.0.1:$(MOBILE_PORT) (default 3002).
mobile-dev: install
	@set -a; if [ -f .env ]; then . ./.env; fi; set +a; \
	$(PY) -m app.seed || exit 1; \
	$(VENV)/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port $(API_PORT) & API_PID=$$!; \
	trap 'kill $$API_PID 2>/dev/null' EXIT INT TERM; \
	cd mobile && BACKEND_URL=$(API_ORIGIN) npx next dev -H 127.0.0.1 -p $(MOBILE_PORT)

## Browser tests (Playwright) against `make dev` (started automatically if not running).
e2e: install
	cd web && npx playwright install chromium && WEB_PORT=$(WEB_PORT) API_PORT=$(API_PORT) npx playwright test

## Pharma Agent (s5): inject + evaluate both modes -> slices/s5/eval/{results.json,injection_log.jsonl}.
pharma-eval: install
	$(PY) -m app.pharma.eval.run_eval --out slices/s5/eval

## Pharma page browser tests (slice ports 8105/3105; servers started automatically if not running).
e2e-pharma: install
	cd web && npx playwright install chromium && \
	API_PORT=8105 WEB_PORT=3105 npx playwright test e2e/pharma.spec.ts e2e/pharma-a11y.spec.ts

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

## s4 System Evaluation on synthetic fixtures -> slices/s4/eval/metrics_v1.json (offline, mock provider).
triage-eval: install
	$(PY) -m app.triage.evaluate

## e1 System Evaluation of S3 voice + S4 triage on S1r (needs `make data` output at the frozen tree sha).
## Unfrozen dev runs go to eval/results/e1/unfrozen/ with a scratch ledger; frozen runs record in eval/ledger/.
eval-e1-dev: $(VENV)/.installed
	$(PY) -m eval.adapters run --split dev

## Test split: refuses (exit 2, nothing written) unless all 4 e1 manifests are frozen; run once, then commit.
eval-e1-test: $(VENV)/.installed
	$(PY) -m eval.adapters run --split test

## i2 Case Graph vs single prompt (PROPOSAL Table 3.2 row "Case Graph"; synthetic, mock only).
## Unfrozen dev -> eval/results/i2/unfrozen/ (scratch ledger); frozen runs record in eval/ledger/.
eval-i2-dev: $(VENV)/.installed
	$(PY) -m eval_i2 run --split dev

## Test split: refuses (exit 2, nothing written) unless i2-cg-vs-sp-test-v1 is frozen; run once, then commit.
eval-i2-test: $(VENV)/.installed
	$(PY) -m eval_i2 run --split test

## s6 System Evaluation (mock baseline, synthetic, offline): SPLIT=dev|test -> slices/s6/eval/results_$(SPLIT)[_NNNN]/.
## Needs `make data` at the default seed (dataset tree hash must equal the manifest). The test manifest must be
## frozen and committed first; the test split runs once. Pages: make dev API_PORT=8106 WEB_PORT=3106 -> /physician/care
## s6r: DATASET=<dir> EVAL_ID=s6-care-<split>-NNNN; ids other than -0001 use the _NNNN file suffix. The v1 test split
## is retired (DECISIONS.md 2026-09-27): SPLIT=test needs DATASET=data/synthetic/s6r-heldout.
SPLIT ?= dev
DATASET ?= data/synthetic/v1
EVAL_ID ?= s6-care-$(SPLIT)-0001
S6_EVAL := slices/s6/eval
S6_SFX = $(if $(filter %-0001,$(EVAL_ID)),,_$(lastword $(subst -, ,$(EVAL_ID))))
S6_X = $(SPLIT)$(S6_SFX)
care-eval: install
	$(PY) -m app.care.evaluate --split $(SPLIT) --dataset "$(DATASET)" --evaluation-id $(EVAL_ID)
	$(PY) -m eval --ledger-dir $(S6_EVAL)/ledger run --manifest $(S6_EVAL)/manifest_$(S6_X).json \
	  --predictions $(S6_EVAL)/predictions_$(S6_X).jsonl --comparator $(S6_EVAL)/comparator_$(S6_X).jsonl \
	  --out $(S6_EVAL)/results_$(S6_X)

clean:
	rm -rf $(VENV) web/node_modules web/.next mobile/node_modules mobile/.next backend/dev.db
