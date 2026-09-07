#!/usr/bin/env python3
from __future__ import annotations
import json, hashlib, re
from pathlib import Path
HEX64=re.compile(r'^sha256:[0-9a-f]{64}$')
def load(p): return json.loads(Path(p).read_text())
def dump(p,obj): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(obj,indent=2)+'\n')
def valid_digest(v): return isinstance(v,str) and bool(HEX64.match(v)) and v != 'sha256:'+'0'*64
def real_files(p):
 p=Path(p)
 return [x for x in p.rglob('*') if x.is_file() and x.name not in {'.gitkeep'} and x.stat().st_size>0] if p.exists() else []
def inside(base, rel):
 try: (Path(base)/rel).resolve().relative_to(Path(base).resolve()); return True
 except Exception: return False
def resolve_evidence(base,ref):
 if not isinstance(ref,dict): return False,'evidence ref must be object'
 rel=ref.get('path'); digest=ref.get('sha256'); art=ref.get('artifact_digest'); env=ref.get('environment_digest')
 if not rel or not inside(base,rel): return False,'invalid evidence path'
 p=(Path(base)/rel).resolve()
 if not p.is_file(): return False,'evidence file missing'
 actual='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
 if digest!=actual: return False,'evidence digest mismatch'
 if not valid_digest(art) or not valid_digest(env): return False,'evidence binding digest invalid'
 return True,''
