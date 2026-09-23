"""DEC-0021 Phase 2: deterministic pre-dispensing check, the Pharma Agent and its harness."""
import json
import pytest
from innovation.v2.agents import AgentTool, run_agent, MAX_CALLS
from innovation.v2.pharmacy import PharmacyNote, check, review
from innovation.v2.store import DomainError
from test_v2_journey import T, client, h, post_fact  # noqa: F401 (fixture)


def ev(event_id, kind, value, state='KNOWN'):
    return {'fact': {'event_id': event_id, 'kind': kind, 'state': state, 'value': value if state == 'KNOWN' else None,
                     'supersedes_event_id': None}}


def order(event_id, drug, dose='500 mg', frequency='tid'):
    return ev(event_id, 'MEDICATION_ORDER', {'drug': drug, 'dose': dose, 'frequency': frequency})


def codes(result):
    return [(f.code, f.severity) for f in result.findings]


def test_allergy_class_match_needs_pharmacist_review():
    result = check([ev('a', 'ALLERGY', 'แพ้ penicillin ผื่นขึ้น'), order('o', 'Amoxicillin')])
    assert result.status == 'NEEDS_PHARMACIST_REVIEW'
    assert ('ALLERGY_MATCH', 'major') in codes(result)
    assert result.findings[0].evidence_ids == ['o', 'a']


def test_cross_reactivity_interaction_and_duplicate_are_flagged():
    events = [ev('a', 'ALLERGY', 'amoxicillin'), ev('m', 'MEDICATION', 'Warfarin 3 mg od'),
              order('o1', 'cefalexin'), order('o2', 'ibuprofen'), order('o3', 'naproxen')]
    found = codes(check(events))
    assert ('ALLERGY_CROSS_REACTIVITY', 'moderate') in found
    assert ('INTERACTION', 'major') in found          # warfarin + NSAID
    assert ('DUPLICATE_THERAPY', 'moderate') in found  # two NSAIDs


def test_clean_order_is_valid_but_unknown_allergy_is_not():
    assert check([ev('a', 'ALLERGY', 'ไม่มี'), order('o', 'paracetamol')]).status == 'VALID'
    unasked = check([ev('a', 'ALLERGY', None, state='UNKNOWN'), order('o', 'paracetamol')])
    assert unasked.status == 'INSUFFICIENT_INFORMATION'  # missing is not negative
    assert check([ev('a', 'ALLERGY', 'none'), order('o', 'unobtainium')]).status == 'NEEDS_PHARMACIST_REVIEW'
    assert check([ev('a', 'ALLERGY', 'none'), order('o', 'paracetamol', dose=None)]).findings[0].code == 'INCOMPLETE_ORDER'
    assert check([ev('a', 'ALLERGY', 'none')]).status == 'NO_ORDERS'


class Scripted:
    """A function-calling provider that replays scripted model turns."""
    capabilities = frozenset({'tools'})

    def __init__(self, *steps):
        self.steps, self.seen = list(steps), []

    def tool_step(self, messages, tools, output):
        self.seen.append([t['function']['name'] for t in tools])
        return self.steps.pop(0)


def calls(*names):
    return {'message': {'role': 'assistant', 'content': None},
            'tool_calls': [{'id': str(i), 'name': n, 'arguments': json.dumps({'drug': 'x'} if n == 'lookup_formulary' else {})}
                           for i, n in enumerate(names)]}


EVENTS = [ev('a', 'ALLERGY', 'none'), order('o', 'paracetamol')]


def test_harness_runs_tools_and_agent_can_only_escalate():
    provider = Scripted(calls('get_orders', 'get_rule_findings'),
                        {'final': {'summary': 'ตรวจแล้ว', 'additional_findings': [
                            {'severity': 'info', 'message': 'ยืนยันน้ำหนักตัว', 'evidence_ids': ['o']}]}})
    result, summary, trace = review(provider, EVENTS)
    assert [t.tool for t in trace] == ['get_orders', 'get_rule_findings'] and summary == 'ตรวจแล้ว'
    assert result.status == 'NEEDS_PHARMACIST_REVIEW' and result.findings[-1].source == 'agent'


