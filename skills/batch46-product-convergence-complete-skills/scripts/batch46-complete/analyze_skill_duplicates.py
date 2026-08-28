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

def tokenize(s): return set(re.findall(r"[a-z0-9]+",s.lower()))
def main():
 d=load(sys.argv[1]); skills=d.get("skills",[]); out=[]
 for i,a in enumerate(skills):
  ta=tokenize(a["name"]+" "+" ".join(a.get("outputs",[])))
  for b in skills[i+1:]:
   tb=tokenize(b["name"]+" "+" ".join(b.get("outputs",[])))
   score=len(ta&tb)/max(1,len(ta|tb))
   if score>=0.6: out.append({"a":a["name"],"b":b["name"],"score":round(score,3)})
 print(json.dumps({"possible_duplicates":out},indent=2))
if __name__=="__main__":main()
