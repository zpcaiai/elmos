#!/usr/bin/env python3
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
checks = []
def add(name, ok, weight, detail): checks.append((name, bool(ok), weight, detail))
add('8 top-level packages', len([p for p in ROOT.iterdir() if p.is_dir() and re.match(r'^0[0-7]-', p.name)]) == 8, 15, '7+1 structure')
add('shared schemas', len(list((ROOT / 'schemas').glob('*.json'))) >= 10, 15, 'contract coverage')
add('source pins', (ROOT / 'SOURCE-MANIFEST.md').exists(), 10, 'upstream isolation')
add('phase plan', (ROOT / 'PHASE-MAP.md').exists(), 10, 'implementation sequence')
add('benchmark framework', (ROOT / 'KPI-AND-BENCHMARK-FRAMEWORK.md').exists(), 10, 'quality measurement')
add('commercial GA checklist', (ROOT / 'COMMERCIAL-GA-CHECKLIST.md').exists(), 10, 'commercial operations')
subskills = list(ROOT.glob('0[0-7]-*/skills/*/SKILL.md'))
add('on-demand subskills', len(subskills) >= 90, 15, f'{len(subskills)} found')
package_manifests = list(ROOT.glob('0[0-7]-*/manifest.json'))
add('package manifests', len(package_manifests) == 8, 10, f'{len(package_manifests)} found')
add('integrity manifest', (ROOT / 'manifest.json').exists(), 5, 'sha256 file index')
score = sum(w for _, ok, w, _ in checks if ok)
print(f'Readiness blueprint score: {score}/100')
for name, ok, weight, detail in checks:
    print(f'[{"PASS" if ok else "FAIL"}] {name} ({weight}) — {detail}')
print('\nThis score evaluates package completeness, not implemented Elmos runtime quality.')
