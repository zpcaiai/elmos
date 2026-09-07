#!/usr/bin/env python3
from __future__ import annotations
import re,sys
from pathlib import Path

import yaml

def main():
 root=Path(sys.argv[1] if len(sys.argv)>1 else '.agents/skills'); files=sorted(root.glob('b37-*/SKILL.md')); errors=[]; names=[]
 if len(files)!=36: errors.append(f'expected 36 Batch 37 skills, found {len(files)}')
 numeric_ids=[]; supplemental_ids=[]
 for p in files:
  text=p.read_text(); m=re.match(r'---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---',text)
  if not m: errors.append(f'invalid front matter: {p}'); continue
  name,desc=m.groups(); names.append(name)
  if name!=p.parent.name: errors.append(f'name mismatch: {p}')
  if len(desc)<80: errors.append(f'description too short: {name}')
  for h in ['## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
   if h not in text: errors.append(f'{name} missing {h}')
  numeric=re.findall(r'^#{1,2} Skill (\d+)(?::|\b)',text,re.MULTILINE)
  supplemental=re.findall(r'^#{1,2} Skill B37-X(\d+)(?::|\b)',text,re.MULTILINE)
  if len(numeric)+len(supplemental)!=1: errors.append(f'{name} must contain exactly one Skill ID')
  numeric_ids.extend(int(value) for value in numeric)
  supplemental_ids.extend(int(value) for value in supplemental)
  agent_path=p.parent/'agents'/'openai.yaml'
  if not agent_path.is_file(): errors.append(f'missing agents/openai.yaml: {name}')
  else:
   try: agent=yaml.safe_load(agent_path.read_text())
   except yaml.YAMLError as exc: errors.append(f'invalid agents/openai.yaml for {name}: {exc}'); agent={}
   prompt=agent.get('interface',{}).get('default_prompt','') if isinstance(agent,dict) else ''
   if f'${name}' not in prompt: errors.append(f'{name} default_prompt missing exact Skill invocation')
 if len(names)!=len(set(names)): errors.append('duplicate skill names')
 if sorted(numeric_ids)!=list(range(1305,1325)): errors.append(f'numeric Skill IDs mismatch: {sorted(numeric_ids)}')
 if sorted(supplemental_ids)!=list(range(1,17)): errors.append(f'supplemental Skill IDs mismatch: {sorted(supplemental_ids)}')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID SKILLS: {len(files)}'); return 0
if __name__=='__main__': raise SystemExit(main())
