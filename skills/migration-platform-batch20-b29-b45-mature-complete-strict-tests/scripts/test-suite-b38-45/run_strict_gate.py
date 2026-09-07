from pathlib import Path
import json,sys,hashlib,re
s=Path(sys.argv[1]); p=json.load(open(s/'strict-profile.json')); cat=json.load(open(s/'cases/catalog.json'))['cases']; gate=json.load(open(s/'release-gate.json')); cnt={k:[0,0] for k in ['P0','P1','P2']}; bad=[]
def good(x): return isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) and len(set(x))>1
for c in cat:
 r=json.load(open(s/'results'/f"{c['case_id']}.json")); cnt[c['priority']][1]+=1
 if r.get('status')=='passed':
  assert good(r.get('artifact_sha256')) and good(r.get('environment_sha256')) and r.get('evidence_manifest') and r.get('replay_command'); mp=s/r['evidence_manifest']; assert mp.is_file(); m=json.load(open(mp)); assert m['case_id']==c['case_id'] and m['artifact_sha256']==r['artifact_sha256'] and m['environment_sha256']==r['environment_sha256'];
  for f in m['files']:
   fp=(s/f['path']).resolve(); assert s.resolve() in fp.parents and fp.is_file() and hashlib.sha256(fp.read_bytes()).hexdigest()==f['sha256']
  cnt[c['priority']][0]+=1
 else: bad.append(c['case_id'])
rates={k:v[0]/v[1] for k,v in cnt.items()}; th=p['thresholds']; orgs={x.get('organization_id') for x in gate.get('design_partner_evidence',[]) if x.get('accepted') and x.get('independent')}; rev=[x for x in gate.get('independent_review_evidence',[]) if x.get('accepted') and x.get('independent')]; ok=rates['P0']>=1 and rates['P1']>=1 and rates['P2']>=.98 and len(orgs)>=2 and len(rev)>=1 and not gate.get('zero_tolerance_findings'); out={'status':'passed' if ok else 'failed','rates':rates,'design_partner_organizations':len(orgs),'independent_reviews':len(rev),'failures':len(bad)}; json.dump(out,open(s/'strict-gate-result.json','w'),indent=2); print(json.dumps(out,indent=2)); raise SystemExit(0 if ok else 1)
