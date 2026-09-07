#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-autonomous-system-safety-case-profile/profile.yaml', 'artifacts/elmos-autonomous-system-safety-case-profile/plan.json', 'artifacts/elmos-autonomous-system-safety-case-profile/result.json', 'artifacts/elmos-autonomous-system-safety-case-profile/evidence/', 'artifacts/elmos-autonomous-system-safety-case-profile/assurance-case.json']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
