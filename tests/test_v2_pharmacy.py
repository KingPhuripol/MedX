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


NONE = [ev('a', 'ALLERGY', 'ไม่มี'), ev('m', 'MEDICATION', 'ไม่มี')]


def test_clean_order_has_no_rule_findings_but_missing_history_is_not_clean():
    assert check(NONE + [order('o', 'paracetamol')]).status == 'NO_RULE_FINDINGS'
    unasked = check([ev('a', 'ALLERGY', None, state='UNKNOWN'), ev('m', 'MEDICATION', 'ไม่มี'), order('o', 'paracetamol')])
    assert unasked.status == 'INSUFFICIENT_INFORMATION'  # missing is not negative
    for meds in ([], [ev('m', 'MEDICATION', None, state='UNKNOWN')], [ev('m', 'MEDICATION', None, state='REFUSED')]):
        result = check([ev('a', 'ALLERGY', 'none'), *meds, order('o', 'clarithromycin')])
        assert result.status == 'INSUFFICIENT_INFORMATION' and result.findings[0].code == 'MEDICATION_HISTORY_UNKNOWN'
    assert check(NONE + [order('o', 'unobtainium')]).status == 'NEEDS_PHARMACIST_REVIEW'
    assert check(NONE + [order('o', 'paracetamol', dose=None)]).findings[0].code == 'INCOMPLETE_ORDER'
    assert check(NONE).status == 'NO_ORDERS'


def test_lists_and_combinations_are_fully_parsed():  # clinical safety review B1
    cases = [
        ([ev('a', 'ALLERGY', 'amoxicillin, ibuprofen')], 'ibuprofen', 'ALLERGY_MATCH'),
        ([ev('a', 'ALLERGY', 'aspirin, penicillin')], 'amoxicillin', 'ALLERGY_MATCH'),
        ([ev('a', 'ALLERGY', 'แพ้แอสไพรินและเพนิซิลลิน')], 'amoxicillin', 'ALLERGY_MATCH'),
        ([ev('a', 'ALLERGY', 'ไม่มี'), ev('m', 'MEDICATION', 'paracetamol, sertraline')], 'tramadol', 'INTERACTION'),
        ([ev('a', 'ALLERGY', 'ไม่มี'), ev('m', 'MEDICATION', 'sertraline')], 'paracetamol/tramadol', 'INTERACTION'),
        ([ev('a', 'ALLERGY', 'ไม่มี'), ev('b', 'ALLERGY', 'penicillin')], 'paracetamol', 'ALLERGY_CONFLICT'),
        ([ev('a', 'ALLERGY', 'amoxicillin, ผื่นแพ้ยาไม่ทราบชื่อ')], 'paracetamol', 'ALLERGY_UNRESOLVED'),
        ([ev('a', 'ALLERGY', 'ไม่มี'), ev('m', 'MEDICATION', 'ยาความดันไม่ทราบชื่อ')], 'paracetamol', 'MEDICATION_UNRESOLVED'),
    ]
    for facts, drug, code in cases:
        meds = [] if any(f['fact']['kind'] == 'MEDICATION' for f in facts) else [ev('m', 'MEDICATION', 'ไม่มี')]
        result = check(facts + meds + [order('o', drug)])
        assert result.status == 'NEEDS_PHARMACIST_REVIEW' and code in {f.code for f in result.findings}, (facts, drug)
    assert 'MULTI_DRUG_ORDER' in {f.code for f in check(NONE + [order('o', 'paracetamol/tramadol')]).findings}


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


EVENTS = [ev('a', 'ALLERGY', 'none'), ev('m', 'MEDICATION', 'none'), order('o', 'paracetamol')]


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


def test_every_list_joiner_and_unknown_brand_is_accounted_for():  # re-review MAJOR-1
    for text in ['แพ้ amoxicillin กับ Brufen', 'amoxicillin & Brufen', 'แพ้ยา amoxicillin หรือ Brufen ไม่แน่ใจ',
                 'amoxicillin - sulfa', 'amoxicillin | codeine', 'amoxicillin Brufen']:
        result = check([ev('a', 'ALLERGY', text), ev('m', 'MEDICATION', 'ไม่มี'), order('o', 'ibuprofen')])
        assert result.status == 'NEEDS_PHARMACIST_REVIEW' and 'ALLERGY_UNRESOLVED' in {f.code for f in result.findings}, text
    assert check(NONE[:1] + [ev('m', 'MEDICATION', 'ไม่มี'), ev('b', 'ALLERGY', 'แพ้ penicillin ผื่นลมพิษ rash'),
                 order('o', 'paracetamol')]).status == 'NEEDS_PHARMACIST_REVIEW'  # conflict with "ไม่มี", not a leftover
    assert 'ALLERGY_UNRESOLVED' not in {f.code for f in check([ev('a', 'ALLERGY', 'แพ้ penicillin ผื่นลมพิษ rash'),
        ev('m', 'MEDICATION', 'ไม่มี'), order('o', 'paracetamol')]).findings}


def test_thai_script_brands_and_abbreviations_beside_a_drug_are_reported():  # re-review MINOR-A
    for allergy, drug in [('แพ้ amoxicillin บรูเฟน', 'ibuprofen'), ('แพ้อะม็อกซีซิลลิน บรูเฟน', 'ibuprofen'),
                          ('amoxicillin ASA', 'aspirin')]:
        result = check([ev('a', 'ALLERGY', allergy), ev('m', 'MEDICATION', 'ไม่มี'), order('o', drug)])
        assert 'ALLERGY_UNRESOLVED' in {f.code for f in result.findings}, allergy
    meds = check([ev('a', 'ALLERGY', 'ไม่มี'), ev('m', 'MEDICATION', 'warfarin ซอลอฟท์'), order('o', 'tramadol')])
    assert 'MEDICATION_UNRESOLVED' in {f.code for f in meds.findings}
    for allergy in ['แพ้ penicillin ผื่นลมพิษ', 'แพ้แอสไพรินและเพนิซิลลิน']:  # ordinary context words stay quiet
        found = check([ev('a', 'ALLERGY', allergy), ev('m', 'MEDICATION', 'warfarin 3 mg วันละครั้ง'), order('o', 'paracetamol')])
        assert not {'ALLERGY_UNRESOLVED', 'MEDICATION_UNRESOLVED'} & {f.code for f in found.findings}, allergy