def test_harness_rejects_unregistered_tools_budget_and_invented_evidence():
    with pytest.raises(DomainError) as denied:
        review(Scripted(calls('dispense_now')), EVENTS)
    assert denied.value.code == 'TOOL_FORBIDDEN'
    with pytest.raises(DomainError) as budget:
        review(Scripted(*[calls('get_orders')] * (MAX_CALLS + 1)), EVENTS)
    assert budget.value.code == 'TOOL_BUDGET_EXCEEDED'
    with pytest.raises(DomainError) as invented:
        review(Scripted({'final': {'summary': 'x', 'additional_findings': [
            {'severity': 'moderate', 'message': 'y', 'evidence_ids': ['made-up']}]}}), EVENTS)
    assert invented.value.code == 'INVALID_EVIDENCE_REFERENCE'
    with pytest.raises(DomainError) as malformed:
        review(Scripted({'final': {'additional_findings': []}}), EVENTS)
    assert malformed.value.code == 'INVALID_PROVIDER_OUTPUT'


def test_offline_provider_runs_every_argument_free_tool():
    tools = [AgentTool('a', 'a', lambda: 1), AgentTool('b', 'b', lambda drug: drug,
             {'type': 'object', 'properties': {'drug': {'type': 'string'}}, 'required': ['drug']})]
    note, trace = run_agent(type('Mock', (), {'capabilities': frozenset()})(), system='', context={}, tools=tools,
                            output=PharmacyNote, offline=lambda r: {'summary': str(r)})
    assert [t.tool for t in trace] == ['a'] and note.summary == "{'a': 1}"


def test_pharmacy_endpoints_roles_and_audit(client):
    c = client
    c.post('/v2/encounters', headers=h('nurse'), json={'encounter_id': 'opd', 'age': 40, 'care_context': 'OPD_ADULT_GENERAL'})
    post_fact(c, 'nurse', 'a', 'ALLERGY', 'แพ้ penicillin', 0)
    post_fact(c, 'doctor', 'o1', 'MEDICATION_ORDER', {'drug': 'amoxicillin', 'dose': '500 mg', 'frequency': 'tid'}, 1)
    checked = c.get('/v2/encounters/opd/pharmacy-check', headers=h('pharm')).json()
    assert checked['status'] == 'NEEDS_PHARMACIST_REVIEW' and checked['orders'][0]['event_id'] == 'o1'
    assert c.get('/v2/encounters/opd/pharmacy-check', headers=h('nurse')).status_code == 403
    assert c.post('/v2/encounters/opd/pharmacy-review', headers=h('doctor')).status_code == 403
    reviewed = c.post('/v2/encounters/opd/pharmacy-review', headers=h('pharm')).json()
    assert reviewed['agent']['status'] == 'COMPLETED' and reviewed['agent']['trace']
    assert reviewed['findings'][0]['code'] == 'ALLERGY_MATCH'
    audit = c.get('/v2/encounters/opd/audit?limit=100', headers=h('pharm')).json()['items']
    assert any(a['event'] == 'PHARMACY_AGENT_RUN' and a['verdict'] == 'NEEDS_PHARMACIST_REVIEW' for a in audit)


def test_chat_completions_tool_step_round_trip_through_the_gateway():
    from innovation.gateway.workflow import WorkflowGateway
    from innovation.v2.compatible import CompatibleProvider
    from innovation.v2.providers import ExternalConfig
    from innovation.v2.store import Store
    provider = CompatibleProvider(ExternalConfig('http://localhost:9000/v1', '', 'gpt-6-luna', 0, 0), Store(),
                                  ['tools'], local_free=True)
    replies = [
        {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None, 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': 'lookup_formulary', 'arguments': '{"drug": "amoxicillin"}'}}]}}]},
        {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'summary': 'ok'})}}]}]
    sent = []
    provider.transport = lambda path, json: (sent.append(json), replies.pop(0))[1]
    result, summary, trace = review(WorkflowGateway(provider), EVENTS)
    assert summary == 'ok' and [t.tool for t in trace] == ['lookup_formulary']
    assert sent[0]['max_completion_tokens'] and sent[0]['tools'][0]['type'] == 'function'
    assert sent[1]['messages'][-1] == {'role': 'tool', 'tool_call_id': 'c1', 'content': json.dumps(
        {'atc': 'J01CA04', 'class': 'penicillin', 'chembl': 'CHEMBL1082', 'th': 'อะม็อกซีซิลลิน'}, ensure_ascii=False)}
