from pathlib import Path
import json, hashlib, re, sys
HEX=set("0123456789abcdef")
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def valid_digest(s): return isinstance(s,str) and len(s)==64 and set(s)<=HEX and len(set(s))>1
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()

def main():
 d=load(sys.argv[1]); skills=d['skills']; ids=[x['skill_id'] for x in skills]; names=[x['name'] for x in skills]
 assert len(ids)==len(set(ids)) and len(names)==len(set(names))
 known=set(ids)
 for s in skills:
  assert s['layer'] in {'meta','orchestrator','implementation','test','operations'}
  for dep in s.get('prerequisites',[]): assert dep in known
 print(f'skill registry ok: {len(skills)}')
if __name__=='__main__': main()
