from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from innovation.v2.models import (ClinicalFact, CaseRevision, ClinicalDraft, now, DraftContent)
from innovation.v2.safety import screen_case
from innovation.v2.store import DomainError, digest
from innovation.v2.runtime import DESIGNS, validate_content


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    workspace: str = "default"


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
        self.require(actor, {"intake", "physician"})
        def perform():
            self.ensure_revision(encounter_id, body.expected_revision)
            events = self.case(encounter_id)["events"]
            fact = body.fact
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
                "actor": actor.subject, "recorded_at": now().isoformat()})
            self.audit(encounter_id, "EVIDENCE_APPENDED", actor,
                       event_id=fact.event_id, fact_kind=fact.kind,
                       case_revision=body.expected_revision + 1,
                       supersedes_event_id=fact.supersedes_event_id)
            return self.case(encounter_id)
        return self.command(actor, f"event:{encounter_id}", body.idempotency_key, body.model_dump(mode="json"), perform)

    def snapshot(self, encounter_id, decision_time):
        case = self.case(encounter_id)
        facts = [ClinicalFact.model_validate(e["fact"]) for e in case["events"]]
        eligible = [f for f in facts if f.available_at_time <= decision_time and f.kind != "LABEL"]
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
                draft = ClinicalDraft(draft_id=uuid4().hex, encounter_id=encounter_id,
                    case_revision=snapshot.case_revision, snapshot=snapshot, content=content,
                    screen=screen, provenance={**run.provenance},
                    created_by=actor.subject)
                self.store.append("draft", draft.draft_id, draft.model_dump(mode="json"))
                run.draft_id = draft.draft_id
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
        stale = latest['case_revision'] != self.case(latest['encounter_id'])['case_revision']
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
            if current['case_revision'] != body.expected_revision:
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
