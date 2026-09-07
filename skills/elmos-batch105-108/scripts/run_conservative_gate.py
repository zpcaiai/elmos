#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('candidate'); p.add_argument('--out',default='gate-decision.json'); a=p.parse_args(); c=json.loads(Path(a.candidate).read_text())
required=['schemaVersion','runId','repository','baselineCommit','candidateCommit','imageDigest','readyAt','expiresAt','destroyedAt','health','apiValidation','browserValidation','cleanupAttestation','artifactDigests']
missing=[k for k in required if k not in c]; reasons=[]
if missing: reasons.append('missing:'+','.join(missing))
for k in ['health','apiValidation','browserValidation','cleanupAttestation']:
 if c.get(k) not in ['PASS','NOT_APPLICABLE']: reasons.append(f'{k}={c.get(k)}')
if c.get('claimedCertificate'): reasons.append('caller-provided certificate claim is not trusted')
if not c.get('artifactDigests'): reasons.append('no artifact digests')
status='PASS' if not reasons else 'REJECTED'
d={'status':status,'reasons':reasons,'trustedClaims':['RUNTIME_VERIFIED'] if status=='PASS' else []}
Path(a.out).write_text(json.dumps(d,indent=2)+'\n'); print(json.dumps(d,indent=2)); sys.exit(0 if status=='PASS' else 2)
