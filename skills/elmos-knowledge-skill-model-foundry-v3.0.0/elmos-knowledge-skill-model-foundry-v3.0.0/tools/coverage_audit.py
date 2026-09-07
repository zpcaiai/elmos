#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import yaml
YAML_LOADER=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
def load_yaml(path): return yaml.load(path.read_text(encoding='utf-8'), Loader=YAML_LOADER)
ROOT=Path(__file__).resolve().parents[1]
cat=load_yaml(ROOT/'registry/skill-catalog.yaml')['spec']['skills']
bl=load_yaml(ROOT/'registry/business-line-catalog.yaml')['spec']['businessLines']
counts=Counter(x['pack'] for x in cat)
errors=[]
for item in bl:
    if counts[item['pack']] != item['atomicSkillCount']:
        errors.append(f"count mismatch {item['pack']}: {counts[item['pack']]} != {item['atomicSkillCount']}")
    required={'discover','model','plan','transform-or-generate','verify','release-or-cutover','operate','learn'}
    if not required.issubset(set(item['lifecycleCoverage'])):
        errors.append(f"lifecycle gap: {item['pack']}")
    if not item['requiredGates']:
        errors.append(f"no gates: {item['pack']}")
if errors:
    raise SystemExit('\n'.join(errors))
print(f"OK: {len(bl)} deep business lines; {sum(counts.values())} skills; lifecycle and gate coverage complete at specification level")
