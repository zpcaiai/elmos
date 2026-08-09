#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

def load(path): return json.loads(Path(path).read_text())
def write(path,obj): Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(obj,indent=2)+"\n")
def real_files(path):
 p=Path(path)
 return [x for x in p.rglob('*') if x.is_file() and x.name not in {'.gitkeep'} and x.stat().st_size>0]
def safe_ref(ref):
 if not isinstance(ref,str) or not ref or ref.startswith('/') or '..' in Path(ref).parts: return False
 return True
def resolve_ref(pack,ref):
 if not safe_ref(ref): return False
 p=(Path(pack)/ref).resolve(); root=Path(pack).resolve()
 try: p.relative_to(root)
 except ValueError: return False
 return p.is_file() and p.stat().st_size>0
