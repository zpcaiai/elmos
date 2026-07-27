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

def validate(profile_path,result_path=None):
 p=load(profile_path); th=p["thresholds"]
 if th["min_idiomaticity"]<0.9 or th["max_compatibility_runtime_ratio"]>0.1: fail("weak maintainability thresholds")
 if result_path:
  r=load(result_path)
  checks=[r["complexity_regression"]<=th["max_complexity_regression"],r["duplication"]<=th["max_duplication"],r["idiomaticity"]>=th["min_idiomaticity"],r["compatibility_runtime_ratio"]<=th["max_compatibility_runtime_ratio"],r["testability"]>=th["min_testability"],r["documentation_coverage"]>=th["min_documentation_coverage"],r["ownership_coverage"]>=th["min_ownership_coverage"]]
  if not all(checks): fail("maintainability gate failed")
 return p
def main():validate(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None);print("maintainability ok")
if __name__=="__main__":main()
