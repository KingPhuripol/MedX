.PHONY: bootstrap verify smoke leakage-fixture status

bootstrap:
	bash scripts/bootstrap.sh

verify:
	python3 scripts/verify_harness.py

smoke:
	bash scripts/run_smoke_test.sh

leakage-fixture:
	python3 scripts/temporal_leakage_audit.py tests/fixtures/patient_journey/valid.json --as-of 2026-01-01T09:15:00Z

status:
	python3 scripts/project_status.py

