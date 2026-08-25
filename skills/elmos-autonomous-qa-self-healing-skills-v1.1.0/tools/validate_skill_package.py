#!/usr/bin/env python3
"""Validate the Elmos Autonomous QA skills package structure and schemas."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install pyyaml") from exc

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover
    raise SystemExit("jsonschema is required: pip install jsonschema") from exc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', nargs='?', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--verify-checksums', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []

    required_docs = [
        'README.md', 'PROJECT_OUTPUT_CONTRACT.md', 'ARCHITECTURE.md',
        'MANIFEST.yaml', 'QUALITY_GATES.yaml', 'IMPLEMENTATION_PLAN.md',
        'AGENTS.md', 'CLAUDE.md', 'PACKAGE_VALIDATION_REPORT.md'
    ]
    for rel in required_docs:
        if not (root / rel).is_file():
            errors.append(f'missing required document: {rel}')

    # Parse all JSON and YAML files.
    for path in sorted(root.rglob('*.json')):
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'invalid JSON {path.relative_to(root)}: {exc}')
    for path in sorted(root.rglob('*.yaml')):
        try:
            yaml.safe_load(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f'invalid YAML {path.relative_to(root)}: {exc}')

    # Check JSON Schemas.
    for path in sorted((root / 'schemas').glob('*.json')):
        try:
            Draft202012Validator.check_schema(json.loads(path.read_text(encoding='utf-8')))
        except Exception as exc:
            errors.append(f'invalid JSON Schema {path.name}: {exc}')

    manifest_path = root / 'MANIFEST.yaml'
    if manifest_path.is_file():
        manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
        version = str(manifest.get('package', {}).get('version', ''))
        if version != '1.1.0':
            errors.append(f'package version must be 1.1.0, got {version!r}')
        skill_order = manifest.get('skill_order') or []
        if len(skill_order) != 40 or len(set(skill_order)) != 40:
            errors.append(f'skill_order must contain 40 unique skills, got {len(skill_order)}')
        known = set(skill_order)
        for skill_id in skill_order:
            skill_file = root / 'skills' / skill_id / 'SKILL.md'
            if not skill_file.is_file():
                errors.append(f'missing skill: {skill_id}')
                continue
            text = skill_file.read_text(encoding='utf-8')
            match = re.match(r'^---\n(.*?)\n---\n', text, flags=re.S)
            if not match:
                errors.append(f'missing YAML frontmatter: {skill_id}')
                continue
            meta = yaml.safe_load(match.group(1))
            if meta.get('id') != skill_id:
                errors.append(f'skill id mismatch: folder={skill_id}, meta={meta.get("id")}')
            if str(meta.get('version')) != '1.1.0':
                errors.append(f'skill version mismatch: {skill_id} -> {meta.get("version")}')
            for dep in meta.get('depends_on') or []:
                if dep not in known:
                    errors.append(f'unknown dependency {dep} in {skill_id}')
        for rel in manifest.get('required_schemas') or []:
            if not (root / rel).is_file():
                errors.append(f'missing required schema: {rel}')
        for rel in manifest.get('required_workflows') or []:
            if not (root / rel).is_file():
                errors.append(f'missing required workflow: {rel}')
        for key in ('required_policies', 'required_tools'):
            for rel in manifest.get(key) or []:
                if not (root / rel).is_file():
                    errors.append(f'missing {key}: {rel}')

    # Verify stored checksums when requested.
    checksums = root / 'CHECKSUMS.sha256'
    if args.verify_checksums and checksums.is_file():
        for line in checksums.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            digest, rel = line.split('  ', 1)
            path = root / rel
            if not path.is_file():
                errors.append(f'checksum target missing: {rel}')
            elif sha256_file(path) != digest:
                errors.append(f'checksum mismatch: {rel}')

    if errors:
        print('VALIDATION FAILED')
        for err in errors:
            print(f'- {err}')
        return 1

    skill_count = len(list((root / 'skills').glob('*/SKILL.md')))
    schema_count = len(list((root / 'schemas').glob('*.json')))
    workflow_count = len(list((root / 'workflows').glob('*.yaml')))
    print(f'VALIDATION PASSED: {skill_count} skills, {schema_count} schemas, {workflow_count} workflows')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
