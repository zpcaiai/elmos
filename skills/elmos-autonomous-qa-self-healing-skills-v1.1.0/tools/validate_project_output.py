#!/usr/bin/env python3
"""Validate an Elmos project deliverable, artifact hashes and ZIP safety."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover
    raise SystemExit("jsonschema is required: pip install jsonschema") from exc

SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
    re.compile(rb'(?i)(?:api[_-]?key|secret|password)\s*[:=]\s*["\'][^"\']{12,}["\']'),
]
TEXT_SCAN_LIMIT = 2 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_relative(rel: str) -> bool:
    p = PurePosixPath(rel.replace('\\', '/'))
    return bool(rel) and not p.is_absolute() and '..' not in p.parts and '\x00' not in rel


def inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def scan_zip(path: Path) -> list[str]:
    errors: list[str] = []
    if not zipfile.is_zipfile(path):
        return [f'not a valid ZIP: {path}']
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if not safe_relative(info.filename):
                errors.append(f'unsafe ZIP entry {info.filename!r} in {path.name}')
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                errors.append(f'symlink ZIP entry is not allowed: {info.filename!r}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('deliverable_root')
    parser.add_argument('--schema', default=str(Path(__file__).resolve().parents[1] / 'schemas' / 'project-output-manifest.schema.json'))
    parser.add_argument('--skip-secret-scan', action='store_true')
    args = parser.parse_args()

    root = Path(args.deliverable_root).resolve()
    manifest_path = root / 'manifests' / 'project-output-manifest.json'
    errors: list[str] = []
    if not manifest_path.is_file():
        print(f'VALIDATION FAILED: missing {manifest_path}')
        return 1

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    schema = json.loads(Path(args.schema).read_text(encoding='utf-8'))
    for err in Draft202012Validator(schema).iter_errors(manifest):
        loc = '/'.join(str(x) for x in err.absolute_path)
        errors.append(f'schema {loc}: {err.message}')

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for artifact in manifest.get('artifacts', []):
        aid = artifact.get('artifact_id', '')
        rel = artifact.get('path', '')
        if aid in seen_ids:
            errors.append(f'duplicate artifact_id: {aid}')
        seen_ids.add(aid)
        normalized = rel.replace('\\', '/')
        if normalized in seen_paths:
            errors.append(f'duplicate artifact path: {rel}')
        seen_paths.add(normalized)
        if not safe_relative(rel):
            errors.append(f'unsafe artifact path: {rel!r}')
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f'missing artifact: {rel}')
            continue
        if path.is_symlink() or not inside(root, path):
            errors.append(f'artifact escapes root or is symlink: {rel}')
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_size != artifact.get('size_bytes'):
            errors.append(f'size mismatch: {rel}')
        if actual_hash.lower() != str(artifact.get('sha256', '')).lower():
            errors.append(f'hash mismatch: {rel}')
        if artifact.get('category') == 'test_source':
            if not artifact.get('test_case_refs'):
                errors.append(f'test source missing test_case_refs: {rel}')
            if not artifact.get('requirement_refs') and not artifact.get('risk_justification'):
                errors.append(f'test source missing requirement/risk reference: {rel}')
        if not args.skip_secret_scan and actual_size <= TEXT_SCAN_LIMIT:
            data = path.read_bytes()
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    errors.append(f'possible secret in artifact: {rel}')
                    break

    bundle_kinds: set[str] = set()
    for bundle in manifest.get('bundles', []):
        rel = bundle.get('path', '')
        bundle_kinds.add(bundle.get('kind', ''))
        if not safe_relative(rel):
            errors.append(f'unsafe bundle path: {rel!r}')
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f'missing bundle: {rel}')
            continue
        if path.stat().st_size != bundle.get('size_bytes'):
            errors.append(f'bundle size mismatch: {rel}')
        if sha256_file(path).lower() != str(bundle.get('sha256', '')).lower():
            errors.append(f'bundle hash mismatch: {rel}')
        if bundle.get('format') == 'zip':
            errors.extend(scan_zip(path))

    mode = manifest.get('run_mode')
    if mode != 'plan-only':
        for required_kind in ('project-with-tests', 'tests-only'):
            if required_kind not in bundle_kinds:
                errors.append(f'missing required bundle for {mode}: {required_kind}')
    if mode in {'verify', 'repair', 'certify', 'continuous'} and 'qa-evidence' not in bundle_kinds:
        errors.append(f'missing required bundle for {mode}: qa-evidence')

    q = manifest.get('quality_summary', {})
    if manifest.get('status') == 'certified':
        if not q.get('quality_gates_passed'):
            errors.append('certified output has failing quality gates')
        if q.get('required_tests') != q.get('materialized_required_tests'):
            errors.append('certified output has unmaterialized required tests')

    if errors:
        print('VALIDATION FAILED')
        for err in errors:
            print(f'- {err}')
        return 1
    print(f"VALIDATION PASSED: {len(manifest.get('artifacts', []))} artifacts, {len(manifest.get('bundles', []))} bundles")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
