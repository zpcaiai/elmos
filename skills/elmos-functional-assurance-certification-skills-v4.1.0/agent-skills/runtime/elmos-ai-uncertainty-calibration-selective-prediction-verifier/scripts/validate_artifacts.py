#!/usr/bin/env python3
from pathlib import Path
import json,sys
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
required=['artifacts/elmos-ai-uncertainty-calibration-selective-prediction-verifier/profile.yaml', 'artifacts/elmos-ai-uncertainty-calibration-selective-prediction-verifier/plan.json', 'artifacts/elmos-ai-uncertainty-calibration-selective-prediction-verifier/result.json', 'artifacts/elmos-ai-uncertainty-calibration-selective-prediction-verifier/evidence/', 'artifacts/elmos-ai-uncertainty-calibration-selective-prediction-verifier/assurance-case.json']
missing=[x for x in required if not (root/x).exists()]
print(json.dumps({'status':'PASS' if not missing else 'FAIL','root':str(root.resolve()),'missing':missing},indent=2))
raise SystemExit(0 if not missing else 1)
