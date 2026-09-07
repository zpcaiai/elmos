from pathlib import Path
import json, hashlib, re, sys
HEX=set("0123456789abcdef")
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def valid_digest(s): return isinstance(s,str) and len(s)==64 and set(s)<=HEX and len(set(s))>1
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()

def main():
 root=Path(sys.argv[1]); d=load(root/'readiness-gate.json'); criteria=d.get('criteria',{})
 required=['unified_core','private_runner','reference_engine','reference_route','validation_lab','maintainability','customer_handoff','unit_economics']
 ok=all(criteria.get(k) is True for k in required)
 orgs={x.get('organization_id') for x in d.get('design_partner_evidence',[]) if x.get('accepted') and x.get('independent') and valid_digest(x.get('artifact_sha256'))}
 reviews=[x for x in d.get('independent_review_evidence',[]) if x.get('accepted') and x.get('independent') and valid_digest(x.get('artifact_sha256'))]
 ok=ok and len(orgs)>=2 and len(reviews)>=1 and not d.get('zero_tolerance_findings') and valid_digest(d.get('artifact_sha256')) and valid_digest(d.get('environment_sha256'))
 result={'status':'passed' if ok else 'failed','criteria':criteria,'design_partner_organizations':len(orgs),'independent_reviews':len(reviews),'zero_tolerance_findings':d.get('zero_tolerance_findings',[])}
 (root/'results'/'convergence-gate-result.json').parent.mkdir(parents=True,exist_ok=True); (root/'results'/'convergence-gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2)); raise SystemExit(0 if ok else 1)
if __name__=='__main__': main()
