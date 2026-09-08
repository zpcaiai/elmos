from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reference_planner.adaptive import decide_granularity, verify_dag, coverage_gaps, refinement_frontier, replan_scope


def test_granularity_splits_large_node_and_keeps_indivisible_invariant():
    f={"context_demand":1,"write_surface":1,"semantic_breadth":1,"cross_boundary_coupling":0.9,"invariant_density":0.9,"verification_distance":0.9,"uncertainty":0.8}
    assert decide_granularity(f).decision == "split"
    assert decide_granularity(f, indivisible_invariant=True).decision == "keep"


def test_example_dag_structurally_valid_and_covered():
    data=json.loads((ROOT/'examples/adaptive-hierarchical-plan.json').read_text())
    leaves=[n for n in data['nodes'] if n.get('hierarchy_level')=='atomic_task']
    assert verify_dag(leaves, data['edges']) == []
    gaps=coverage_gaps(leaves, data['required_scenarios'], data['required_invariants'], data['required_proofs'])
    assert gaps == {"missing_scenarios":[],"missing_invariants":[],"missing_proofs":[]}


def test_refinement_prioritizes_uncertain_coarse_branch():
    data=json.loads((ROOT/'examples/adaptive-hierarchical-plan.json').read_text())
    f=refinement_frontier(data['nodes'])
    assert f[0] == 'C1'


def test_replan_scope():
    assert replan_scope('contract_change') == 'boundary_cluster'
    assert replan_scope('acceptance_scenario_change') == 'global'
    assert replan_scope('repeated_same_failure') == 'local'
