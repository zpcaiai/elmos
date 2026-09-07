#!/usr/bin/env python3
"""Developer checksum generation. NOT a signature. Retest before resealing changes."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    rows=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_symlink():raise SystemExit('symlink refused')
        if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc') and p.name not in ['FILES.sha256','.installation-receipt.json']:rows.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix())
    (ROOT/'FILES.sha256').write_text('\n'.join(rows)+'\n');print('SEALED',len(rows),'files; integrity only')
