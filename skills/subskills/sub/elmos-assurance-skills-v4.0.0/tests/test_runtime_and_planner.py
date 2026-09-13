from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from elmos_assurance.ledger import CommitLedger, BudgetLedger
from elmos_assurance.planner import coverage, select_smoke
from elmos_assurance.comparison import compare_rows
from elmos_assurance.metrics import zero_event_upper_bound, mutation_summary


def test_parallel_duplicate_results_commit_once():
    l=CommitLedger();l.create('t','r',0,100)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:l.commit('t','r','s',1,'i',{'answer':42},1),range(32)))
    assert results.count('COMMITTED')==1
    assert l.result_count()==1


def test_payload_conflict_is_not_silently_deduplicated():
    l=CommitLedger();l.create('t','r',0,100);l.commit('t','r','s',1,'i',{'x':1},1)
    with pytest.raises(ValueError,match='IDEMPOTENCY_PAYLOAD_CONFLICT'):
        l.commit('t','r','s',1,'i',{'x':2},2)


def test_old_executor_fenced():
    l=CommitLedger();l.create('t','r',0,100);l.replace_executor('t','r',1,100)
    with pytest.raises(ValueError,match='FENCE_REJECTED'):l.commit('t','r','s',1,'i',{},2)


def test_cancel_fences_and_cannot_resume_old_run():
    l=CommitLedger();l.create('t','r',0,100);l.cancel('t','r')
    with pytest.raises(ValueError,match='FENCE_REJECTED'):l.commit('t','r','s',1,'i',{},2)
    with pytest.raises(ValueError,match='RUN_CANCELLED'):l.replace_executor('t','r',2,100)


def test_expired_lease_cannot_commit():
    l=CommitLedger();l.create('t','r',0,10)
    with pytest.raises(ValueError,match='LEASE_EXPIRED'):l.commit('t','r','s',1,'i',{},10)


def test_cross_tenant_cannot_use_run_lease():
    l=CommitLedger();l.create('a','r',0,100)
    with pytest.raises(KeyError):l.commit('b','r','s',1,'i',{},1)


def test_same_run_ids_distinct_tenants_isolate_results():
    l=CommitLedger()
    for t in ['a','b']:
        l.create(t,'r',0,100);l.commit(t,'r','s',1,'i',{'tenant':t},1)
    assert l.result_count()==2


def test_budget_unknown_is_not_zero_cost():
    b=BudgetLedger(100);b.reserve('a',80)
    assert b.settle('a',None)=='PENDING_RECONCILIATION'
    assert b.available==20
    assert b.settle('a',60)=='SETTLED'
    assert b.available==40
    assert b.settle('a',60)=='DUPLICATE'
    assert b.available==40


def test_three_top_level_reservations_default():
    b=BudgetLedger(100)
    for i in range(3):b.reserve(str(i),10)
    with pytest.raises(ValueError,match='CONCURRENCY_LIMIT'):b.reserve('4',10)


def test_budget_limit_is_atomic():
    b=BudgetLedger(10,8)
    def reserve(i):
        try:return b.reserve(str(i),6)
        except ValueError:return 'REJECTED'
    with ThreadPoolExecutor(max_workers=8) as pool:res=list(pool.map(reserve,range(8)))
    assert res.count('RESERVED')==1
    assert b.available==4


def test_overage_keeps_reservation_for_reconciliation():
    b=BudgetLedger(100);b.reserve('a',20)
    with pytest.raises(ValueError,match='OVERAGE'):b.settle('a',30)
    assert b.available==80


def test_empty_coverage_has_no_percentage():
    assert coverage(set(),{})['ratio'] is None


def test_not_run_does_not_count_as_pass():
    c=coverage({'a','b'},{'a':'PASS','b':'NOT_RUN'})
    assert c['numerator']==1 and c['denominator']==2


def test_unknown_coverage_id_cannot_inflate_denominator():
    with pytest.raises(ValueError):coverage({'a'},{'elsewhere':'PASS'})


def test_smoke_complete_is_only_a_plan():
    p=select_smoke([{'id':'a','covers':['startup','auth'],'estimated_ms':10},
                    {'id':'b','covers':['persistence'],'estimated_ms':5}],{'startup','auth','persistence'},20)
    assert not p['uncovered']
    assert p['tests_executed'] is False


def test_smoke_budget_reports_uncovered_not_pass():
    p=select_smoke([{'id':'a','covers':['a'],'estimated_ms':10}],{'a','b'},10)
    assert p['status']=='INCONCLUSIVE' and p['uncovered']==['b']


def test_smoke_ties_deterministic():
    a={'id':'a','covers':['x'],'estimated_ms':10};b={'id':'b','covers':['x'],'estimated_ms':10}
    assert select_smoke([b,a],{'x'},10)['selected']==['a']

@pytest.mark.parametrize('critical,budget',[ (set(),10),({'a'},0)])
def test_smoke_invalid_inputs(critical,budget):
    with pytest.raises(ValueError):select_smoke([],critical,budget)


def row(kind,value):return [{'type':kind,'value':value}]


def test_bag_multiplicity_preserved():
    assert not compare_rows([row('int',1),row('int',1)],[row('int',1)])


def test_order_only_ignored_for_bag():
    a=[row('int',1),row('int',2)];b=list(reversed(a))
    assert compare_rows(a,b,'bag')
    assert not compare_rows(a,b,'ordered')


def test_set_semantics_require_explicit_mode():
    assert compare_rows([row('int',1),row('int',1)],[row('int',1)],'set')


def test_null_is_not_empty_string():
    assert not compare_rows([row('null',None)],[row('string','')])


def test_decimal_exact_no_epsilon():
    assert not compare_rows([row('decimal','100.00')],[row('decimal','100.01')])
    assert compare_rows([row('decimal','100.0')],[row('decimal','100.00')])


def test_bool_is_not_integer():
    with pytest.raises(ValueError):compare_rows([row('int',True)],[row('int',1)])

@pytest.mark.parametrize('value',['NaN','Infinity','not-a-number'])
def test_decimal_invalid_values(value):
    with pytest.raises(ValueError):compare_rows([row('decimal',value)],[row('decimal','1')])


def test_zero_events_does_not_imply_zero_risk():
    assert zero_event_upper_bound(100)==pytest.approx(0.02951305,rel=1e-5)
    assert zero_event_upper_bound(3000)<0.001

@pytest.mark.parametrize('n',[0,-1,1.5,True])
def test_zero_event_bad_sample(n):
    with pytest.raises(ValueError):zero_event_upper_bound(n)


def test_mutant_unknown_in_denominator():
    s=mutation_summary(90,0,10)
    assert s['conservative_ratio']==0.9 and s['complete'] is False


def test_empty_mutant_denominator_not_one():
    assert mutation_summary(0,0,0)['conservative_ratio'] is None
