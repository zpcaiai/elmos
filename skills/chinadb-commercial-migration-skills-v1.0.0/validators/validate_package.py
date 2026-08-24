#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'PACKAGE_MANIFEST.json').read_text())
required=['## Objective','## Inputs','## Required outputs','## Implementation modules / repository contract','## Workflow','## Mandatory tests','## Required evidence','## Definition of Done']
errors=[]
skills=sorted((root/'skills').glob('*/SKILL.md'))
if len(skills)!=manifest['skill_count']:
    errors.append(f"skill count mismatch: manifest={manifest['skill_count']} files={len(skills)}")
for p in skills:
    t=p.read_text(encoding='utf-8')
    for h in required:
        if h not in t: errors.append(f'{p}: missing {h}')
    if 'specification only until repository evidence proves otherwise' not in t:
        errors.append(f'{p}: missing specification-only status contract')
    if re.search(r'\b(TODO|FIXME)\b',t): errors.append(f'{p}: TODO/FIXME present')
for s in ['evidence.schema.json','route-manifest.schema.json','conversion-result.schema.json','repair-plan.schema.json','certification.schema.json']:
    try: json.loads((root/'schemas'/s).read_text())
    except Exception as e: errors.append(f'{s}: invalid json {e}')
if errors:
    print('PACKAGE VALIDATION FAILED')
    print('\n'.join(errors)); sys.exit(1)
print(f"PACKAGE STRUCTURE VALID: {len(skills)} skills")
print('NOTE: This validates package structure only; it does not claim any product implementation is complete.')
