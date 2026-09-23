from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4
from innovation.v2.models import (ClinicalFact, CaseRevision, ClinicalDraft, JOURNEY_KINDS, now)
from innovation.v2.safety import screen_case
from innovation.v2.store import DomainError, digest
from innovation.v2.runtime import DESIGNS, validate_content


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    workspace: str = "default"


assert JOURNEY_KINDS == {"MEDICATION_ORDER", "DISPENSE", "RETURN_PRECAUTION", "DISPOSITION"}, "update the queue SQL staleness list"
STAGES = ("INTAKE", "DOCTOR_REVIEW", "PHARMACY", "PHARMACY_HOLD", "AWAITING_DISPOSITION",
          "DISPOSITION_HOME", "DISPOSITION_REFER", "DISPOSITION_OBSERVE")


class Service:
    def __init__(self, store, runtime):
        self.store, self.runtime = store, runtime

    def require(self, principal, roles):
        if principal.role not in roles:
            raise DomainError(403, "ROLE_FORBIDDEN")

    def audit(self, encounter_id, event, actor, **details):
        """Append a payload-minimised, immutable audit event.

        Clinical text remains in its source record. The audit stream contains stable
        references, versions and actor identity so a reviewer can reconstruct what
        happened without duplicating sensitive payloads.
        """
        self.store.append("audit", encounter_id, {
            "event": event,
            "encounter_id": encounter_id,
            "actor": actor.subject,
            "role": actor.role,
            "recorded_at": now().isoformat(),
            **details,
        })

    def command(self, actor, scope, key, body, fn):
        with self.store.transaction():
            cached = self.store.replay(actor.subject, scope, key, body)
            if cached is not None:
                return cached
            result = fn()
            self.store.remember(actor.subject, scope, key, body, result)
            return result

    def create(self, body, key, actor):
        self.require(actor, {"intake", "physician"})
        def perform():
            if self.store.all("encounter", body.encounter_id):
                raise DomainError(409, "ENCOUNTER_EXISTS")
            self.store.append("encounter", body.encounter_id, {**body.model_dump(), "workspace": actor.workspace})
            self.audit(body.encounter_id, "ENCOUNTER_CREATED", actor,
                       profile=body.profile, classification=body.classification,
                       care_context=body.care_context)
            return self.case(body.encounter_id)
        return self.command(actor, "create", key, body.model_dump(), perform)

    def case(self, encounter_id):
        records = self.store.all("encounter", encounter_id)
        if not records:
            raise DomainError(404, "ENCOUNTER_NOT_FOUND")
        events = self.store.all("event", encounter_id)
        return {**records[0], "case_revision": len(events), "events": events}

    def authorize_case(self, encounter_id, actor):
        if self.case(encounter_id).get('workspace', 'default') != actor.workspace:
            raise DomainError(404, 'ENCOUNTER_NOT_FOUND')

    def ensure_revision(self, encounter_id, revision):
        current = self.case_summary(encounter_id)["case_revision"]
        if current != revision:
            events = self.case(encounter_id)["events"]
            changed = sorted({event["fact"]["kind"] for event in events[max(0, revision):]})
            raise DomainError(409, "STALE_CASE_REVISION", {
                "expected_revision": revision,
                "current_revision": current,
                "changed_fact_types": changed,
            })

    def case_summary(self, encounter_id):
        records=self.store.all('encounter',encounter_id)
        if not records:
            raise DomainError(404,'ENCOUNTER_NOT_FOUND')
        with self.store.lock:
            count=self.store.conn.execute("SELECT count(*) FROM v2_records WHERE kind='event' AND resource=?",
                                          (encounter_id,)).fetchone()[0]
        return {**records[0],'case_revision':count}

    def append_event(self, encounter_id, body, actor):
        self.authorize_case(encounter_id, actor)
        fact = body.fact
        # DEC-0005/DEC-0021: physicians prescribe, pharmacists dispense; intake records evidence.
        self.require(actor, {"DISPENSE": {"pharmacist"}, "MEDICATION_ORDER": {"physician"}, "DISPOSITION": {"physician"},
                             "RETURN_PRECAUTION": {"physician"}}.get(fact.kind, {"intake", "physician"}))
        def perform():
            self.ensure_revision(encounter_id, body.expected_revision)
            events = self.case(encounter_id)["events"]
            check_record = None
            if fact.kind == "DISPENSE":
                orders = {e["fact"]["event_id"] for e in events if e["fact"]["kind"] == "MEDICATION_ORDER"}
                replaced = {e["fact"]["supersedes_event_id"] for e in events}
                if fact.value["order_event_id"] not in orders - replaced:
                    raise DomainError(422, "INVALID_ORDER_REFERENCE")
                check_record = self.dispense_gate(encounter_id, events, fact, actor)
            if fact.kind == "DISPOSITION" and self.escalation(encounter_id) and not fact.value.get("reason"):
                # Red flags outrank routine flow: overriding an escalation is a recorded, reasoned decision.
                raise DomainError(422, "DISPOSITION_REASON_REQUIRED")
            available_ids = {f.event_id for f in self.snapshot(encounter_id, fact.available_at_time).evidence}
            if not set(fact.conflicts_with_event_ids) <= available_ids:
                raise DomainError(422, 'INVALID_CONFLICT_TARGET')
            if any(e["fact"]["event_id"] == fact.event_id for e in events):
                raise DomainError(409, "DUPLICATE_EVENT")
            if fact.supersedes_event_id:
                old = next((ClinicalFact.model_validate(e["fact"]) for e in events if e["fact"]["event_id"] == fact.supersedes_event_id), None)
                if old is None or old.kind != fact.kind:
                    raise DomainError(422, "INVALID_CORRECTION_TARGET")
                if any(e["fact"]["supersedes_event_id"] == old.event_id for e in events):
                    raise DomainError(409, "ALREADY_SUPERSEDED")
                if fact.available_at_time < old.available_at_time:
                    raise DomainError(422, "BACKDATED_CORRECTION")
            self.store.append("event", encounter_id, {"fact": fact.model_dump(mode="json"),
                "actor": actor.subject, "recorded_at": now().isoformat(),
                **({"pharmacy_check": check_record} if fact.kind == "DISPENSE" else {})})
            self.audit(encounter_id, "EVIDENCE_APPENDED", actor,
                       event_id=fact.event_id, fact_kind=fact.kind,
                       case_revision=body.expected_revision + 1,
                       supersedes_event_id=fact.supersedes_event_id)
            return self.case(encounter_id)
        return self.command(actor, f"event:{encounter_id}", body.idempotency_key, body.model_dump(mode="json"), perform)

    def snapshot(self, encounter_id, decision_time):
        case = self.case(encounter_id)
        facts = [ClinicalFact.model_validate(e["fact"]) for e in case["events"]]
        eligible = [f for f in facts if f.available_at_time <= decision_time
                    and f.kind != "LABEL" and f.kind not in JOURNEY_KINDS]
        superseded = {f.supersedes_event_id for f in eligible if f.supersedes_event_id}
        evidence = [f for f in eligible if f.event_id not in superseded]
        timepoint = "T1" if any(f.kind in {"LAB", "REPORT"} for f in evidence) else "T0"
        payload = {"encounter_id": encounter_id, "case_revision": case["case_revision"],
            "decision_time": decision_time.isoformat(), "timepoint": timepoint,
            "care_context": case.get("care_context", "ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC"),
            "evidence": [f.model_dump(mode="json") for f in evidence]}
        return CaseRevision(**payload, checksum=digest(payload))

    def resolve(self, encounter_id, evidence_id, decision_time):
        # IDs only: never dereference arbitrary paths or URLs.
        item = next((f for f in self.snapshot(encounter_id, decision_time).evidence if f.event_id == evidence_id), None)
        if item is None:
            raise DomainError(404, "EVIDENCE_NOT_AVAILABLE")
        return item

    def turn(self, encounter_id, body, actor, design=None, cancel_check=None):
        self.authorize_case(encounter_id, actor)
        self.require(actor, {"intake", "physician"})
        scope = f"turn:{encounter_id}"
        payload = {**body.model_dump(mode="json"), "design_override": design.model_dump() if design else None}
        ticket_id = digest([actor.subject, scope, body.idempotency_key])
        # Reserve one case run under a short transaction; provider runs outside SQLite.
        with self.store.transaction():
            cached = self.store.replay(actor.subject, scope, body.idempotency_key, payload)
            if cached is not None:
                return cached
            if any(t["ticket_id"] == ticket_id for t in self.store.all("interrupted", encounter_id)):
                raise DomainError(409, "INTERRUPTED_RUN_USE_NEW_KEY")
            tickets = self.store.all("ticket", encounter_id)
            finished = {t['ticket_id'] for t in self.store.all("ticket_done", encounter_id)}
            if any(t['ticket_id'] == ticket_id and t['checksum'] != digest(payload) for t in tickets):
                raise DomainError(409, "IDEMPOTENCY_CONFLICT")
            if any(t['ticket_id'] not in finished for t in tickets):
                raise DomainError(409, "RUN_IN_PROGRESS")
            self.ensure_revision(encounter_id, body.expected_revision)
            snapshot = self.snapshot(encounter_id, body.decision_time)
            previous = self.store.all("run", encounter_id)
            interrupted = len(self.store.all("interrupted", encounter_id))
            self.store.append("ticket", encounter_id, {"ticket_id": ticket_id, "checksum": digest(payload),
                "encounter_id": encounter_id, "created_at": now().isoformat()})
            self.audit(encounter_id, "MODEL_RUN_STARTED", actor,
                       ticket_id=ticket_id, case_revision=snapshot.case_revision,
                       decision_time=snapshot.decision_time.isoformat(),
                       timepoint=snapshot.timepoint, intent=body.intent)
        run, content = self.runtime.execute(snapshot, body.text, design or DESIGNS[body.design_id],
            prior_calls=sum(len(r['trace']) for r in previous)+8*interrupted, prior_turns=len(previous)+interrupted,
            intent=body.intent, role=actor.role, cancel_check=cancel_check,
            history=[{'user': r.get('user_text', '')[:2000], 'assistant': r.get('response', '')[:2000]}
                     for r in previous[-6:] if r.get('actor') == actor.subject])
        with self.store.transaction():
            if cancel_check and cancel_check():
                run.status, run.error_code = 'FAILED_SAFE', 'JOB_CANCELLED'
                run.response = 'ยกเลิกงานแล้ว ไม่มีการบันทึกข้อเสนอหรือร่างจากงานนี้'
                run.proposals = []
                content = None
            if self.case(encounter_id)['case_revision'] != snapshot.case_revision:
                run.status, run.error_code = "NEEDS_REVIEW", "CASE_CHANGED_DURING_RUN"
                run.response = "ข้อมูลเคสเปลี่ยนระหว่างทำงาน กรุณาตรวจข้อมูลแล้วส่งใหม่"
                run.proposals = []
                content = None
            if content is not None:
                if content.differentials and actor.role != "physician":
                    content = content.model_copy(update={"differentials": []})
                screen = screen_case(snapshot)
                safety_escalation = bool(screen.missing_required) or any(
                    flag.state in {"TRIGGERED", "UNKNOWN"} for flag in screen.red_flags
                )
                if safety_escalation:
                    content = content.model_copy(update={
                        "uncertainty": content.uncertainty.model_copy(update={
                            "abstained": True,
                            "escalation_required": True,
                            "reasons": list(dict.fromkeys([
                                *content.uncertainty.reasons,
                                "Deterministic safety policy requires human escalation",
                            ])),
                        })
                    })
                from innovation.v2.graph import finish_artifact
                finish_artifact(run, content)
                draft = ClinicalDraft(draft_id=uuid4().hex, encounter_id=encounter_id,
                    case_revision=snapshot.case_revision, snapshot=snapshot, content=content,
                    screen=screen, provenance={**run.provenance},
                    created_by=actor.subject)
                self.store.append("draft", draft.draft_id, draft.model_dump(mode="json"))
                run.draft_id = draft.draft_id
            from innovation.v2.graph import finish_artifact
            finish_artifact(run, content)
            data = run.model_dump(mode="json")
            data.update(user_text=body.text, created_at=now().isoformat(), actor=actor.subject, intent=body.intent)
            self.store.append("run", encounter_id, data)
            self.audit(encounter_id, "MODEL_RUN_COMPLETED", actor,
                       run_id=run.run_id, draft_id=run.draft_id, status=run.status,
                       error_code=run.error_code, case_revision=snapshot.case_revision,
                       decision_time=snapshot.decision_time.isoformat(),
                       timepoint=snapshot.timepoint,
                       provider=run.provenance.get("provider"),
                       provider_version=run.provenance.get("provider_version"),
                       model=run.provenance.get("model"),
                       policy=run.provenance.get("policy"))
            self.store.append("ticket_done", encounter_id, {"ticket_id": ticket_id})
            self.store.remember(actor.subject, scope, body.idempotency_key, payload, data)
            return data

    def recover_interrupted(self):
        """Startup-only recovery for the documented single API process deployment.

        An uncertain prior inference is never automatically replayed.
        """
        with self.store.transaction():
            finished = {t['ticket_id'] for t in self.store.all('ticket_done')}
            for ticket in self.store.all('ticket'):
                if ticket['ticket_id'] not in finished:
                    self.store.append('ticket_done', ticket['encounter_id'], {'ticket_id': ticket['ticket_id'],
                        'error_code': 'PROCESS_INTERRUPTED'})
                    self.store.append('interrupted', ticket['encounter_id'], ticket)

    def accept_proposal(self, run_id, proposal_id, body, actor):
        self.require(actor, {'intake', 'physician'})
        run = self.run(run_id)
        proposal = next((p for p in run['proposals'] if p.get('proposal_id') == proposal_id), None)
        if not proposal or run['status'] != 'COMPLETED':
            raise DomainError(404, 'PROPOSAL_NOT_AVAILABLE')
        from innovation.v2.models import EventRequest
        scope = f'accept:{run_id}:{proposal_id}'
        def perform():
            self.ensure_revision(run['encounter_id'], body.expected_revision)
            if run['case_revision'] != body.expected_revision:
                raise DomainError(409, 'STALE_PROPOSAL')
            if self.store.all('accepted', scope):
                raise DomainError(409, 'PROPOSAL_ALREADY_ACCEPTED')
            # Nested service command uses the same transaction (savepoint), including every fact control.
            result = self.append_event(run['encounter_id'], EventRequest(expected_revision=body.expected_revision,
                idempotency_key='proposal-'+digest(scope), fact=body.fact), actor)
            self.store.append('accepted', scope, {'actor': actor.subject, 'event_id': body.fact.event_id})
            return result
        return self.command(actor, scope, body.idempotency_key, body.model_dump(mode='json'), perform)

    def accept_proposals(self, run_id, body, actor):
        """Validate against one base revision and commit all reviewed facts atomically.

        Event-count revisions remain compatible with existing clients. A batch can
        advance that revision by several events, but no intermediate state commits.
        """
        self.require(actor, {'intake', 'physician'})
        from innovation.v2.models import EventRequest
        scope = f'accept-batch:{run_id}'

        def perform():
            run = self.run(run_id)
            self.ensure_revision(run['encounter_id'], body.expected_revision)
            if run['status'] != 'COMPLETED' or run['case_revision'] != body.expected_revision:
                raise DomainError(409, 'STALE_PROPOSAL')
            ids = [p.proposal_id for p in body.proposals]
            available = {p.get('proposal_id') for p in run['proposals']}
            if len(ids) != len(set(ids)) or not set(ids) <= available:
                raise DomainError(422, 'INVALID_PROPOSAL_SELECTION')
            for index, proposal in enumerate(body.proposals):
                accepted_scope = f'accept:{run_id}:{proposal.proposal_id}'
                if self.store.all('accepted', accepted_scope):
                    raise DomainError(409, 'PROPOSAL_ALREADY_ACCEPTED')
                self.append_event(run['encounter_id'], EventRequest(
                    expected_revision=body.expected_revision + index,
                    idempotency_key='batch-' + digest([scope, body.idempotency_key, index]),
                    fact=proposal.fact), actor)
                self.store.append('accepted', accepted_scope, {
                    'actor': actor.subject, 'event_id': proposal.fact.event_id})
            return self.case(run['encounter_id'])

        return self.command(actor, scope, body.idempotency_key,
                            body.model_dump(mode='json'), perform)

    def draft_evidence(self, draft_id, evidence_id, actor):
        draft = self.draft(draft_id, actor)
        evidence = next((f for f in draft['snapshot']['evidence']
                         if f['event_id'] == evidence_id), None)
        if evidence is None:
            raise DomainError(404, 'EVIDENCE_NOT_AVAILABLE')
        return evidence

    def run(self, run_id):
        import json
        with self.store.lock:
            row=self.store.conn.execute("SELECT payload FROM v2_records WHERE kind='run' AND json_extract(payload,'$.run_id')=?",(run_id,)).fetchone()
        result=json.loads(row[0]) if row else None
        if result is None:
            raise DomainError(404, "RUN_NOT_FOUND")
        return result

    def draft(self, draft_id, actor):
        versions = self.store.all("draft", draft_id)
        if not versions:
            raise DomainError(404, "DRAFT_NOT_FOUND")
        latest = versions[-1]
        self.authorize_case(latest['encounter_id'], actor)
        reviews = self.store.all("review", draft_id)
        events = self.case(latest['encounter_id'])['events']
        stale = latest['case_revision'] > len(events) or any(
            e['fact']['kind'] not in JOURNEY_KINDS for e in events[latest['case_revision']:])
        with self.store.lock:
            newest=self.store.conn.execute("SELECT resource FROM v2_records WHERE kind='draft' AND json_extract(payload,'$.encounter_id')=? ORDER BY sequence DESC LIMIT 1",(latest['encounter_id'],)).fetchone()
        superseded=bool(newest and newest[0] != draft_id)
        last = reviews[-1] if reviews else None
        confirmed = bool(last and last['action'] == 'CONFIRM' and last['draft_revision'] == latest['draft_revision'])
        status = "STALE" if stale else ("SUPERSEDED" if superseded else (last['action'] if last else "PENDING_REVIEW"))
        result = {**latest, "status": status, "effective": confirmed and not stale and not superseded,
            "review_sequence": len(reviews), "reviews": reviews, "versions": versions}
        if actor.role != 'physician':
            # Work on a copy, never overwrite stored clinical content.
            for record in [result, *result['versions']]:
                record['content'] = {**record['content'], 'differentials': []}
        return result

    def dispense_gate(self, encounter_id, events, fact, actor):
        """Dispensing needs a confirmed hand-off; dispensing over rule findings needs a reason and acknowledgement."""
        from innovation.v2.pharmacy import check
        result = check(events)
        oid = fact.value["order_event_id"]
        relevant = sorted({f.code for f in result.findings if f.order_event_id in {oid, None}})
        if fact.value["outcome"] == "DISPENSED":
            drafts = self.drafts(encounter_id, actor)
            if not drafts or not drafts[-1]["effective"] or drafts[-1]["status"] != "CONFIRM":
                raise DomainError(409, "HANDOFF_NOT_CONFIRMED")
            if relevant and (not fact.value.get("reason") or set(relevant) - set(fact.value.get("acknowledged_findings", []))):
                raise DomainError(422, "OVERRIDE_REASON_REQUIRED", {"findings": relevant})
        return {"status": result.status, "formulary_version": result.formulary_version, "finding_codes": relevant}

    def pharmacy_check(self, encounter_id, actor):
        from innovation.v2.pharmacy import check
        self.require(actor, {"pharmacist", "physician"})
        self.authorize_case(encounter_id, actor)
        return check(self.case(encounter_id)["events"]).model_dump(mode="json")

    def pharmacy_review(self, encounter_id, actor):
        """Pharma Agent run: rule floor plus a model note. It records a run, never a dispense."""
        from innovation.v2.pharmacy import check, review
        self.require(actor, {"pharmacist"})
        self.authorize_case(encounter_id, actor)
        case = self.case(encounter_id)
        provider = self.runtime.provider
        agent = {"run_id": uuid4().hex, "provider": provider.name, "model": provider.model_version,
                 "case_revision": case["case_revision"], "created_at": now().isoformat()}
        try:
            result, summary, trace = review(provider, case["events"])
            agent.update(status="COMPLETED", summary=summary, trace=[t.model_dump(mode="json") for t in trace])
        except DomainError as exc:
            result = check(case["events"])
            agent.update(status="FAILED_SAFE", error_code=exc.code, summary=None, trace=[])
        self.store.append("pharmacy_review", encounter_id, {**agent, "status_verdict": result.status,
            "formulary_version": result.formulary_version, "findings": [f.model_dump() for f in result.findings]})
        self.audit(encounter_id, "PHARMACY_AGENT_RUN", actor, run_id=agent["run_id"], agent_status=agent["status"],
                   verdict=result.status, model=agent["model"], provider=agent["provider"],
                   case_revision=case["case_revision"])
        return {**result.model_dump(mode="json"), "agent": agent}

    def passport(self, encounter_id, actor, as_of=None):
        from innovation.v2.passport import build
        self.require(actor, {"intake", "physician", "pharmacist"})
        self.authorize_case(encounter_id, actor)
        return build(self, encounter_id, actor, as_of)

    def passport_assist(self, encounter_id, actor):
        """Passport Agent run: a take-home summary and proposed precautions for the physician."""
        from innovation.v2.passport import assist
        self.require(actor, {"physician"})
        passport = self.passport(encounter_id, actor)
        provider = self.runtime.provider
        run = {"run_id": uuid4().hex, "provider": provider.name, "model": provider.model_version,
               "case_revision": self.case_summary(encounter_id)["case_revision"], "created_at": now().isoformat()}
        try:
            note, trace = assist(provider, passport)
            run.update(status="COMPLETED", **note.model_dump(), trace=[t.model_dump(mode="json") for t in trace])
        except DomainError as exc:
            run.update(status="FAILED_SAFE", error_code=exc.code, patient_summary=None,
                       proposed_return_precautions=[], trace=[])
        self.store.append("passport_assist", encounter_id, run)
        self.audit(encounter_id, "PASSPORT_AGENT_RUN", actor, run_id=run["run_id"], agent_status=run["status"],
                   model=run["model"], provider=run["provider"], case_revision=run["case_revision"])
        return run

    def dashboard(self, actor):
        """Operational view of the OPD journey for this workspace: where cases wait and for how long."""
        from collections import Counter
        from datetime import datetime
        from statistics import median
        self.require(actor, {"physician", "pharmacist", "evaluator"})
        # ponytail: recomputes per request over the whole workspace; fine at pilot scale, add a rollup table if it grows.
        items = self.queue(actor, limit=10_000)["items"]
        at = lambda value: datetime.fromisoformat(value)
        waits = {"intake_to_draft": [], "draft_to_review": [], "review_to_dispense": []}
        urgency, agents = Counter(), Counter()
        for item in items:
            eid = item["encounter_id"]
            audit = self.store.all("audit", eid)
            created = next((at(a["recorded_at"]) for a in audit if a["event"] == "ENCOUNTER_CREATED"), None)
            confirmed = next((at(a["recorded_at"]) for a in audit if a["event"] == "HUMAN_REVIEW_RECORDED" and a["action"] == "CONFIRM"), None)
            agents.update(a["event"] + ":" + a["agent_status"] for a in audit if a["event"].endswith("_AGENT_RUN"))
            with self.store.lock:
                rows = self.store.conn.execute("SELECT payload FROM v2_records WHERE kind='draft' AND json_extract(payload,'$.encounter_id')=? ORDER BY sequence", (eid,)).fetchall()
            drafts = [json.loads(r[0]) for r in rows]
            dispensed = [at(e["recorded_at"]) for e in self.store.all("event", eid)
                         if e["fact"]["kind"] == "DISPENSE" and (e["fact"]["value"] or {}).get("outcome") == "DISPENSED"]
            if drafts:
                screen = drafts[-1].get("screen") or {}
                urgency[screen.get("urgency_floor", "UNSCREENED")] += 1
                if created:
                    waits["intake_to_draft"].append(at(drafts[0]["created_at"]) - created)
                if confirmed:
                    waits["draft_to_review"].append(confirmed - at(drafts[0]["created_at"]))
            if confirmed and dispensed and item["journey_stage"] in {"AWAITING_DISPOSITION", "DISPOSITION_HOME"}:
                waits["review_to_dispense"].append(max(dispensed) - confirmed)
        minutes = lambda values: {"n": len(values), "median_minutes": round(median(v.total_seconds() for v in values) / 60, 1) if values else None}
        stages = Counter(item["journey_stage"] for item in items)
        return {"generated_at": now().isoformat(), "total": len(items),
                "stages": {s: stages[s] for s in STAGES}, "escalated": sum(bool(item["escalation"]) for item in items),
                "waits": {k: minutes(v) for k, v in waits.items()},
                "urgency_floor": dict(urgency),
                "needs_attention": sum(item["attention"]["needs_attention"] for item in items),
                "agent_runs": dict(agents)}

    def journey_stage(self, encounter_id, handoff):
        """OPD journey stage derived from handoff status and journey facts; no extra state.

        Going home is never inferred: once pharmacy work is done the case waits for the
        physician's DISPOSITION record (DEC-0005).
        """
        if handoff == 'NO_DRAFT':
            return 'INTAKE'
        if handoff != 'CONFIRMED':
            return 'DOCTOR_REVIEW'
        facts = [e['fact'] for e in self.store.all('event', encounter_id)]
        replaced = {f['supersedes_event_id'] for f in facts}
        facts = [f for f in facts if f['event_id'] not in replaced and f['state'] == 'KNOWN']
        latest = {f['value']['order_event_id']: f['value']['outcome'] for f in facts if f['kind'] == 'DISPENSE'}
        outcomes = [latest.get(f['event_id']) for f in facts if f['kind'] == 'MEDICATION_ORDER']
        if any(o in {'HELD', 'CONTACT_PRESCRIBER'} for o in outcomes):
            return 'PHARMACY_HOLD'
        if any(o != 'DISPENSED' for o in outcomes):
            return 'PHARMACY'
        dispositions = [f for f in facts if f['kind'] == 'DISPOSITION']
        return 'DISPOSITION_' + dispositions[-1]['value']['decision'] if dispositions else 'AWAITING_DISPOSITION'

    def escalation(self, encounter_id):
        """Red flags and urgency floor from the latest draft's deterministic screen; they outrank the stage."""
        with self.store.lock:
            row = self.store.conn.execute("SELECT payload FROM v2_records WHERE kind='draft' AND json_extract(payload,'$.encounter_id')=? ORDER BY sequence DESC LIMIT 1", (encounter_id,)).fetchone()
        screen = (json.loads(row[0]).get('screen') or {}) if row else {}
        reasons = [f"{flag['code']}:{flag['state']}" for flag in screen.get('red_flags', []) if flag.get('state') in {'TRIGGERED', 'UNKNOWN'}]
        if screen.get('urgency_floor') in {'URGENT_REVIEW', 'IMMEDIATE_REVIEW'}:
            reasons.append(screen['urgency_floor'])
        return reasons

    def queue(self, actor, q='', status='', offset=0, limit=25, stage=''):
        """The case list with the attention fields the queue needs, scoped to the actor's workspace."""
        import json
        with self.store.lock:
            rows = self.store.conn.execute("""WITH
                counts AS (SELECT resource,count(*) revision FROM v2_records WHERE kind='event' GROUP BY resource),
                events AS (SELECT resource,json_extract(payload,'$.fact.kind') fact_kind,
                    row_number() OVER (PARTITION BY resource ORDER BY sequence) n FROM v2_records WHERE kind='event'),
                last_draft AS (SELECT json_extract(payload,'$.encounter_id') encounter,max(sequence) seq FROM v2_records WHERE kind='draft' GROUP BY encounter),
                last_review AS (SELECT resource,max(sequence) seq FROM v2_records WHERE kind='review' GROUP BY resource),
                cases AS (SELECT e.resource,e.payload,e.sequence,COALESCE(c.revision,0) revision,
                    CASE WHEN d.sequence IS NULL THEN 'NO_DRAFT'
                    WHEN json_extract(d.payload,'$.case_revision')>COALESCE(c.revision,0) OR EXISTS(SELECT 1 FROM events v
                        WHERE v.resource=e.resource AND v.n>json_extract(d.payload,'$.case_revision')
                        AND v.fact_kind NOT IN ('MEDICATION_ORDER','DISPENSE','RETURN_PRECAUTION','DISPOSITION')) THEN 'STALE'
                    WHEN json_extract(r.payload,'$.action')='CONFIRM' AND json_extract(r.payload,'$.draft_revision')=json_extract(d.payload,'$.draft_revision') THEN 'CONFIRMED'
                    WHEN json_extract(r.payload,'$.action')='REJECT' THEN 'REJECTED' ELSE 'PENDING' END handoff_status
                    FROM v2_records e LEFT JOIN counts c ON c.resource=e.resource
                    LEFT JOIN last_draft ld ON ld.encounter=e.resource LEFT JOIN v2_records d ON d.sequence=ld.seq
                    LEFT JOIN last_review lr ON lr.resource=d.resource LEFT JOIN v2_records r ON r.sequence=lr.seq
                    WHERE e.kind='encounter' AND COALESCE(json_extract(e.payload,'$.workspace'),'default')=?
                    AND instr(lower(e.resource),lower(?))>0)
                SELECT * FROM cases WHERE (?='' OR handoff_status=?) ORDER BY sequence DESC LIMIT ? OFFSET ?""",
                (actor.workspace,q,status,status,-1 if stage else limit+1,0 if stage else offset)).fetchall()
        stages={row['resource']:self.journey_stage(row['resource'],row['handoff_status']) for row in rows}
        if stage:
            rows=[row for row in rows if stages[row['resource']]==stage][offset:offset+limit+1]
        items=[]
        for row in rows[:limit]:
            encounter_id=row['resource']
            revision=row['revision']
            pending=0
            for run in self.store.all('run', encounter_id):
                if run.get('status')!='COMPLETED' or run.get('case_revision')!=revision:
                    continue
                for proposal in run.get('proposals',[]):
                    proposal_id=proposal.get('proposal_id')
                    if proposal_id and not self.store.all('accepted', f"accept:{run['run_id']}:{proposal_id}"):
                        pending+=1
            with self.store.lock:
                active=self.store.conn.execute("""SELECT status FROM v2_jobs
                    WHERE encounter=? AND status IN ('queued','running')
                    ORDER BY created_at DESC LIMIT 1""",(encounter_id,)).fetchone()
            handoff=row['handoff_status']
            attention={'pending_proposal_count':pending,
                'active_job_status':active['status'] if active else None,
                'stale_draft':handoff=='STALE',
                'needs_attention':bool(pending or active or handoff in {'PENDING','STALE','REJECTED'})}
            escalation=self.escalation(encounter_id)
            attention['needs_attention']=attention['needs_attention'] or (bool(escalation) and not stages[encounter_id].startswith('DISPOSITION_'))
            items.append({**json.loads(row['payload']),'case_revision':revision,
                'handoff_status':handoff,'journey_stage':stages[encounter_id],'escalation':escalation,'attention':attention})
        return {'items':items,
                'next_offset':offset+limit if len(rows)>limit else None}

    def drafts(self, encounter_id, actor):
        self.case(encounter_id)
        with self.store.lock:
            ids=[r[0] for r in self.store.conn.execute("SELECT resource FROM v2_records WHERE kind='draft' AND json_extract(payload,'$.encounter_id')=? GROUP BY resource ORDER BY min(sequence)",(encounter_id,)).fetchall()]
        return [self.draft(i, actor) for i in ids]

    def review(self, draft_id, body, actor):
        self.require(actor, {"physician"})
        def perform():
            current = self.draft(draft_id, actor)
            if current['status'] == 'SUPERSEDED':
                raise DomainError(409, 'DRAFT_SUPERSEDED')
            self.ensure_revision(current['encounter_id'], body.expected_revision)
            if current['status'] == 'STALE':
                raise DomainError(409, "STALE_DRAFT")
            if current['draft_revision'] != body.draft_revision or current['review_sequence'] != body.expected_review_sequence:
                raise DomainError(409, "STALE_REVIEW")
            if body.action == 'MODIFY':
                snapshot = CaseRevision.model_validate(current['snapshot'])
                validate_content(body.content, snapshot, self.runtime.allow_differential)
                version = ClinicalDraft.model_validate(
                    {k: current[k] for k in ClinicalDraft.model_fields if k in current})
                version = version.model_copy(update={'draft_revision': version.draft_revision+1,
                    'content': body.content, 'created_by': actor.subject, 'created_at': now()})
                self.store.append('draft', draft_id, version.model_dump(mode='json'))
            self.store.append('review', draft_id, {'action': body.action, 'actor': actor.subject,
                'role': actor.role, 'draft_revision': body.draft_revision,
                'reason_code': body.reason_code, 'reason': body.reason,
                'reviewed_at': now().isoformat()})
            self.audit(current['encounter_id'], "HUMAN_REVIEW_RECORDED", actor,
                       draft_id=draft_id, draft_revision=body.draft_revision,
                       action=body.action, reason_code=body.reason_code,
                       reason=body.reason,
                       case_revision=body.expected_revision,
                       model=current.get('provenance', {}).get('model'),
                       provider=current.get('provenance', {}).get('provider'),
                       policy=(current.get('screen') or {}).get('policy_version'))
            return self.draft(draft_id, actor)
        self.command(actor, f'review:{draft_id}', body.idempotency_key, body.model_dump(mode='json'), perform)
        return self.draft(draft_id, actor)
