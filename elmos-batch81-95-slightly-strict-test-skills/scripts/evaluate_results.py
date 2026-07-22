#!/usr/bin/env python3
import json, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
profile=json.loads((root/'references'/'STRICTNESS_PROFILE.json').read_text())['thresholds']
results=json.loads(Path(sys.argv[1]).read_text())
if isinstance(results,dict): results=results.get('results',[])
blocking=[]
if not results: blocking.append('no results')
def rate(items,pred): return (sum(1 for x in items if pred(x))/len(items)) if items else 0.0
crit=[x for x in results if x.get('severity')=='critical']
high=[x for x in results if x.get('severity')=='high']
metrics={
 'critical_pass_rate':rate(crit,lambda x:x.get('status')=='passed'),
 'high_pass_rate':rate(high,lambda x:x.get('status')=='passed'),
 'overall_pass_rate':rate(results,lambda x:x.get('status')=='passed'),
 'critical_high_evidence_completeness':rate(crit+high,lambda x:x.get('evidence_complete') is True),
 'overall_evidence_completeness':rate(results,lambda x:x.get('evidence_complete') is True),
 'flaky_rate':rate(results,lambda x:x.get('flaky') is True),
 'quarantine_rate':rate(results,lambda x:x.get('status')=='quarantined'),
}
for k in ['critical_pass_rate','high_pass_rate','overall_pass_rate','critical_high_evidence_completeness','overall_evidence_completeness']:
 if metrics[k] < profile[k]: blocking.append(f'{k} below threshold')
for k in ['flaky_rate','quarantine_rate']:
 maxk='max_'+k
 if metrics[k] > profile[maxk]: blocking.append(f'{k} above threshold')
covered=set()
for r in results:
 if r.get('status') in ('passed','failed','blocked','quarantined'):
  covered.update(r.get('target_skills',[]))
metrics['direct_source_skill_coverage']=len({x for x in covered if x.startswith('PG') and 223<=int(x[2:])<=402})/180
if metrics['direct_source_skill_coverage']<1.0: blocking.append('direct source Skill coverage incomplete')
for r in results:
 for f in r.get('findings',[]):
  if f.get('zero_tolerance') is True: blocking.append(f"zero-tolerance finding in {r.get('case_id')}")
out={'suite':'elmos-batch81-95-slightly-strict-tests','decision':'failed' if blocking else 'passed','metrics':metrics,'blocking_reasons':sorted(set(blocking))}
print(json.dumps(out,indent=2))
sys.exit(1 if blocking else 0)
