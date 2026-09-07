#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def load(path: Path):
    return json.loads(path.read_text())

def has_real_file(path: Path) -> bool:
    for item in path.rglob('*'):
        if item.is_file() and item.name.lower() not in {'readme.md', '.gitkeep'} and item.stat().st_size > 0:
            return True
    return False

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('pack_dir')
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    here = Path(__file__).resolve().parent

    if subprocess.run([sys.executable, str(here / 'validate_client_pack.py'), str(pack)]).returncode:
        return 1
    if subprocess.run([sys.executable, str(here / 'validate_ui_ir.py'), str(pack / 'ui-ir' / 'model.json')]).returncode:
        return 1

    manifest = load(pack / 'pack.json')
    support = load(pack / 'support-matrix.json')
    fingerprint = load(pack / 'source-fingerprint' / 'fingerprint.json')
    ui_ir = load(pack / 'ui-ir' / 'model.json')
    acceptance = load(pack / 'acceptance' / 'acceptance-profile.json')
    evidence = load(pack / 'certification' / 'evidence.json')
    certification = load(pack / 'certification' / 'certification.json')
    failures: list[str] = []

    if manifest.get('status') == 'certified' or certification.get('status') == 'certified':
        if manifest.get('status') != 'certified' or certification.get('status') != 'certified':
            failures.append('pack and certification statuses must both be certified')
        if not [cap for cap in support.get('capabilities', []) if cap.get('status') == 'certified']:
            failures.append('no certified capabilities')

        metrics = evidence.get('metrics', {})
        thresholds = {
            'source_fingerprint_coverage': 0.95,
            'ui_ir_source_map_coverage': 0.95,
            'target_build_green_rate': 1.0,
            'target_startup_or_launch_rate': 1.0,
            'p0_journey_pass_rate': 1.0,
            'route_contract_pass_rate': 1.0,
            'state_contract_pass_rate': 1.0,
            'form_contract_pass_rate': 1.0,
            'identity_permission_pass_rate': 1.0,
            'visual_pass_rate': 1.0,
            'accessibility_pass_rate': 1.0,
            'i18n_pass_rate': 1.0,
            'browser_matrix_pass_rate': 1.0,
            'representative_workload_pass_rate': 1.0,
            'source_map_coverage': 0.95,
        }
        for key, threshold in thresholds.items():
            if metrics.get(key, 0) < threshold:
                failures.append(f'{key} below {threshold}')

        zero_fields = [
            'critical_unknowns',
            'silent_ui_drops',
            'critical_visual_regressions',
            'critical_accessibility_violations',
            'critical_security_regressions',
            'critical_interaction_regressions',
            'test_integrity_violations',
            'unapproved_baseline_changes',
            'unapproved_dependency_changes',
        ]
        for key in zero_fields:
            if evidence.get(key, 1) != 0:
                failures.append(f'{key} must be zero')

        if fingerprint.get('coverage', 0) < 0.95:
            failures.append('source fingerprint coverage below 0.95')
        if str(fingerprint.get('snapshot_digest', '')).upper() in {'', 'UNSET'}:
            failures.append('source fingerprint snapshot digest unset')
        if not any(ui_ir.get(group) for group in ('routes', 'views', 'components', 'states', 'forms')):
            failures.append('UI IR contains no evidence-bearing nodes')
        if not acceptance.get('p0_journeys'):
            failures.append('acceptance profile has no P0 journeys')
        route_matrix = load(pack / 'route-matrix.json')
        if not route_matrix.get('tuples'):
            failures.append('route matrix has no exact tuples')
        if not has_real_file(pack / 'corpus' / 'holdout'):
            failures.append('holdout corpus empty')
        if not has_real_file(pack / 'corpus' / 'representative-workloads'):
            failures.append('representative workload corpus empty')
        if not has_real_file(pack / 'visual-baselines' / 'approved'):
            failures.append('approved visual baselines empty')

        references = evidence.get('evidence_refs', []) + certification.get('evidence_refs', [])
        if not references:
            failures.append('certification evidence refs empty')
        for reference in references:
            if reference.startswith(('http://', 'https://')):
                continue
            if not (pack / reference).is_file():
                failures.append(f'missing evidence ref: {reference}')

    result = {
        'schema_version': 1,
        'pack_key': manifest.get('pack_key'),
        'status': 'failed' if failures else 'passed',
        'pack_status': manifest.get('status'),
        'failures': failures,
    }
    result_path = pack / 'certification' / 'gate-result.json'
    result_path.write_text(json.dumps(result, indent=2) + '\n')

    report = [
        f"# Batch 32 gate: {manifest.get('pack_key')}",
        '',
        f"- Pack status: `{manifest.get('status')}`",
        f"- Gate status: `{'failed' if failures else 'passed'}`",
        '',
    ]
    if failures:
        report.append('## Failures')
        report.extend(f'- {failure}' for failure in failures)
    else:
        report.append('No structural or certification-gate failures were detected.')
    (pack / 'certification' / 'gate-report.md').write_text('\n'.join(report) + '\n')

    if failures:
        print('\n'.join('GATE FAIL: ' + failure for failure in failures), file=sys.stderr)
        return 2
    print(f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
