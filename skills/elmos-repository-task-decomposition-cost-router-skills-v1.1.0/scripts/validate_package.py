from pathlib import Path
import yaml, re, sys
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={
"gpt-5.6-sol-max","claude-opus-5-max","claude-fable-5","grok-4.6","kimi-k3-max",
"glm-5.3-max","qwen3.8-max","deepseek-v4-pro-0813","gemini-3.7-flash-high","claude-sonnet-5"}
errors=[]
reg=yaml.safe_load((ROOT/'config/model-registry.yaml').read_text())
actual=set(reg['aliases'])
if actual != ALLOWED:
    errors.append(f"registry aliases mismatch: missing={ALLOWED-actual}, extra={actual-ALLOWED}")

# Ensure every concrete model-like alias referenced in machine-readable YAML/JSON configs/examples is allowed.
family_prefixes=('gpt-','claude-','grok-','kimi-','glm-','qwen','deepseek-','gemini-')
def walk(v, path='root'):
    if isinstance(v, dict):
        for k,x in v.items():
            yield from walk(x, f'{path}.{k}')
    elif isinstance(v, list):
        for i,x in enumerate(v):
            yield from walk(x, f'{path}[{i}]')
    elif isinstance(v, str):
        yield path, v
for p in list((ROOT/'config').glob('*.yaml')) + list((ROOT/'examples').glob('*.yaml')) + list((ROOT/'examples').glob('*.json')) + [ROOT/'manifest.json']:
    obj=yaml.safe_load(p.read_text()) if p.suffix in {'.yaml','.yml'} else __import__('json').loads(p.read_text())
    for loc,val in walk(obj):
        if loc.endswith('.display_name'):
            continue
        s=val.strip().lower()
        if s.startswith(family_prefixes) and s not in ALLOWED:
            # Ignore non-model prose values and task/skill names by requiring a digit after a model-family prefix.
            if re.search(r'(gpt-|claude-|grok-|kimi-|glm-|qwen|deepseek-|gemini-).*\d', s):
                errors.append(f"unknown model-like alias {val!r} in {p.name}:{loc}")


# Validate model-selection schema aliases are exactly the hard allowlist.
sel_schema=__import__('json').loads((ROOT/'schemas/model-selection.schema.json').read_text())
sel_enum=set(x for x in sel_schema['properties']['selected_model']['enum'] if x is not None)
if sel_enum != ALLOWED:
    errors.append(f"model-selection schema aliases mismatch: missing={ALLOWED-sel_enum}, extra={sel_enum-ALLOWED}")
sel_policy=yaml.safe_load((ROOT/'config/model-selection-policy.yaml').read_text())
if sel_policy.get('default_mode') not in {'smart','manual'}:
    errors.append('invalid model-selection default mode')

# Validate skill count and that workflow references real skill names.
skill_files=list((ROOT/'skills').glob('*/SKILL.md'))
if len(skill_files) != 37:
    errors.append(f"expected 37 skills, found {len(skill_files)}")
skill_names=set()
for sf in skill_files:
    for line in sf.read_text().splitlines()[:8]:
        if line.startswith('name: '):
            skill_names.add(line.split(':',1)[1].strip())
            break
wf=yaml.safe_load((ROOT/'examples/full-repository-workflow.yaml').read_text())
def collect_skills(v):
    if isinstance(v,dict):
        for k,x in v.items():
            if k=='skill' and isinstance(x,str): yield x
            else: yield from collect_skills(x)
    elif isinstance(v,list):
        for x in v: yield from collect_skills(x)
for s in collect_skills(wf):
    if s not in skill_names:
        errors.append(f"workflow references unknown skill: {s}")

if errors:
    print('INVALID')
    for e in errors: print('-',e)
    sys.exit(1)
print(f'VALID: exact 10-model hard allowlist, {len(skill_files)} skills, and workflow references verified')
