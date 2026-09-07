#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import re
import sys
import yaml
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ROOT = [
    'README.md', 'SKILL.md', 'AGENTS.md', 'ELMOS_WORKFLOW.md', 'PHASE-MAP.md',
    'SOURCE-MANIFEST.md', 'SOURCE-TO-CAPABILITY-MATRIX.md',
    'UPSTREAM-CAPABILITY-EXTRACTION.md', 'DETAILED-PHASE-DELIVERY-PLAN.md',
    'ELMOS-REFERENCE-ARCHITECTURE.md',
    'KPI-AND-BENCHMARK-FRAMEWORK.md', 'COMMERCIAL-GA-CHECKLIST.md',
    'LICENSE-AND-ATTRIBUTION.md', 'manifest.json'
]
REQUIRED_PACKAGE = [
    'README.md', 'SKILL.md', 'PRODUCT-CAPABILITY-SPEC.md', 'ARCHITECTURE.md',
    'PHASE-PLAN.md', 'INTERFACE-CONTRACTS.md', 'DATA-AND-EVENT-MODEL.md',
    'SECURITY-AND-GOVERNANCE.md', 'OBSERVABILITY-AND-SLO.md',
    'BENCHMARKS-AND-EVALS.md', 'ACCEPTANCE-GATES.md',
    'FAILURE-MODES-AND-RECOVERY.md', 'IMPLEMENTATION-BACKLOG.md',
    'examples/package-config.yaml', 'schemas/package-config.schema.json', 'manifest.json'
]
errors = []
for rel in REQUIRED_ROOT:
    if not (ROOT / rel).is_file(): errors.append(f'missing root file: {rel}')
shared_schemas = {}
for schema in (ROOT / 'schemas').glob('*.json'):
    try:
        parsed = json.loads(schema.read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator.check_schema(parsed)
        shared_schemas[schema.name] = parsed
    except Exception as exc: errors.append(f'invalid JSON Schema {schema.relative_to(ROOT)}: {exc}')
packages = sorted(p for p in ROOT.iterdir() if p.is_dir() and re.match(r'^0[0-7]-', p.name))
if len(packages) != 8: errors.append(f'expected 8 package dirs, got {len(packages)}')
for pkg in packages:
    for rel in REQUIRED_PACKAGE:
        if not (pkg / rel).is_file(): errors.append(f'missing {pkg.name}/{rel}')
    text = (pkg / 'SKILL.md').read_text(encoding='utf-8') if (pkg / 'SKILL.md').exists() else ''
    if not text.startswith('---\n') or '\nname:' not in text or '\ndescription:' not in text:
        errors.append(f'invalid SKILL frontmatter: {pkg.name}/SKILL.md')
    subskills = list((pkg / 'skills').glob('*/SKILL.md')) if (pkg / 'skills').exists() else []
    try:
        pkg_manifest = json.loads((pkg / 'manifest.json').read_text(encoding='utf-8'))
        if 'package-manifest.schema.json' in shared_schemas:
            jsonschema.validate(pkg_manifest, shared_schemas['package-manifest.schema.json'])
        expected = len(pkg_manifest.get('subskills', []))
    except Exception as exc:
        errors.append(f'invalid package manifest {pkg.name}: {exc}')
        expected = -1
    if len(subskills) != expected: errors.append(f'{pkg.name}: expected {expected} subskills from manifest, got {len(subskills)}')
    for sub in subskills:
        t = sub.read_text(encoding='utf-8')
        if not t.startswith('---\n') or '\nname:' not in t or '\ndescription:' not in t:
            errors.append(f'invalid subskill frontmatter: {sub.relative_to(ROOT)}')
    try:
        pkg_schema = json.loads((pkg / 'schemas/package-config.schema.json').read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator.check_schema(pkg_schema)
        pkg_config = yaml.safe_load((pkg / 'examples/package-config.yaml').read_text(encoding='utf-8'))
        jsonschema.validate(pkg_config, pkg_schema)
    except Exception as exc: errors.append(f'invalid package schema/config {pkg.name}: {exc}')
example_schema_map = {
    'source-capability-ledger.example.json': 'capability-ledger.schema.json',
    'requirement-ledger.example.json': 'requirement-ledger.schema.json',
}
for example_name, schema_name in example_schema_map.items():
    try:
        data = json.loads((ROOT / 'examples' / example_name).read_text(encoding='utf-8'))
        jsonschema.validate(data, shared_schemas[schema_name])
    except Exception as exc: errors.append(f'invalid example {example_name}: {exc}')
for md in ROOT.rglob('*.md'):
    text = md.read_text(encoding='utf-8')
    if text.count('```') % 2 != 0:
        errors.append(f'unbalanced markdown code fence: {md.relative_to(ROOT)}')
manifest_path = ROOT / 'manifest.json'
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in manifest.get('files', []):
        path = ROOT / entry['path']
        if not path.exists(): errors.append(f'manifest missing file: {entry["path"]}'); continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']: errors.append(f'hash mismatch: {entry["path"]}')
if errors:
    print('VALIDATION FAILED')
    for e in errors: print('-', e)
    sys.exit(1)
print(f'VALIDATION PASSED: {len(packages)} packages, {sum(len(list((p / "skills").glob("*/SKILL.md"))) for p in packages)} subskills')
