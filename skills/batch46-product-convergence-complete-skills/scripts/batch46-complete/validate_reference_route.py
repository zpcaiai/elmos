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

REQUIRED={"repository-intake","semantic-model","psp-uir","framework-contract","code-generation","build","test-migration","repair","behavior-verification","database-migration","pull-request","private-runner","canary","cutover","hypercare","customer-handoff"}
def validate(path,require_pass=False):
 d=load(path); stages={x["stage"]:x for x in d.get("stage_results",[])}
 if not REQUIRED<=set(d.get("required_stages",[])) or not REQUIRED<=set(stages): fail("incomplete reference route")
 if require_pass and any(stages[s]["status"]!="passed" or not stages[s].get("evidence") for s in REQUIRED): fail("reference route not passed")
 return d
def main():validate(sys.argv[1],"--require-pass" in sys.argv);print("route ok")
if __name__=="__main__":main()
