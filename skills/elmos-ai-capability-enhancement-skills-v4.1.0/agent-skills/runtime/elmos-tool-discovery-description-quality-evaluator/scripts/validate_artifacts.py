#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-tool-discovery-description-quality-evaluator/profile.yaml', 'artifacts/elmos-tool-discovery-description-quality-evaluator/plan.json', 'artifacts/elmos-tool-discovery-description-quality-evaluator/result.json', 'artifacts/elmos-tool-discovery-description-quality-evaluator/evidence/']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
