#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-auditor-evaluator-competence-authorization-controller/profile.yaml', 'artifacts/elmos-auditor-evaluator-competence-authorization-controller/plan.json', 'artifacts/elmos-auditor-evaluator-competence-authorization-controller/result.json', 'artifacts/elmos-auditor-evaluator-competence-authorization-controller/evidence/', 'artifacts/elmos-auditor-evaluator-competence-authorization-controller/assurance-case.json']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
