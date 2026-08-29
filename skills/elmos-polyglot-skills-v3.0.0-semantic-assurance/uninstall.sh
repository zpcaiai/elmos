#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 ]] || { echo "usage: $0 /path/to/elmos" >&2; exit 2; }
target=$(cd "$1" && pwd); rec="$target/elmos-polyglot/install-receipt.json"; [[ -f "$rec" ]] || { echo "missing receipt" >&2; exit 3; }
python3 - "$target" "$rec" <<'PYI'
import json,pathlib,shutil,sys
T=pathlib.Path(sys.argv[1]); r=json.loads(pathlib.Path(sys.argv[2]).read_text());
for n in r['skills']: shutil.rmtree(T/'agent-skills/runtime'/n,ignore_errors=True)
shutil.rmtree(T/'elmos-polyglot',ignore_errors=True)
PYI
echo "uninstalled ELMOS polyglot package"
