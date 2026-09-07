#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-modular-monolith-microservice-boundary-analyzer/profile.yaml', 'artifacts/elmos-modular-monolith-microservice-boundary-analyzer/plan.json', 'artifacts/elmos-modular-monolith-microservice-boundary-analyzer/result.json', 'artifacts/elmos-modular-monolith-microservice-boundary-analyzer/evidence/']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
