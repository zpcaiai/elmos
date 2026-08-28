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
 d=load(path); ids={n["id"] for n in d["nodes"]}; adj={i:[] for i in ids}
 for e in d["edges"]:
  if e["consumer"] not in ids or e["provider"] not in ids: fail("unknown dependency node")
  adj[e["consumer"]].append(e["provider"])
 visiting=set(); done=set()
 def dfs(n):
  if n in visiting: fail("dependency cycle")
  if n in done: return
  visiting.add(n)
  for m in adj[n]: dfs(m)
  visiting.remove(n); done.add(n)
 for n in ids: dfs(n)
 return d
def main(): validate(sys.argv[1]); print("dependency graph ok")
if __name__=="__main__": main()
