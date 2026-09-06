"""Check evidence binding, not the semantic truth of a natural-language claim."""
def validate_claim(claim: dict, anchors: dict, events: dict) -> None:
    binding = (claim["tenant_id"],claim["repository_id"],claim["snapshot_id"])
    for key in claim["source_anchor_ids"]:
        a = anchors.get(key)
        if not a or (a["tenant_id"],a["repository_id"],a["snapshot_id"]) != binding:
            raise ValueError("source binding mismatch")
    for key in claim["runtime_event_ids"]:
        e = events.get(key)
        if not e or (e["tenant_id"],e["repository_id"],e["snapshot_id"]) != binding or e["commit_status"] != "committed":
            raise ValueError("runtime evidence not committed for this revision")
    if claim["classification"] == "verified-static" and not claim["source_anchor_ids"]:
        raise ValueError("static claim without evidence")
    if claim["classification"] == "runtime-observed" and not claim["runtime_event_ids"]:
        raise ValueError("runtime claim without evidence")

def validate_correspondence(m: dict) -> None:
    s,t=len(m["source_anchor_ids"]),len(m["target_anchor_ids"])
    valid={"one-to-one":s==1 and t==1,"one-to-many":s==1 and t>1,"many-to-one":s>1 and t==1,"many-to-many":s>1 and t>1,"deleted":s>0 and t==0,"synthesized":s==0 and t>0,"unmapped":s+t>0}
    if not valid.get(m["relation"],False):raise ValueError("mapping cardinality mismatch")
    if m["confidence"]=="observed-scenario" and not m["evidence_ids"]:raise ValueError("observed mapping without evidence")

def validate_session(s: dict) -> None:
    ready,expiry=s["first_ready_at"],s["expires_at"]
    if (ready is None)!=(expiry is None):raise ValueError("partial time binding")
    if ready is not None and (expiry!=ready+600 or ready<s["created_at"] or s["provider_hard_deadline"]<expiry+30):raise ValueError("invalid fixed deadline")
    if s["state"]=="ready" and ready is None:raise ValueError("ready without time")
