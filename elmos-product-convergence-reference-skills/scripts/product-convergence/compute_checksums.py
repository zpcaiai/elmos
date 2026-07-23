
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
for p in sorted(root.rglob('*')):
 if p.is_file() and p!=out:
  rows.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}")
out.write_text('\n'.join(rows)+'\n'); print(len(rows))
