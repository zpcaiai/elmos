"""Metric math and integrity prechecks; not certification or statistical significance."""
import math,hashlib
from pathlib import Path,PurePosixPath

def ranked_metrics(ranking,relevance,k=5):
    if k<1 or any(type(g)!=int or not 0<=g<=3 for g in relevance.values()):raise ValueError('grades')
    ranks=list(dict.fromkeys(ranking))[:k];positive={x for x,g in relevance.items() if g>0}
    if not positive:return dict(answerable=False,recall=None,mrr=None,ndcg=None,returned_any=bool(ranks))
    gain=[relevance.get(x,0) for x in ranks];ideal=sorted(relevance.values(),reverse=True)[:k]
    dcg=lambda a:sum((2**g-1)/math.log2(i+2) for i,g in enumerate(a))
    first=next((i+1 for i,g in enumerate(gain) if g),None)
    return dict(answerable=True,recall=len(set(ranks)&positive)/len(positive),mrr=1/first if first else 0.,ndcg=dcg(gain)/dcg(ideal),returned_any=bool(ranks))

def nearest_rank(samples,p):
    if not samples or not 0<p<=1 or any(not math.isfinite(x) or x<0 for x in samples):raise ValueError('samples')
    return sorted(samples)[math.ceil(p*len(samples))-1]

def cost_per_accepted(costs,accepted,amortization=0.):
    if type(accepted)!=int or accepted<0 or not math.isfinite(amortization) or amortization<0 or any(not math.isfinite(x) or x<0 for x in costs):raise ValueError('cost')
    return (sum(costs)+amortization)/accepted if accepted else None

def compare_paired(b,c,min_quality_delta=.03,max_latency_ratio=1.10,max_cost_ratio=1.10):
    for key in ['dataset_digest','environment_digest','scope_digest','model_profile','warm_state']:
        if key not in b or b[key]!=c.get(key):raise ValueError('incomparable '+key)
    bs,cs=b['cases'],c['cases']
    if not bs or set(bs)!=set(cs) or min_quality_delta<=0:raise ValueError('paired cases')
    for group in [bs,cs]:
        for v in group.values():
            if not math.isfinite(v['latency_ms']) or v['latency_ms']<=0 or not 0<=v['quality']<=1 or type(v['leaks'])!=int or v['leaks']<0:raise ValueError('observation')
    delta=sum(cs[q]['quality']-bs[q]['quality'] for q in bs)/len(bs)
    ratio=nearest_rank([cs[q]['latency_ms']/bs[q]['latency_ms'] for q in bs],.95);leaks=sum(v['leaks'] for v in cs.values())
    bc,cc=b.get('total_attempt_cost'),c.get('total_attempt_cost');cr=None
    if isinstance(bc,(int,float)) and isinstance(cc,(int,float)) and math.isfinite(bc) and math.isfinite(cc) and bc>0 and cc>=0:cr=cc/bc
    return dict(n=len(bs),mean_quality_delta=delta,p95_paired_latency_ratio=ratio,cost_ratio=cr,security_leaks=leaks,pilot_eligible=delta>=min_quality_delta and ratio<=max_latency_ratio and cr is not None and cr<=max_cost_ratio and leaks==0,production_certified=False,statistical_claim='descriptive_only; cluster intervals and host review required')

REQUIRED_CHECKS=['host_mapping_review','real_consumer_e2e','tenant_acl_and_revocation','snapshot_and_tombstone','injection_and_redaction','paired_quality_latency_cost','rollback_and_compatibility','independent_host_review']

def preflight_release(report,artifact_root):
    reasons=[];root=Path(artifact_root).resolve()
    if report.get('environment_kind')!='actual_elmos':reasons.append('real Elmos not qualified')
    for name in REQUIRED_CHECKS:
        item=report.get('checks',{}).get(name,{})
        if item.get('status')!='pass':reasons.append(name+': missing/not_run/failed');continue
        rel=item.get('artifact') or '';p=PurePosixPath(rel)
        if not rel or p.is_absolute() or '..' in p.parts or '\\' in rel or '\x00' in rel:reasons.append(name+': unsafe evidence');continue
        if any(root.joinpath(*p.parts[:n]).is_symlink() for n in range(1,len(p.parts)+1)):reasons.append(name+': symlink');continue
        f=root.joinpath(*p.parts)
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=item.get('sha256'):reasons.append(name+': missing/tampered bytes')
    return dict(local_precheck='blocked' if reasons else 'ready_for_host_review',production_allowed=False,reasons=reasons,note='Integrity only. Host signature/provenance/semantic review and K8 remain authoritative.')
