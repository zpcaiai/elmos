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
 d=load(sys.argv[1]); caps=d['capabilities']; ids=[]
 for c in caps:
  ids.append(c['capability_id'])
  assert c['owner'] and c['version']
  if c['status']=='certified': assert c.get('evidence'), c['capability_id']
 assert len(ids)==len(set(ids))
 print(f'capability registry ok: {len(caps)}')
if __name__=='__main__': main()
