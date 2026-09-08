#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reference_planner.adaptive import decide_granularity, verify_dag, coverage_gaps, refinement_frontier


def main():
    p=argparse.ArgumentParser()
    p.add_argument('plan', nargs='?', default=str(ROOT/'examples'/'adaptive-hierarchical-plan.json'))
    args=p.parse_args()
    data=json.loads(Path(args.plan).read_text())
    nodes=data['nodes']
    print('Granularity decisions:')
    for n in nodes:
        f=n.get('granularity_features')
        if f:
            d=decide_granularity(f, indivisible_invariant=n.get('indivisible_invariant', False))
            print(f"  {n['id']}: {d.decision} score={d.score:.3f} reasons={','.join(d.reasons)}")
    leaves=[n for n in nodes if n.get('hierarchy_level')=='atomic_task']
    errors=verify_dag(leaves, data.get('edges', []))
    print('DAG:', 'PASS' if not errors else 'FAIL')
    for e in errors: print('  -',e)
    cov=coverage_gaps(leaves, data.get('required_scenarios', []), data.get('required_invariants', []), data.get('required_proofs', []))
    print('Coverage:', json.dumps(cov, indent=2))
    print('Refinement frontier:', refinement_frontier(nodes))

if __name__=='__main__': main()
