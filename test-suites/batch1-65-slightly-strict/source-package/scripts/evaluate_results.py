#!/usr/bin/env python3
import json, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
profile=json.loads((root/'references/STRICTNESS_PROFILE.json').read_text())
run=json.loads(Path(sys.argv[1]).read_text())
results=run.get('results',[])
blockers=[]; warnings=[]
bysev={s:[] for s in ['CRITICAL','HIGH','MEDIUM','LOW']}
for r in results: bysev.setdefault(r['severity'],[]).append(r)
def rate(items):
    applicable=[r for r in items if r['status'] not in ['NOT_APPLICABLE']]
    return 1.0 if not applicable else sum(r['status']=='PASSED' for r in applicable)/len(applicable)
allapp=[r for r in results if r['status']!='NOT_APPLICABLE']
metrics={'overall_pass_rate':rate(allapp)}
for sev in bysev: metrics[sev.lower()+'_pass_rate']=rate(bysev[sev])
critical_failed=any(r['severity']=='CRITICAL' and r['status']!='PASSED' for r in allapp)
if critical_failed: blockers.append('any_failed_critical_case')
if metrics['high_pass_rate'] < profile['thresholds']['high_pass_rate_min']: blockers.append('high_pass_rate_below_threshold')
if metrics['overall_pass_rate'] < profile['thresholds']['overall_pass_rate_min']: blockers.append('overall_pass_rate_below_threshold')
if any(r['severity'] in ['CRITICAL','HIGH'] and not r.get('evidence_complete',False) for r in allapp): blockers.append('incomplete_critical_high_evidence')
if any(r['status']=='SKIPPED' for r in allapp): blockers.append('hidden_or_unapproved_skip')
q=[r for r in allapp if r['status']=='QUARANTINED']
metrics['quarantined_rate']=len(q)/len(allapp) if allapp else 0
if any(r['severity'] in ['CRITICAL','HIGH'] for r in q): blockers.append('critical_or_high_quarantined')
if metrics['quarantined_rate'] > profile['thresholds']['quarantined_rate_max']: blockers.append('quarantine_rate_above_threshold')
out={'decision':'FAIL' if blockers else 'PASS','profile_id':profile['profile_id'],'metrics':metrics,'blockers':sorted(set(blockers)),'warnings':warnings}
print(json.dumps(out,indent=2))
sys.exit(1 if blockers else 0)
