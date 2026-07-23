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
 d=load(sys.argv[1]); nodes={n['id']:n for n in d['nodes']}
 for n in nodes.values(): assert valid_digest(n['digest']) and n['tenant_id'] and n['producer']
 for e in d['edges']:
  assert e['from'] in nodes and e['to'] in nodes
  assert nodes[e['from']]['tenant_id']==nodes[e['to']]['tenant_id'], 'cross-tenant evidence edge'
 print(f'evidence graph ok: {len(nodes)} nodes')
if __name__=='__main__': main()
