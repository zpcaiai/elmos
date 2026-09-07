#!/usr/bin/env bash
set -euo pipefail
force=0
if [[ ${1:-} == --force ]]; then force=1; shift; fi
[[ $# -eq 1 ]] || { echo "usage: $0 [--force] /path/to/elmos" >&2; exit 2; }
target=$(cd "$1" && pwd); root=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$target/agent-skills/runtime"
for src in "$root"/agent-skills/runtime/*; do n=$(basename "$src"); d="$target/agent-skills/runtime/$n"; if [[ -e "$d" && $force -ne 1 ]]; then echo "collision: $d" >&2; exit 3; fi; done
for src in "$root"/agent-skills/runtime/*; do n=$(basename "$src"); d="$target/agent-skills/runtime/$n"; rm -rf "$d"; cp -R "$src" "$d"; done
rm -rf "$target/elmos-polyglot"; mkdir -p "$target/elmos-polyglot"
for x in manifest.json technology-registry.json technology-registry.yaml repository-surface-registry.json repository-surface-registry.yaml route-registry.json route-registry.yaml route-matrix.csv p0-mutual-route-matrix.csv route-certification-registry.json schemas policies templates examples docs references certification-corpus native-runtime-lab; do [[ -e "$root/$x" ]] && cp -R "$root/$x" "$target/elmos-polyglot/"; done
python3 - "$target" "$root" <<'PYI'
import json,pathlib,sys,hashlib
T=pathlib.Path(sys.argv[1]); R=pathlib.Path(sys.argv[2]); m=json.loads((R/'manifest.json').read_text()); rec={'package':'elmos-polyglot-skills','version':m['package']['version'],'skills':[x['name'] for x in m['skills']]}; (T/'elmos-polyglot'/'install-receipt.json').write_text(json.dumps(rec,indent=2)+'\n')
PYI
count=$(find "$root/agent-skills/runtime" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
echo "installed $count Skills into $target"
