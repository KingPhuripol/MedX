.PHONY: bootstrap verify smoke leakage-fixture status idea-docx

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

# สร้างไฟล์ .docx ของเอกสาร Senior Project IDEA — ต้องมี python-docx (pip install python-docx)
idea-docx:
	python3 tools/build_idea_docx.py docs/academic/PROJECT_IDEA.md docs/academic/SeniorProject_IDEA.docx
