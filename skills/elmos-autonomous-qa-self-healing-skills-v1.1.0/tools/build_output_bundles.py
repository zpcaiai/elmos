#!/usr/bin/env python3
"""Build deterministic Elmos output ZIP bundles from a project output manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
CATEGORY_SETS = {
    'project-with-tests': {
        'application_source', 'application_config', 'test_source', 'test_config',
        'test_fixture', 'test_data', 'test_mock', 'test_baseline', 'ci_config',
        'replay_script', 'manifest'
    },
    'tests-only': {
        'test_source', 'test_config', 'test_fixture', 'test_data', 'test_mock',
        'test_baseline', 'ci_config', 'replay_script', 'manifest'
    },
    'qa-evidence': {
        'test_plan', 'traceability', 'test_result', 'report', 'evidence', 'coverage',
        'performance_baseline', 'security_result', 'defect', 'patch', 'certificate', 'manifest'
    },
    'repair-patches': {'patch', 'defect', 'replay_script', 'manifest'},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(rel: str) -> str:
    p = PurePosixPath(rel.replace('\\', '/'))
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError(f'unsafe relative path: {rel!r}')
    return p.as_posix()


def zip_add_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
    zf.writestr(info, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('deliverable_root')
    parser.add_argument('--kinds', default='project-with-tests,tests-only,qa-evidence')
    args = parser.parse_args()

    root = Path(args.deliverable_root).resolve()
    manifest_path = root / 'manifests' / 'project-output-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    output_id = manifest['output_id']
    project_id = manifest['project_id']
    revision_id = manifest['revision_id']
    artifacts = manifest.get('artifacts', [])
    bundles_dir = root / 'bundles'
    bundles_dir.mkdir(parents=True, exist_ok=True)
    built = []

    for kind in [x.strip() for x in args.kinds.split(',') if x.strip()]:
        if kind not in CATEGORY_SETS:
            raise SystemExit(f'unknown bundle kind: {kind}')
        selected = [a for a in artifacts if a.get('category') in CATEGORY_SETS[kind]]
        if kind == 'repair-patches' and not any(a.get('category') == 'patch' for a in selected):
            continue
        filename = f'{project_id}-{revision_id}-{kind}.zip'
        bundle_path = bundles_dir / filename
        content_manifest = {
            'output_id': output_id,
            'kind': kind,
            'files': [
                {'path': safe_rel(a['path']), 'sha256': a['sha256'], 'size_bytes': a['size_bytes'], 'artifact_id': a['artifact_id']}
                for a in sorted(selected, key=lambda x: x['path'])
            ],
        }
        with zipfile.ZipFile(bundle_path, 'w') as zf:
            for artifact in sorted(selected, key=lambda x: x['path']):
                rel = safe_rel(artifact['path'])
                source = root / rel
                if not source.is_file() or source.is_symlink():
                    raise SystemExit(f'missing or unsafe artifact: {rel}')
                info = zipfile.ZipInfo(rel, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                executable = os.access(source, os.X_OK)
                info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
                zf.writestr(info, source.read_bytes())
            zip_add_bytes(
                zf,
                'bundle-content-manifest.json',
                (json.dumps(content_manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            )
        digest = sha256_file(bundle_path)
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        built.append({
            'bundle_id': f'bundle_{output_id}_{kind}',
            'output_id': output_id,
            'kind': kind,
            'format': 'zip',
            'path': bundle_path.relative_to(root).as_posix(),
            'sha256': digest,
            'size_bytes': bundle_path.stat().st_size,
            'status': 'verified',
            'created_at': now,
            'verified_at': now,
            'file_count': len(selected) + 1,
            'includes_categories': sorted(CATEGORY_SETS[kind]),
            'manifest_ref': 'bundle-content-manifest.json',
            'content_manifest_path': 'bundle-content-manifest.json',
        })

    manifest['bundles'] = built
    manifest['published_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    checksums = []
    for path in sorted(p for p in root.rglob('*') if p.is_file() and p != root / 'manifests' / 'checksums.sha256'):
        checksums.append(f'{sha256_file(path)}  {path.relative_to(root).as_posix()}')
    (root / 'manifests' / 'checksums.sha256').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
    print(f'Built {len(built)} bundles in {bundles_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
