#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 ]] || { echo "usage: $0 /path/to/elmos" >&2; exit 2; }
target=$(cd "$1" && pwd); root=$(cd "$(dirname "$0")" && pwd); [[ -d "$target/agent-skills/runtime" ]] || { echo "missing base agent-skills/runtime" >&2; exit 3; }
for src in "$root"/agent-skills/runtime/*; do n=$(basename "$src"); [[ ! -e "$target/agent-skills/runtime/$n" ]] || { echo "collision: $n" >&2; exit 4; }; done
for src in "$root"/agent-skills/runtime/*; do cp -R "$src" "$target/agent-skills/runtime/"; done
mkdir -p "$target/elmos-semantic-assurance"; for x in manifest.json route-certification-registry.json schemas policies templates references certification-corpus native-runtime-lab; do [[ -e "$root/$x" ]] && cp -R "$root/$x" "$target/elmos-semantic-assurance/"; done
python3 - "$target" "$root" <<'PYI'
import json,pathlib,sys
T=pathlib.Path(sys.argv[1]); R=pathlib.Path(sys.argv[2]); m=json.loads((R/'manifest.json').read_text()); (T/'elmos-semantic-assurance'/'install-receipt.json').write_text(json.dumps({'package':'elmos-semantic-assurance-expansion-skills','version':'1.0.0','skills':[x['name'] for x in m['skills']]},indent=2)+'\n')
PYI
echo "installed 132 semantic assurance Skills"
