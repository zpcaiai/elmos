#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text())


def has_file(path: Path) -> bool:
    return any(item.is_file() for item in path.rglob('*'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('pack_dir')
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    validator = Path(__file__).with_name('validate_framework_pack.py')
    if subprocess.run([sys.executable, str(validator), str(pack)]).returncode:
        return 1
    manifest = load(pack/'pack.json')
    support = load(pack/'support-matrix.json')
    evidence = load(pack/'certification'/'evidence.json')
    failures: list[str] = []
    if manifest.get('status') == 'certified':
        certified = [c for c in support.get('capabilities', []) if c.get('status') == 'certified']
        metrics = evidence.get('metrics', {})
        if not certified:
            failures.append('certified pack has no certified capabilities')
        if metrics.get('source_fingerprint_coverage', 0) < 0.95:
            failures.append('source fingerprint coverage below 0.95')
        if metrics.get('framework_contract_coverage', 0) < 0.95:
            failures.append('framework contract coverage below 0.95')
        if metrics.get('build_green_rate', 0) <= 0:
            failures.append('no target build-green evidence')
        if metrics.get('startup_pass_rate', 0) < 1:
            failures.append('startup pass rate must be 1')
        if metrics.get('p0_contract_pass_rate', 0) < 1:
            failures.append('P0 contract pass rate must be 1')
        if metrics.get('source_map_coverage', 0) < 0.95:
            failures.append('source-map coverage below 0.95')
        for field in [
            'critical_unknowns','silent_framework_drops','critical_security_regressions',
            'critical_transaction_regressions','critical_data_regressions',
            'duplicate_message_or_job_effects','test_integrity_violations'
        ]:
            if evidence.get(field, 1) != 0:
                failures.append(f'{field} must be zero')
        if not has_file(pack/'corpus'/'holdout'):
            failures.append('holdout corpus is empty')
        if not has_file(pack/'corpus'/'real-repository'):
            failures.append('representative repository corpus is empty')
        if not load(pack/'version-matrix.json').get('tuples'):
            failures.append('version matrix has no exact tuples')
    if failures:
        print('\n'.join(f'GATE FAIL: {item}' for item in failures), file=sys.stderr)
        return 2
    print(f"GATE PASS: {manifest.get('pack_key')} status={manifest.get('status')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
