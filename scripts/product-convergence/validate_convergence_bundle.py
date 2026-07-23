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
 root=Path(sys.argv[1]); required=['convergence-plan.json','capability-registry.json','dependency-graph.json','project-lifecycle.json','workflow-definition.json','evidence-graph.json','skill-registry.json','benchmark-corpus.json','reference-route-plan.json','handoff-package.json','readiness-gate.json']
 for n in required: assert (root/n).is_file(), n
 subprocess=__import__('subprocess')
 base=Path(__file__).parent
 subprocess.run([sys.executable,str(base/'validate_dependency_graph.py'),str(root/'dependency-graph.json')],check=True)
 subprocess.run([sys.executable,str(base/'validate_skill_registry.py'),str(root/'skill-registry.json')],check=True)
 subprocess.run([sys.executable,str(base/'validate_capability_registry.py'),str(root/'capability-registry.json')],check=True)
 subprocess.run([sys.executable,str(base/'validate_evidence_graph.py'),str(root/'evidence-graph.json')],check=True)
 subprocess.run([sys.executable,str(base/'validate_reference_route.py'),str(root/'reference-route-plan.json')],check=True)
 print('convergence bundle ok')
if __name__=='__main__': main()
