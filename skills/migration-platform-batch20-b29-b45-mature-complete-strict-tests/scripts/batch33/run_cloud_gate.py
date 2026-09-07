#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def load(path: Path): return json.loads(path.read_text())

def has_real_file(path: Path) -> bool:
    if not path.exists(): return False
    for item in path.rglob('*'):
        if item.is_file() and item.name.lower() not in {'readme.md', '.gitkeep'} and item.stat().st_size > 0:
            return True
    return False

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument('pack_dir'); args = p.parse_args()
    pack = Path(args.pack_dir); here = Path(__file__).resolve().parent
    for cmd in (
        [sys.executable, str(here/'validate_cloud_pack.py'), str(pack)],
        [sys.executable, str(here/'validate_runtime_contract.py'), str(pack/'runtime-architecture'/'contract.json')],
        [sys.executable, str(here/'validate_iac_ir.py'), str(pack/'iac-ir'/'model.json')],
    ):
        if subprocess.run(cmd).returncode: return 1
    manifest = load(pack/'pack.json'); support = load(pack/'support-matrix.json')
    fingerprint = load(pack/'source-fingerprint'/'fingerprint.json')
    runtime = load(pack/'runtime-architecture'/'contract.json'); ir = load(pack/'iac-ir'/'model.json')
    validation = load(pack/'validation'/'validation-profile.json')
    evidence = load(pack/'certification'/'evidence.json'); cert = load(pack/'certification'/'certification.json')
    failures: list[str] = []
    if manifest.get('status') == 'certified' or cert.get('status') == 'certified':
        if manifest.get('status') != 'certified' or cert.get('status') != 'certified': failures.append('pack and certification statuses must both be certified')
        if not [c for c in support.get('capabilities', []) if c.get('status') == 'certified']: failures.append('no certified capabilities')
        metrics = evidence.get('metrics', {})
        thresholds = {
            'source_fingerprint_coverage': .95,
            'runtime_contract_source_map_coverage': .95,
            'iac_ir_source_map_coverage': .95,
            'source_plan_pass_rate': 1.0,
            'target_plan_pass_rate': 1.0,
            'target_apply_or_emulator_pass_rate': 1.0,
            'p0_deployment_contract_pass_rate': 1.0,
            'container_build_pass_rate': 1.0,
            'kubernetes_validation_pass_rate': 1.0,
            'cicd_pipeline_pass_rate': 1.0,
            'identity_network_contract_pass_rate': 1.0,
            'secret_config_pass_rate': 1.0,
            'observability_pass_rate': 1.0,
            'security_guardrail_pass_rate': 1.0,
            'drift_validation_pass_rate': 1.0,
            'cost_budget_pass_rate': 1.0,
            'rollback_destroy_pass_rate': 1.0,
            'representative_workload_pass_rate': 1.0,
            'source_map_coverage': .95,
        }
        for key, threshold in thresholds.items():
            if metrics.get(key, 0) < threshold: failures.append(f'{key} below {threshold}')
        zero_fields = [
            'critical_unknowns','silent_resource_drops','critical_security_regressions','critical_network_exposures',
            'secret_leaks','privilege_expansions','data_residency_violations','unauthorized_public_egress',
            'unapproved_provider_changes','unknown_drift_resources','orphaned_resources','cost_budget_violations',
            'destroy_failures','test_integrity_violations','unapproved_baseline_changes',
        ]
        for key in zero_fields:
            if evidence.get(key, 1) != 0: failures.append(f'{key} must be zero')
        if fingerprint.get('coverage', 0) < .95: failures.append('source fingerprint coverage below 0.95')
        if str(fingerprint.get('snapshot_digest','')).upper() in {'','UNSET'}: failures.append('source fingerprint digest unset')
        if not any(runtime.get(g) for g in ('components','connections','identities','data_flows')): failures.append('runtime contract has no evidence-bearing nodes')
        if not ir.get('resources'): failures.append('IaC IR has no resources')
        if not validation.get('p0_workloads'): failures.append('validation profile has no P0 workloads')
        route = load(pack/'route-matrix.json')
        if not route.get('tuples'): failures.append('route matrix has no exact tuples')
        if not has_real_file(pack/'corpus'/'holdout'): failures.append('holdout corpus empty')
        if not has_real_file(pack/'corpus'/'representative-workloads'): failures.append('representative workload corpus empty')
        refs = evidence.get('evidence_refs', []) + cert.get('evidence_refs', []) + validation.get('evidence_refs', [])
        if not refs: failures.append('certification evidence refs empty')
        for ref in refs:
            if ref.startswith(('http://','https://')): continue
            if not (pack/ref).is_file(): failures.append(f'missing evidence ref: {ref}')
    result = {'schema_version':1,'pack_key':manifest.get('pack_key'),'status':'failed' if failures else 'passed','pack_status':manifest.get('status'),'failures':failures}
    (pack/'certification'/'gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=[f"# Batch 33 gate: {manifest.get('pack_key')}",'',f"- Pack status: `{manifest.get('status')}`",f"- Gate status: `{'failed' if failures else 'passed'}`",'']
    if failures: lines += ['## Failures'] + [f'- {x}' for x in failures]
    else: lines.append('No structural or certification-gate failures were detected.')
    (pack/'certification'/'gate-report.md').write_text('\n'.join(lines)+'\n')
    if failures:
        print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
    print(f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')}"); return 0
if __name__ == '__main__': raise SystemExit(main())
