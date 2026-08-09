from pathlib import Path
import re,sys
r=Path(sys.argv[1] if len(sys.argv)>1 else '.'); fs=[p for p in (r/'.agents/skills').glob('tst-*/SKILL.md') if 'b38-45' in str(p) or any(x in p.parent.name for x in ['tst-b38-','tst-b39-','tst-b40-','tst-b41-','tst-b42-','tst-b43-','tst-b44-','tst-b45-','tst-edition-','tst-mixed-','tst-airgap-','tst-slo-','tst-backup-','tst-supply-','tst-compliance-','tst-knowledge-','tst-agent-','tst-model-','tst-api-','tst-metering-','tst-customer-','tst-cross-','tst-privacy-','tst-performance-','tst-evidence-'])]
assert len(fs)==30,len(fs); names=[]
for p in fs:
 s=p.read_text(); m=re.search(r'^name:\s*(\S+)',s,re.M); assert m and '## Workflow' in s and '## Definition of done' in s; names.append(m.group(1))
assert len(names)==len(set(names)); print('skills ok: 30')
