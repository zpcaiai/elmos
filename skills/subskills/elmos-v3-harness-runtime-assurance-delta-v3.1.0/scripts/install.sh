#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="${1:?usage: install.sh /path/to/elmos-or-v3-package-root [--dry-run]}"
MODE="${2:-}"

resolve_base() {
  if [[ -f "$INPUT/PACKAGE_MANIFEST.yaml" ]]; then printf '%s\n' "$INPUT"; return; fi
  if [[ -f "$INPUT/packages/elmos-v3/PACKAGE_MANIFEST.yaml" ]]; then printf '%s\n' "$INPUT/packages/elmos-v3"; return; fi
  echo "Cannot locate Elmos v3 PACKAGE_MANIFEST.yaml under $INPUT" >&2; exit 2
}
BASE="$(resolve_base)"
python3 "$SOURCE_DIR/scripts/validate_delta.py" >/dev/null

python3 - "$BASE" "$SOURCE_DIR" "$MODE" <<'PY'
from __future__ import annotations
import hashlib, json, shutil, sys, time
from pathlib import Path
import yaml

base=Path(sys.argv[1]).resolve(); src=Path(sys.argv[2]).resolve(); mode=sys.argv[3]
manifest_path=base/'PACKAGE_MANIFEST.yaml'
manifest=yaml.safe_load(manifest_path.read_text())
name=manifest.get('metadata',{}).get('name'); version=str(manifest.get('metadata',{}).get('version'))
expected='elmos-proof-driven-agentic-harness-repository-semantic-compiler'
package_id='elmos-v3-harness-runtime-assurance-delta-v3.1.0'
record_path=base/'applied-deltas'/package_id/'install-record.json'
if name != expected: raise SystemExit(f'wrong base package: {name}')
if record_path.exists():
    print(f'{package_id} already installed; no changes')
    raise SystemExit(0)
if version != '3.0.0': raise SystemExit(f'exact base 3.0.0 required, found {version}')
if mode == '--dry-run':
    print(f'dry-run PASS: compatible base at {base}')
    raise SystemExit(0)

payload=src/'payload'; hashes=json.loads((src/'PAYLOAD_HASHES.json').read_text())
backup_root=base/'.elmos-delta-backups'/package_id/str(int(time.time_ns()))
backup_root.mkdir(parents=True)
installed=[]; overwritten=[]
for rel, expected_hash in sorted(hashes.items()):
    source=payload/rel; target=base/rel
    actual=hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != expected_hash: raise SystemExit(f'payload hash mismatch: {rel}')
    if target.exists():
        b=backup_root/'overwritten'/rel; b.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,b); overwritten.append(rel)
    target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target); installed.append(rel)

# Backup and update base metadata files.
for rel in ['PACKAGE_MANIFEST.yaml','PACKAGE_MANIFEST.json','VERSION','FILES.sha256']:
    p=base/rel
    if p.exists():
        b=backup_root/'metadata'/rel; b.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,b)

manifest['metadata']['version']='3.1.0'
manifest['metadata']['packageId']=expected+'-v3.1.0'
spec=manifest.setdefault('spec',{})
counts=spec.setdefault('counts',{})
counts['kernelExtensions']=13
counts['deltaJsonSchemas']=15
applied=spec.setdefault('appliedDeltas',[])
applied.append({'packageId':package_id,'version':'3.1.0','installedAt':'generated-install-time','routableSkillsAdded':0,'kernelExtensions':13})
manifest_path.write_text(yaml.safe_dump(manifest,allow_unicode=True,sort_keys=False,width=120))
(base/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(base/'VERSION').write_text('3.1.0\n')

record_path.parent.mkdir(parents=True,exist_ok=True)
record={'packageId':package_id,'baseVersion':'3.0.0','compositeVersion':'3.1.0','backupRoot':str(backup_root.relative_to(base)),'installed':installed,'overwritten':overwritten,'installedHashes':hashes}
record_path.write_text(json.dumps(record,indent=2)+'\n')

# Regenerate base checksum manifest after every mutation.
import subprocess
subprocess.run([sys.executable, str(base/'scripts/generate_checksums.py')], cwd=base, check=True)
print(f'installed {package_id} into {base}')
PY

# Combined validation.
(
  cd "$BASE"
  python3 scripts/validate_package.py >/dev/null
  python3 scripts/generate_registry.py --check >/dev/null
  python3 scripts/verify_migration_coverage.py >/dev/null
  python3 scripts/generate_checksums.py --check >/dev/null
  PYTHONPATH=reference-implementation/src \
    python3 -m unittest discover -s reference-implementation/tests -v >/dev/null
)

echo "Elmos composite v3.1.0 validation PASS"
