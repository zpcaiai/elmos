#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-critical-infrastructure-ai-resilience-profile/profile.yaml', 'artifacts/elmos-critical-infrastructure-ai-resilience-profile/plan.json', 'artifacts/elmos-critical-infrastructure-ai-resilience-profile/result.json', 'artifacts/elmos-critical-infrastructure-ai-resilience-profile/evidence/', 'artifacts/elmos-critical-infrastructure-ai-resilience-profile/assurance-case.json']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
