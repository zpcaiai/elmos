
from pathlib import Path
import re, sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
files=sorted((root/'.agents'/'skills').glob('conv-*/SKILL.md'))
assert len(files)==32, f'expected 32, got {len(files)}'
names=[]; ids=[]
for p in files:
 s=p.read_text(encoding='utf-8')
 m=re.search(r'^name:\s*(\S+)',s,re.M); i=re.search(r'^#\s+(CONV-\d{3})',s,re.M)
 assert m and i and '## Workflow' in s and '## Verification' in s and '## Stop / escalate' in s and '## Definition of done' in s
 names.append(m.group(1)); ids.append(i.group(1))
assert len(names)==len(set(names)); assert len(ids)==len(set(ids))
print('convergence skills ok: 32')
