#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def load(path:Path): return json.loads(path.read_text())
def has_real_file(path:Path)->bool:
    for f in path.rglob('*'):
        if f.is_file() and f.name.lower() not in {'readme.md','.gitkeep'} and f.stat().st_size>0: return True
    return False

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('pack_dir'); a=p.parse_args(); pack=Path(a.pack_dir)
    here=Path(__file__).resolve().parent
    if subprocess.run([sys.executable,str(here/'validate_database_pack.py'),str(pack)]).returncode: return 1
    if subprocess.run([sys.executable,str(here/'validate_canonical_ir.py'),str(pack/'canonical-ir'/'model.json')]).returncode: return 1
    manifest=load(pack/'pack.json'); support=load(pack/'support-matrix.json'); fp=load(pack/'source-fingerprint'/'manifest.json'); ir=load(pack/'canonical-ir'/'model.json'); evidence=load(pack/'certification'/'evidence.json'); cert=load(pack/'certification'/'certification.json'); failures=[]
    if manifest.get('status')=='certified' or cert.get('status')=='certified':
        if manifest.get('status')!='certified' or cert.get('status')!='certified': failures.append('pack and certification statuses must both be certified')
        if not [c for c in support.get('capabilities',[]) if c.get('status')=='certified']: failures.append('no certified capabilities')
        metrics=evidence.get('metrics',{})
        thresholds={'workload_fingerprint_coverage':0.95,'canonical_ir_coverage':0.95,'schema_conversion_pass_rate':1,'type_boundary_pass_rate':1,'query_semantic_pass_rate':1,'transaction_contract_pass_rate':1,'data_reconciliation_pass_rate':1,'target_provision_pass_rate':1,'representative_workload_pass_rate':1,'source_map_coverage':0.95,'query_performance_slo_pass_rate':1}
        for k,v in thresholds.items():
            if metrics.get(k,0)<v: failures.append(f'{k} below {v}')
        zero_fields=['critical_unknowns','silent_database_drops','critical_precision_loss','critical_collation_regressions','critical_transaction_regressions','critical_data_differences','critical_security_regressions','destructive_unapproved_changes','test_integrity_violations']
        for k in zero_fields:
            if evidence.get(k,1)!=0: failures.append(f'{k} must be zero')
        if fp.get('coverage',0)<0.95: failures.append('fingerprint coverage below 0.95')
        if str(fp.get('snapshot_digest','')).upper() in {'','UNSET'}: failures.append('fingerprint snapshot digest unset')
        if not (ir.get('objects') or ir.get('queries') or ir.get('pipelines')): failures.append('canonical IR contains no evidence-bearing nodes')
        route=load(pack/'route-matrix.json')
        if not route.get('tuples'): failures.append('route matrix has no exact tuples')
        if not has_real_file(pack/'corpus'/'holdout'): failures.append('holdout corpus empty')
        if not has_real_file(pack/'corpus'/'representative-workloads'): failures.append('representative workload corpus empty')
        refs=evidence.get('evidence_refs',[])+cert.get('evidence_refs',[])
        if not refs: failures.append('certification evidence refs empty')
        for ref in refs:
            if ref.startswith('http://') or ref.startswith('https://'): continue
            if not (pack/ref).is_file(): failures.append(f'missing evidence ref: {ref}')
        plan=load(pack/'migration'/'data-migration-plan.json')
        if not plan.get('reconciliation'): failures.append('no data reconciliation rules')
        if str(plan.get('rollback',{}).get('strategy','')).upper() in {'','UNSET'}: failures.append('rollback strategy unset')
    result={'schema_version':1,'pack_key':manifest.get('pack_key'),'status':'failed' if failures else 'passed','pack_status':manifest.get('status'),'failures':failures}
    (pack/'certification'/'gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
    if failures:
        print('\n'.join('GATE FAIL: '+f for f in failures),file=sys.stderr); return 2
    print(f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')}"); return 0
if __name__=='__main__': raise SystemExit(main())
