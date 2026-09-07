#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path

EXPECTED = 20

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.agents/skills')
    errors: list[str] = []
    names: dict[str, Path] = {}
    files = sorted(root.glob('*/SKILL.md'))
    batch = [f for f in files if f.parent.name.startswith('b32-')]
    if not batch:
        errors.append(f'no Batch 32 skills found under {root}')
    for path in batch:
        text = path.read_text()
        match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
        if not match:
            errors.append(f'{path}: missing YAML front matter')
            continue
        metadata: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
        for key in ('name', 'description'):
            if not metadata.get(key):
                errors.append(f'{path}: missing {key}')
        name = metadata.get('name', '')
        if not re.fullmatch(r'[a-z0-9-]{1,64}', name):
            errors.append(f'{path}: invalid name {name!r}')
        if name in names:
            errors.append(f'{path}: duplicate name also in {names[name]}')
        names[name] = path
        if len(metadata.get('description', '')) < 50:
            errors.append(f'{path}: description too vague/short')
        for heading in (
            '## Workflow',
            '## Verification',
            '## Stop and escalate when',
            '## Definition of done',
        ):
            if heading not in text:
                errors.append(f'{path}: missing heading {heading}')
    if len(batch) != EXPECTED:
        errors.append(f'expected {EXPECTED} Batch 32 skills, found {len(batch)}')
    if errors:
        print('\n'.join('ERROR: ' + error for error in errors), file=sys.stderr)
        return 1
    print(f'OK: {len(batch)} Batch 32 skills')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
