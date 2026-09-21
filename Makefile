.PHONY: bootstrap verify smoke test demo api eval leakage-fixture idea-docx citations citations-online web

bootstrap:
	bash scripts/bootstrap.sh

verify:
	python3 scripts/verify_harness.py

smoke:
	bash scripts/run_smoke_test.sh

leakage-fixture:
	python3 scripts/temporal_leakage_audit.py tests/fixtures/patient_journey/valid.json --as-of 2026-01-01T09:15:00Z

# Offline consistency pass over the literature registry: the APA string, the structured
# fields and the identifiers must agree.
citations:
	python3 scripts/verify_citations.py

# Re-fetch every ACCEPTED reference from Crossref, the arXiv API or PubMed and diff it
# against the registry. Needs network; deliberately kept out of the smoke test. Run this
# before the Proposal freeze on 29 Sep.
citations-online:
	python3 scripts/verify_citations.py --online

# สร้างไฟล์ .docx ของเอกสาร Senior Project IDEA — ต้องมี python-docx (pip install python-docx)
idea-docx:
	python3 tools/build_idea_docx.py docs/academic/PROJECT_IDEA.md docs/academic/SeniorProject_IDEA.docx

# Contract, gateway, Front Door and API tests — needs `pip install -r requirements.txt`
test:
	python3 -m pytest tests/ -q

# Offline synthetic demonstration of the Clinical Front Door (release stage 1)
demo:
	python3 -m innovation.demo

# Front Door API + UI. API docs at /docs, screens at /ui/
# Optional: FRONT_DOOR_PROVIDER=mock|baseline  FRONT_DOOR_DB=path.sqlite3  FRONT_DOOR_AUDIT_LOG=audit.jsonl
api:
	python3 -m uvicorn innovation.api.app:app --reload

# Frozen synthetic evaluation of the Front Door (reports rates; decides no pass/fail)
eval:
	python3 -m innovation.evaluation

# Build both frontends (nurse.html, platform.html) that the API serves at /nurse and /platform.
web:
	cd innovation/workspace && npm run build
