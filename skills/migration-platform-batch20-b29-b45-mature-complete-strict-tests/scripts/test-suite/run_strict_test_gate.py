#!/usr/bin/env python3
import json, sys, hashlib
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def verify_manifest(suite_root: Path, evidence_ref: str, case, result, blockers):
    p=(suite_root/evidence_ref).resolve()
    try:
        p.relative_to(suite_root.resolve())
    except ValueError:
        blockers.append(f"evidence path escapes suite for {case['id']}: {evidence_ref}"); return
    if not p.exists():
        blockers.append(f"missing evidence for {case['id']}: {evidence_ref}"); return
    try:
        manifest=load(p)
    except Exception as exc:
        blockers.append(f"invalid evidence manifest for {case['id']}: {evidence_ref}: {exc}"); return
    if manifest.get('case_id') != case['id']:
        blockers.append(f"evidence case mismatch {case['id']}: {evidence_ref}")
    if manifest.get('artifact_digest') != result.get('artifact_digest'):
        blockers.append(f"artifact digest mismatch in evidence {case['id']}")
    if manifest.get('environment_digest') != result.get('environment_digest'):
        blockers.append(f"environment digest mismatch in evidence {case['id']}")
    files=manifest.get('files',[])
    if not files:
        blockers.append(f"evidence manifest has no raw files {case['id']}")
    for item in files:
        raw=(p.parent/item.get('path','')).resolve()
        try:
            raw.relative_to(suite_root.resolve())
        except ValueError:
            blockers.append(f"raw evidence escapes suite {case['id']}: {item.get('path')}"); continue
        if not raw.exists():
            blockers.append(f"missing raw evidence {case['id']}: {raw}"); continue
        if digest_file(raw) != item.get('sha256'):
            blockers.append(f"raw evidence digest mismatch {case['id']}: {raw}")

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else 'test-suites/batch1-37-strict').resolve()
    cat=load(root/'cases/catalog.json'); profile=load(root/'strict-profile.json'); results_dir=root/'results'
    thresholds=profile['thresholds']; blockers=[]
    counts={'passed':0,'failed':0,'blocked':0,'not-run':0,'waived':0,'missing':0}
    totals={'critical_unknowns':0,'critical_security_findings':0,'tenant_isolation_violations':0,'test_integrity_violations':0,'stale_evidence':0,'unreplayed_critical_failures':0,'forged_certification_attempts':0,'flaky_p0_p1':0}
    trace_values=[]; affected_recall=[]; mutation_scores=[]; p95_regs=[]; p99_regs=[]; resource_regs=[]
    for c in cat['cases']:
        p=results_dir/f"{c['id']}.json"
        if not p.exists():
            counts['missing']+=1; blockers.append(f"missing result {c['id']}"); continue
        try: r=load(p)
        except Exception as exc:
            blockers.append(f"invalid result {c['id']}: {exc}"); continue
        if r.get('case_id') != c['id']: blockers.append(f"result case mismatch {c['id']}")
        st=r.get('status','not-run'); counts[st]=counts.get(st,0)+1
        if c['severity'] in {'P0','P1'} and st!='passed': blockers.append(f"{c['severity']} {c['id']} is {st}")
        for k in totals: totals[k]+=int(r.get(k,0) or 0)
        if st=='failed' and c['severity'] in {'P0','P1'} and not r.get('replay_command'):
            totals['unreplayed_critical_failures']+=1
        if st=='passed':
            zero='sha256:'+'0'*64
            if r.get('artifact_digest')==zero or r.get('environment_digest')==zero: blockers.append(f"placeholder digest for passed {c['id']}")
            if not r.get('started_at') or not r.get('finished_at'): blockers.append(f"missing timestamps for passed {c['id']}")
            evidence=r.get('evidence',[])
            if not evidence: blockers.append(f"no evidence for passed {c['id']}")
            for ref in evidence: verify_manifest(root,ref,c,r,blockers)
            tc=float(r.get('trace_coverage',0)); trace_values.append(tc)
            if tc < thresholds['evidence_trace_coverage']: blockers.append(f"trace coverage {tc:.3f} below threshold for {c['id']}")
            if c.get('holdout_required') and r.get('holdout_passed') is not True: blockers.append(f"holdout missing for {c['id']}")
            if c.get('representative_workload_required') and r.get('representative_workload_passed') is not True: blockers.append(f"representative workload missing for {c['id']}")
            if 'affected_test_recall' in r:
                v=float(r['affected_test_recall']); affected_recall.append(v)
                if v < thresholds['affected_test_recall']: blockers.append(f"affected test recall below threshold for {c['id']}")
            if 'mutation_score' in r:
                v=float(r['mutation_score']); mutation_scores.append(v)
                if v < thresholds['mutation_score']: blockers.append(f"mutation score below threshold for {c['id']}")
            if 'p95_latency_regression' in r:
                v=float(r['p95_latency_regression']); p95_regs.append(v)
                if v > thresholds['p95_latency_regression_max']: blockers.append(f"P95 regression too high for {c['id']}")
            if 'p99_latency_regression' in r:
                v=float(r['p99_latency_regression']); p99_regs.append(v)
                if v > thresholds['p99_latency_regression_max']: blockers.append(f"P99 regression too high for {c['id']}")
            if 'resource_regression' in r:
                v=float(r['resource_regression']); resource_regs.append(v)
                if v > thresholds['resource_regression_max']: blockers.append(f"resource regression too high for {c['id']}")
    for key,max_allowed in [('critical_unknowns',0),('critical_security_findings',0),('tenant_isolation_violations',0),('test_integrity_violations',0),('stale_evidence',0),('unreplayed_critical_failures',0),('forged_certification_attempts',0),('flaky_p0_p1',0)]:
        if totals[key] > max_allowed: blockers.append(f"{key} {totals[key]}")
    # Coverage is validated separately but duplicated here for defense in depth.
    covered={b:False for b in range(1,38)}
    for c in cat['cases']:
        for b in c.get('batches',[]):
            if 1<=b<=37: covered[b]=True
    missing_batches=[b for b,v in covered.items() if not v]
    if missing_batches: blockers.append(f"missing batch coverage {missing_batches}")
    status='passed' if not blockers else 'failed'
    evidence_input=json.dumps({'counts':counts,'totals':totals,'blockers':blockers},sort_keys=True).encode()
    gate={'gate_id':'batch1-37-strict','status':status,'metrics':{'counts':counts,**totals,'mean_trace_coverage':sum(trace_values)/len(trace_values) if trace_values else 0,'minimum_affected_test_recall':min(affected_recall) if affected_recall else None,'minimum_mutation_score':min(mutation_scores) if mutation_scores else None,'maximum_p95_latency_regression':max(p95_regs) if p95_regs else None,'maximum_p99_latency_regression':max(p99_regs) if p99_regs else None,'maximum_resource_regression':max(resource_regs) if resource_regs else None},'blockers':blockers,'evidence_digest':'sha256:'+hashlib.sha256(evidence_input).hexdigest()}
    (root/'release-gate.json').write_text(json.dumps(gate,indent=2)+"\n",encoding='utf-8')
    print(json.dumps(gate,indent=2)); return 0 if status=='passed' else 2
if __name__=='__main__': raise SystemExit(main())
