#!/usr/bin/env python3
from __future__ import annotations
import json
import re
from pathlib import Path

SHA256_PATTERN = re.compile(r'^sha256:[0-9a-f]{64}$')
REAL_EXECUTION_KINDS = {'approved-sandbox', 'external-lab', 'field', 'customer-approved'}

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

def validate_attested_corpus(pack, relative, failures, *, independent=True):
 """Require a digest-bound corpus manifest before a certification claim.

 Plain files are deliberately insufficient: the manifest binds the dataset and
 source, records independent execution, and resolves authorization/evidence
 references inside the immutable pack boundary.
 """
 manifest_path=Path(pack)/relative/'manifest.json'
 if not manifest_path.is_file():
  failures.append(f'{relative}/manifest.json missing')
  return
 try: manifest=load(manifest_path)
 except Exception as exc:
  failures.append(f'{relative}/manifest.json invalid: {exc}')
  return
 if str(manifest.get('status','')).lower()!='passed': failures.append(f'{relative} status must be passed')
 for key in ('source_digest','dataset_digest'):
  if not SHA256_PATTERN.fullmatch(str(manifest.get(key,''))): failures.append(f'{relative} {key} must be sha256:<64 lowercase hex>')
 if independent and manifest.get('independent') is not True: failures.append(f'{relative} must be independently executed')
 if manifest.get('execution_kind') not in REAL_EXECUTION_KINDS: failures.append(f'{relative} execution_kind is not real or approved')
 for key in ('authorization_refs','evidence_refs'):
  refs=manifest.get(key,[])
  if not isinstance(refs,list) or not refs: failures.append(f'{relative} {key} empty')
  else:
   for ref in refs:
    if not resolve_ref(pack,ref): failures.append(f'{relative} missing {key[:-1]}: {ref}')
