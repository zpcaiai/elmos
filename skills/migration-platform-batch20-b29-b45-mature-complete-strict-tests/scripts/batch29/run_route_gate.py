#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def load(p): return json.loads(Path(p).read_text())
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('route_dir'); a=p.parse_args()
    route=Path(a.route_dir)
    validator=Path(__file__).with_name('validate_route.py')
    rc=subprocess.run([sys.executable,str(validator),str(route)]).returncode
    if rc: return rc
    manifest=load(route/'route.json'); evidence=load(route/'certification'/'evidence.json'); support=load(route/'support-matrix.json')
    failures=[]
    metrics=evidence.get('metrics',{})
    certified=[c for c in support.get('capabilities',[]) if c.get('status')=='certified']
    if manifest.get('status')=='certified':
        if not certified: failures.append('certified route has no certified capabilities')
        if metrics.get('build_green_rate',0) <= 0: failures.append('no build-green evidence')
        if metrics.get('p0_behavior_pass_rate',0) < 1: failures.append('P0 behavior pass rate must be 1 for certified scope')
        if metrics.get('source_map_coverage',0) < 0.95: failures.append('source-map coverage below 0.95')
        if evidence.get('critical_unknown_semantics',1) != 0: failures.append('critical unknown semantics remain')
        if evidence.get('critical_behavior_regressions',1) != 0: failures.append('critical behavior regressions remain')
        if evidence.get('test_integrity_violations',1) != 0: failures.append('test integrity violations remain')
        holdout=list((route/'corpus'/'holdout').rglob('*'))
        real=list((route/'corpus'/'real-repository').rglob('*'))
        if not any(x.is_file() for x in holdout): failures.append('holdout corpus is empty')
        if not any(x.is_file() for x in real): failures.append('representative repository corpus is empty')
    if failures:
        print('\n'.join(f'GATE FAIL: {x}' for x in failures), file=sys.stderr)
        return 2
    print(f"GATE PASS: {manifest.get('route_key')} status={manifest.get('status')}")
    return 0
if __name__=='__main__': raise SystemExit(main())
