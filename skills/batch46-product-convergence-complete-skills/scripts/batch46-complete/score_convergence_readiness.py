from __future__ import annotations
from pathlib import Path
import json, hashlib, re, sys
PLACEHOLDERS={"tbd","unknown","none","team","owner","placeholder","todo","n/a","na"}
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def save(path,obj): Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
def valid_digest(v): return isinstance(v,str) and bool(re.fullmatch(r"[a-f0-9]{64}",v)) and len(set(v))>1
def non_placeholder(v): return isinstance(v,str) and len(v.strip())>=3 and v.strip().lower() not in PLACEHOLDERS
def fail(msg): raise AssertionError(msg)

def main():
 p=Path(sys.argv[1]); c=load(p/"certification.json"); checks={}
 checks["single_kernel"]=all(c["kernel"].values())
 checks["route"]=c["reference_route"].get("certified") is True
 checks["runner"]=c["private_runner"].get("certified") is True
 checks["partners"]=c["design_partners"].get("accepted_count",0)>=2
 checks["handoff"]=c["handoff"].get("passed") is True
 checks["workloads"]=len(c.get("verified_workloads",[]))>=2
 checks["delivery"]=c["delivery_model"].get("passed") is True
 checks["sla"]=c["sla_proof"].get("passed") is True
 score=sum(checks.values())/len(checks)
 print(json.dumps({"score":score,"checks":checks},indent=2))
if __name__=="__main__":main()
