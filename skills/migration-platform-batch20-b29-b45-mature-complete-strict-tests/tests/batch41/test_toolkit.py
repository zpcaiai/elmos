from __future__ import annotations
import json, tempfile, subprocess, sys, hashlib, shutil
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
S=ROOT/'scripts/batch41'
class Toolkit(unittest.TestCase):
 def invoke(self,*args,ok=True):
  r=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,capture_output=True,text=True)
  if ok and r.returncode: self.fail(r.stdout+r.stderr)
  if not ok and r.returncode==0: self.fail('expected failure')
  return r
 def test_skill_bundle(self): self.invoke(S/'validate_skill_bundle.py',ROOT)
 def test_scaffold_validate(self):
  with tempfile.TemporaryDirectory() as td:
   self.invoke(S/'scaffold_pack.py','--pack-key','x','--output-root',td)
   self.invoke(S/'validate_pack.py',Path(td)/'x')
 def test_fake_certified_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   self.invoke(S/'scaffold_pack.py','--pack-key','x','--output-root',td); p=Path(td)/'x'
   pack=json.loads((p/'pack.json').read_text()); pack['status']='certified'; pack['owner']='owner'; pack['artifact_digest']='sha256:'+'1'*64; pack['environment_digest']='sha256:'+'2'*64; (p/'pack.json').write_text(json.dumps(pack))
   cert=json.loads((p/'certification/certification.json').read_text()); cert['status']='certified'; (p/'certification/certification.json').write_text(json.dumps(cert))
   self.invoke(S/'run_gate.py',p,ok=False)
 def test_positive_gate(self):
  with tempfile.TemporaryDirectory() as td:
   self.invoke(S/'scaffold_pack.py','--pack-key','x','--output-root',td); p=Path(td)/'x'
   art='sha256:'+'1'*64; env='sha256:'+'2'*64
   pack=json.loads((p/'pack.json').read_text()); pack.update(status='certified',owner='owner',artifact_digest=art,environment_digest=env); (p/'pack.json').write_text(json.dumps(pack))
   for d in ['corpus/holdout','corpus/representative-workloads']:
    (p/d/'case.json').write_text('{"ok":true}')
   raw=p/'evidence/raw/run.json'; raw.parent.mkdir(parents=True,exist_ok=True); raw.write_text('{"real":"tool-output"}')
   ref={'path':'evidence/raw/run.json','sha256':'sha256:'+hashlib.sha256(raw.read_bytes()).hexdigest(),'artifact_digest':art,'environment_digest':env}
   metrics={k:1.0 for k in ['ontology_coverage', 'knowledge_lineage_coverage', 'private_knowledge_isolation_pass_rate', 'recommendation_precision_at_k', 'risk_calibration_score', 'forecast_interval_coverage', 'holdout_pass_rate', 'human_review_closure_rate', 'evidence_trace_coverage']}; zero={k:0 for k in ['private_knowledge_leaks', 'target_leakage_findings', 'unattributed_knowledge_items', 'uncalibrated_p0_predictions', 'unsafe_recommendations', 'expired_certified_assets_used', 'cross_tenant_reconstruction_findings', 'test_integrity_violations']}
   for rel in ['certification/evidence.json','certification/certification.json']:
    o=json.loads((p/rel).read_text()); o['metrics']=metrics; o['zero_tolerance']=zero; o['evidence_refs']=[ref]
    if rel.endswith('certification.json'): o.update(status='certified',approved_by=['accountable-owner'])
    (p/rel).write_text(json.dumps(o))
   if 41==45:
    for folder,name in [('evidence/customer','a.json'),('evidence/customer','b.json'),('evidence/independent','review.json')]:
     q=p/folder/name; q.parent.mkdir(parents=True,exist_ok=True); q.write_text('{"accepted":true}')
   self.invoke(S/'run_gate.py',p)
if __name__=='__main__': unittest.main()
