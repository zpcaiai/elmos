#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-machine-verifiable-certificate-profile-compiler/profile.yaml', 'artifacts/elmos-machine-verifiable-certificate-profile-compiler/plan.json', 'artifacts/elmos-machine-verifiable-certificate-profile-compiler/result.json', 'artifacts/elmos-machine-verifiable-certificate-profile-compiler/evidence/', 'artifacts/elmos-machine-verifiable-certificate-profile-compiler/assurance-case.json']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
