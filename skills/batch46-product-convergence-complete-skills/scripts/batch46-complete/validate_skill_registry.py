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
 d=load(path); ids=set(); names=set(); triggers={}
 for s in d.get("skills",[]):
  if s["skill_id"] in ids or s["name"] in names: fail("duplicate skill")
  ids.add(s["skill_id"]); names.add(s["name"])
  if not non_placeholder(s.get("owner")): fail("invalid skill owner")
  for t in s.get("triggers",[]): triggers.setdefault(t,[]).append(s["name"])
 conflicts={k:v for k,v in triggers.items() if len(v)>1}
 if conflicts: fail("trigger conflict: "+str(conflicts))
 return d
def main():validate(sys.argv[1]);print("skill registry ok")
if __name__=="__main__":main()
