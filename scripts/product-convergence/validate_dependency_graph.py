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
 d=load(sys.argv[1]); nodes={n['id'] for n in d['nodes']}; graph={n:set() for n in nodes}
 for e in d['edges']:
  assert e['consumer'] in nodes and e['provider'] in nodes
  graph[e['consumer']].add(e['provider'])
 visiting=set(); visited=set()
 def dfs(n):
  if n in visiting: raise AssertionError('dependency cycle')
  if n in visited: return
  visiting.add(n)
  for x in graph[n]: dfs(x)
  visiting.remove(n); visited.add(n)
 for n in nodes: dfs(n)
 print(f'dependency graph ok: {len(nodes)} nodes')
if __name__=='__main__': main()
