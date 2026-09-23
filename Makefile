.PHONY: bootstrap verify smoke test demo api eval leakage-fixture idea-docx citations citations-online web opd-demo speech-local

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

# MedX OPD journey demo (DEC-0021): seed synthetic cases + role accounts, then serve
# http://127.0.0.1:8000/ (hub page with a link per station). Sign-in tokens are in
# .secrets/opd-demo-principals.json.
#   VOICE=1   use the loopback speech server (`make speech-local` in another terminal)
#   LLM=1     use an OpenAI-compatible model for the agents; set FRONT_DOOR_V2_PROVIDER_URL,
#             FRONT_DOOR_V2_PROVIDER_TOKEN, FRONT_DOOR_V2_PAID_BUDGET_USD and
#             FRONT_DOOR_V2_CALL_RESERVATION_USD in .env (model defaults to gpt-6-luna)
OPD_ENV = FRONT_DOOR_AUTH_MODE=token FRONT_DOOR_PRINCIPALS_FILE=.secrets/opd-demo-principals.json \
	FRONT_DOOR_DB=artifacts/opd-demo.sqlite3
ifneq ($(VOICE)$(LLM),)
OPD_ENV += FRONT_DOOR_ALLOW_EXTERNAL=true FRONT_DOOR_V2_TRANSPORT=openai_compatible FRONT_DOOR_V2_LOCAL_FREE=true \
	FRONT_DOOR_V2_BUDGET_DB=artifacts/opd-demo-budget.sqlite3
endif
ifdef VOICE
OPD_ENV += FRONT_DOOR_V2_SPEECH_URL=http://127.0.0.1:9100/v1 FRONT_DOOR_V2_SPEECH_MODEL=small
endif
ifdef LLM
OPD_ENV += FRONT_DOOR_V2_MODEL=$${FRONT_DOOR_V2_MODEL:-gpt-6-luna}
endif

opd-demo: web
	python3 scripts/opd_demo.py
	$(OPD_ENV) python3 -m uvicorn innovation.api.app:app --host 127.0.0.1 --port 8000

# Loopback Whisper transcription for the Voice Agent (downloads the model on first run).
speech-local:
	python3 scripts/local_speech.py
