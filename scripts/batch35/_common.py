from __future__ import annotations
import json
from pathlib import Path
def load(path): return json.loads(Path(path).read_text())
def write(path,obj): Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(obj,indent=2)+"\n")
def real_files(path):
 p=Path(path)
 return [x for x in p.rglob("*") if x.is_file() and x.name not in {".gitkeep","README.md"} and x.stat().st_size>0]
def resolve_ref(pack,ref): return ref.startswith(("http://","https://")) or (Path(pack)/ref).is_file()
