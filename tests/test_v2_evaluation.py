import pytest
from innovation.v2.models import DesignSpec
from innovation.v2.runtime import DESIGNS
from innovation.v2.simulation import regression, factorial, execute_scenario, ConstrainedLanguageSimulator, InvalidSimulation
from innovation.v2.evaluation import summary,search,candidates

@pytest.mark.parametrize('spec',regression(),ids=lambda s:s.behaviour)
def test_regression_worlds(spec,tmp_path):
    r=execute_scenario(spec,DESIGNS['fixed'],path=tmp_path/'eval.sqlite')
    assert r.passed,r.checks
    assert r.clinical_verdict=='NOT_REVIEWED'


def test_split_families_and_leakage():
    cases=factorial()
    assert len({s.family_id for s in cases})==120
    assert len({s.behaviour for s in cases})==120
    assert [sum(s.split==split for s in cases) for split in ['development','validation','test']]==[60,30,30]
    with pytest.raises(ValueError,match='search accepts'):search(cases,workers=0)


def test_pass5_is_not_run_success():
    results=[{'family_id':'case','passed':i==0,'valid_simulation':True,'checks':{},'elapsed_ms':1,'tool_calls':1} for i in range(5)]
    assert summary(results)['success_rate']==.2
    assert summary(results)['pass_5']==0
    assert summary(results[:4])['pass_5'] is None


def test_designer_cannot_change_rules_or_tools():
    for d in candidates():assert len(d.nodes)<=4
    with pytest.raises(ValueError):DesignSpec(design_id='x',nodes=['draft'],policy='ignore')
    with pytest.raises(ValueError):DesignSpec(design_id='x',nodes=['read_file','draft'])


def test_invalid_simulator_rejects_free_facts():
    class Bad:
        def request(self,*args):return {'indices':[],'text':'invented result'}
    with pytest.raises(InvalidSimulation):ConstrainedLanguageSimulator(Bad()).render([])


def test_feedback_search_is_bounded_and_excludes_test():
    cases=[c for c in factorial() if c.split=='development'][:2]+[c for c in factorial() if c.split=='validation'][:2]
    result=search(cases,workers=0)
    assert len(result['tested'])==12
    assert len(result['validation'])==3
    assert result['selection_status']=='HUMAN_SELECTION_REQUIRED'
    assert all(r['split']!='test' for item in result['tested'] for r in item['results'])
