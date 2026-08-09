#!/usr/bin/env python3
from pathlib import Path
import sys,json,subprocess
from _common import load,dump,valid_digest,real_files,resolve_evidence
CFG=load(Path(__file__).with_name('config.json'))
def main():
 p=Path(sys.argv[1]); failures=[]
 if subprocess.run([sys.executable,str(Path(__file__).with_name('validate_pack.py')),str(p)]).returncode: failures.append('pack validation failed')
 try:
  pack=load(p/'pack.json'); ev=load(p/'certification/evidence.json'); cert=load(p/'certification/certification.json')
 except Exception as e: print('GATE FAIL '+str(e),file=sys.stderr); return 2
 requested=pack.get('status')=='certified' or cert.get('status')=='certified'
 if pack.get('status')!=cert.get('status'): failures.append('pack and certification status mismatch')
 if requested:
  if pack.get('owner') in ['',None,'REPLACE_ME']: failures.append('real owner required')
  if not valid_digest(pack.get('artifact_digest')) or not valid_digest(pack.get('environment_digest')): failures.append('real artifact and environment digests required')
  metrics={}; metrics.update(ev.get('metrics',{})); metrics.update(cert.get('metrics',{}))
  for k,t in CFG['METRICS'].items():
   try: v=float(metrics.get(k,0))
   except Exception: v=0
   if v < float(t): failures.append(f'{k} below {t}')
  zero={}; zero.update(ev.get('zero_tolerance',{})); zero.update(cert.get('zero_tolerance',{}))
  for k in CFG['ZERO_TOLERANCE']:
   if zero.get(k,1)!=0: failures.append(f'{k} must be zero')
  for rel in ['corpus/holdout','corpus/representative-workloads']:
   if not real_files(p/rel): failures.append(rel+' empty')
  refs=ev.get('evidence_refs',[])+cert.get('evidence_refs',[])
  if not refs: failures.append('evidence refs empty')
  for ref in refs:
   ok,msg=resolve_evidence(p,ref)
   if not ok: failures.append(msg+': '+str(ref))
  approved=cert.get('approved_by',[])
  if not approved: failures.append('accountable approval required')
  if CFG['BATCH']==45:
   if len(set(pack.get('required_batches',[]))) < 24: failures.append('Batch 45 must bind Batch 21-44')
   customer=real_files(p/'evidence/customer'); independent=real_files(p/'evidence/independent')
   if len(customer)<2: failures.append('two independent customer evidence files required')
   if not independent: failures.append('independent third-party evidence required')
 result={'schema_version':1,'pack_key':pack.get('pack_key'),'status':'failed' if failures else 'passed','claimed_status':pack.get('status'),'failures':failures}
 dump(p/'certification/gate-result.json',result)
 report=['# Batch 38 Gate', '',f"- Pack: `{pack.get('pack_key')}`",f"- Status: `{result['status']}`",'']
 report += ['## Failures']+[f'- {x}' for x in failures] if failures else ['No gate failures detected.']
 (p/'certification/gate-report.md').write_text('\n'.join(report)+'\n')
 if failures: print('\n'.join('GATE FAIL: '+x for x in failures),file=sys.stderr); return 2
 print('GATE PASS'); return 0
if __name__=='__main__': raise SystemExit(main())
