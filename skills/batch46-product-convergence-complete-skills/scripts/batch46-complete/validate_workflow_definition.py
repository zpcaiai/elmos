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
 d=load(path); ids=[x["id"] for x in d["steps"]]
 if len(ids)!=len(set(ids)): fail("duplicate step")
 known=set(ids); adj={i:[] for i in ids}
 for s in d["steps"]:
  if not s.get("idempotency"): fail("missing idempotency")
  for dep in s["dependencies"]:
   if dep not in known: fail("unknown workflow dependency")
   adj[s["id"]].append(dep)
 visiting=set(); done=set()
 def dfs(n):
  if n in visiting: fail("workflow cycle")
  if n in done:return
  visiting.add(n)
  for m in adj[n]:dfs(m)
  visiting.remove(n);done.add(n)
 for n in ids:dfs(n)
 return d
def main(): validate(sys.argv[1]); print("workflow ok")
if __name__=="__main__":main()
