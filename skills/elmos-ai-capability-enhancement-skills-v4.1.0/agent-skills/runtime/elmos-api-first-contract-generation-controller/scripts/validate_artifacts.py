#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-api-first-contract-generation-controller/profile.yaml', 'artifacts/elmos-api-first-contract-generation-controller/plan.json', 'artifacts/elmos-api-first-contract-generation-controller/result.json', 'artifacts/elmos-api-first-contract-generation-controller/evidence/']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
