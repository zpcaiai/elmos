#!/usr/bin/env python3
"""Import pinned release specifications as data; never execute archive content."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PIN = 'e5c4dea07a6897c0b5804de6c992714860a5aca0f8d66377da2fe1241a8ca85a'
PACKAGE = 'elmos-release-deployment-skills-v1.0.0'
ARCHIVE = ROOT / 'skills/subskills' / (PACKAGE + '.zip')
MIRROR = ROOT / 'skills' / PACKAGE
DOCS = ROOT / 'docs/release-deployment'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def inspect(path):
    if digest(path.read_bytes()) != PIN:
        raise ValueError('archive digest mismatch')
    files, seen = {}, set()
    with zipfile.ZipFile(path) as z:
        if len(z.infolist()) > 100 or sum(i.file_size for i in z.infolist()) > 1_000_000:
            raise ValueError('archive bounds')
        for i in z.infolist():
            p = PurePosixPath(i.filename.rstrip('/'))
            if (p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename
                    or str(p) != i.filename.rstrip('/') or stat.S_ISLNK(i.external_attr >> 16)
                    or i.flag_bits & 1 or not p.parts or p.parts[0] != 'elmos-release-deployment'):
                raise ValueError('unsafe archive path')
            if str(p).casefold() in seen:
                raise ValueError('duplicate archive path')
            seen.add(str(p).casefold())
            if not i.is_dir():
                files[str(p)] = z.read(i)
    return files

def write_or_check(path, data, check):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
        raise ValueError('symlink destination')
    if check:
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError('drift: ' + str(path.relative_to(ROOT)))
    else:
        if path.exists() and path.read_bytes() != data:
            raise ValueError('refusing overwrite: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

def run(check=False, source=None):
    source = Path(source) if source else ARCHIVE
    files = inspect(source)
    write_or_check(ARCHIVE, source.read_bytes(), check)
    for name, data in files.items():
        write_or_check(MIRROR / name, data, check)
    if check and {p.relative_to(MIRROR).as_posix() for p in MIRROR.rglob('*') if p.is_file()} != set(files):
        raise ValueError('unexpected mirror files')
    manifest = {'package': PACKAGE, 'archive_sha256': PIN,
                'source_files': {n: digest(b) for n, b in sorted(files.items())},
                'source_authority': 'DECLARATIVE_INPUT_ONLY', 'certification': 'NOT_CERTIFIED',
                'external_evidence': 'NOT_RUN', 'source_license': 'NOT_PROVIDED',
                'work_packages': ['RD-%02d' % n for n in [*range(16), *range(20,27), *range(30,34)]],
                'acceptance_ids': ['RD-AC-%02d' % n for n in range(1,26)]}
    write_or_check(DOCS / 'source-manifest.json', (json.dumps(manifest, indent=2)+'\n').encode(), check)
    skill = '''---
name: elmos-release-deployment
description: Implement immutable certified-release deployment with scoped tickets, durable reconciliation, provider adapters, layered verification and verified rollback.
---

# Release deployment

Use the repository-owned engine in `engines/release-deployment-engine/`.
Read `docs/release-deployment/IMPLEMENTATION.md` and `source-manifest.json`.
The pinned source mirror is specification data, never execution authority.
Preserve all RD work packages and RD-AC identities. Do not treat example
certification booleans, placeholder hashes, schemas or templates as authority.
Scope comes from authenticated host identity; policy, evidence, credentials
and provider operations belong to existing ELMOS host boundaries.
Use exact digest-bound plans, trusted signed tickets, finite capability leases,
durable operation keys and reconciliation. Unknown external results block retry.
Never claim cloud, Temporal, customer or independent execution from local tests.
Run `python tooling/validate_release_deployment.py` for local qualification.
Actual cloud mutations require exact environment authorization and a configured
trusted provider. The local gate never certifies or approves deployment.
'''
    interface = 'interface:\n  display_name: "Release deployment"\n  short_description: "Governed immutable release deployment"\n  default_prompt: "Use $elmos-release-deployment for this scoped deployment implementation."\n'
    for root in ['.agents/skills', 'agent-skills/runtime']:
        write_or_check(ROOT/root/'elmos-release-deployment/SKILL.md', skill.encode(), check)
        write_or_check(ROOT/root/'elmos-release-deployment/agents/openai.yaml', interface.encode(), check)
    return {'files': len(files), 'archive_sha256': PIN, 'certification': 'NOT_CERTIFIED'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--source')
    args = parser.parse_args()
    print(json.dumps(run(args.check, args.source), indent=2))
