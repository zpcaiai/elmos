from pathlib import Path
import re,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
files=sorted((root/'.agents/skills').glob('b46-*/SKILL.md'))
assert len(files)==40, len(files)
names=[]; ids=[]
for p in files:
 s=p.read_text(encoding='utf-8')
 m=re.search(r'^name:\s*(\S+)',s,re.M); i=re.search(r'^# Skill (\d+)',s,re.M)
 assert m and i and '## 实施流程' in s and '## 验证' in s and '## 完成定义' in s and '## 停止与升级' in s
 names.append(m.group(1)); ids.append(int(i.group(1)))
assert len(names)==len(set(names)); assert set(ids)==set(range(1497,1537))
print('Batch 46 complete skills ok: 40')
