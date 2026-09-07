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

def validate(path):
 d=load(path); types={x["type"] for x in d.get("corpora",[])}
 required={"synthetic","open-source-representative","internal-holdout","customer-private"}
 if not required<=types: fail("missing corpus class")
 for c in d["corpora"]:
  if not valid_digest(c["digest"]): fail("invalid corpus digest")
 rules=" ".join(d.get("contamination_rules",[])).lower()
 if "holdout" not in rules or "golden" not in rules: fail("missing contamination controls")
 return d
def main():validate(sys.argv[1]);print("corpus ok")
if __name__=="__main__":main()
