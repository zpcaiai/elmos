#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.agents/skills')
    errors = []
    names = {}
    files = sorted(root.glob('*/SKILL.md'))
    b30_files = [f for f in files if f.parent.name.startswith('b30-')]
    if not b30_files:
        errors.append(f'no Batch 30 skills found under {root}')
    for path in b30_files:
        text = path.read_text()
        match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
        if not match:
            errors.append(f'{path}: missing YAML front matter')
            continue
        meta = {}
        for line in match.group(1).splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                meta[key.strip()] = value.strip()
        for key in ['name','description']:
            if not meta.get(key):
                errors.append(f'{path}: missing {key}')
        name = meta.get('name','')
        if not re.fullmatch(r'[a-z0-9-]{1,64}', name):
            errors.append(f'{path}: invalid name {name!r}')
        if name in names:
            errors.append(f'{path}: duplicate name also in {names[name]}')
        names[name] = path
        if len(meta.get('description','')) < 50:
            errors.append(f'{path}: description too vague/short')
        for heading in ['## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
            if heading not in text:
                errors.append(f'{path}: missing heading {heading}')
    if len(b30_files) != 20:
        errors.append(f'expected 20 Batch 30 skills, found {len(b30_files)}')
    if errors:
        print('\n'.join('ERROR: '+item for item in errors), file=sys.stderr)
        return 1
    print(f'OK: {len(b30_files)} Batch 30 skills')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
