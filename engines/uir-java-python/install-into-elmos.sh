#!/usr/bin/env bash
# Install this engine into the elmos repository and wire it into the build.
#
# Idempotent: safe to re-run.  It refuses rather than guesses if the repository
# does not look like the tree it expects.
#
#   ./install-into-elmos.sh /path/to/elmos
set -euo pipefail

REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "usage: $0 /path/to/elmos" >&2
  exit 2
fi
REPO="$(cd "$REPO" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for required in Makefile engines scripts/modernization_b01_44/audit_repo.py \
                skills/repository-migration-platform-skills-batch1-38; do
  if [[ ! -e "$REPO/$required" ]]; then
    echo "not an elmos checkout: missing $required" >&2
    exit 2
  fi
done

# ---------------------------------------------------------------------------
# 1. the engine itself
# ---------------------------------------------------------------------------
DEST="$REPO/engines/uir-java-python"
mkdir -p "$DEST"
for item in j2p runtime corpus tests tools docs README.md requirements.txt; do
  rm -rf "${DEST:?}/$item"
  cp -R "$HERE/$item" "$DEST/$item"
done
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo "installed engine -> engines/uir-java-python"

# ---------------------------------------------------------------------------
# 2. audit_repo.py: the glob bug that misreports two series as spec-only
# ---------------------------------------------------------------------------
python3 - "$REPO" <<'PY'
import pathlib
import sys

repo = pathlib.Path(sys.argv[1])
path = repo / "scripts/modernization_b01_44/audit_repo.py"
text = path.read_text(encoding="utf-8")

# The batch1-38 series was configured with an empty implementation tuple and no
# test directory, so the audit could not see scripts/migration_platform.py and
# reported the series as "spec-only, 0 lines" even though it ships a runtime and
# 18 passing tests.  The report was wrong about the tree, not about the design.
old = '''    "repository-migration-platform-b1-38": (
        ("skills/repository-migration-platform-skills-batch1-38/**/SKILL.md",),
        (),
        None,
    ),'''
new = '''    "repository-migration-platform-b1-38": (
        ("skills/repository-migration-platform-skills-batch1-38/**/SKILL.md",),
        ("skills/repository-migration-platform-skills-batch1-38/scripts",),
        "skills/repository-migration-platform-skills-batch1-38/tests",
    ),
    "uir-java-python": (
        ("engines/uir-java-python/**/*.md",),
        ("engines/uir-java-python/j2p", "engines/uir-java-python/runtime"),
        "engines/uir-java-python/tests",
    ),'''

if new.split("\n", 1)[0] in text and "uir-java-python" in text:
    print("audit_repo.py already patched")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched audit_repo.py: batch1-38 implementation globs + new series")
else:
    print(
        "WARNING: audit_repo.py does not contain the expected block; "
        "left unchanged so nothing is corrupted",
        file=sys.stderr,
    )
PY

# ---------------------------------------------------------------------------
# 3. Makefile targets
# ---------------------------------------------------------------------------
python3 - "$REPO" <<'PY'
import pathlib
import sys

repo = pathlib.Path(sys.argv[1])
path = repo / "Makefile"
text = path.read_text(encoding="utf-8")
if "uir-j2p-test:" in text:
    print("Makefile already has uir-j2p targets")
    raise SystemExit(0)

block = """

# --- java->python UIR route -------------------------------------------------
# TREE, WORKSPACE and SOURCE are overridable:
#   make uir-j2p-survey TREE=engines/enterprise-suite-engine/src
UIR_J2P_DIR := engines/uir-java-python
TREE ?= .
WORKSPACE ?= /tmp/uir-j2p-workspace
SOURCE ?= $(CURDIR)/engines/uir-java-python

uir-j2p-deps:
\\tpython3 -m pip install -r $(UIR_J2P_DIR)/requirements.txt

uir-j2p-test:
\\tcd $(UIR_J2P_DIR) && python3 -m unittest discover -s tests -v

uir-j2p-mutation:
\\tcd $(UIR_J2P_DIR) && python3 tools/mutation_check.py --json-out docs/mutation-report.json

uir-j2p-survey:
\\tcd $(UIR_J2P_DIR) && python3 -m j2p.cli survey $(CURDIR)/$(TREE) --out docs/survey-latest.json

# The control measurement: the same survey with whole-program resolution turned
# off. A claim that cross-file resolution moved the number is only worth
# something if the unimproved number can still be reproduced on demand.
uir-j2p-survey-noindex:
\\tcd $(UIR_J2P_DIR) && python3 -m j2p.cli survey $(CURDIR)/$(TREE) --no-index --out docs/survey-noindex.json

uir-j2p-evidence:
\\tcd $(UIR_J2P_DIR) && python3 tools/record_batch_evidence.py \\\\
\\t  --runtime $(CURDIR)/skills/repository-migration-platform-skills-batch1-38/scripts/migration_platform.py \\\\
\\t  --workspace $(WORKSPACE) --source $(SOURCE) --survey-tree $(CURDIR)/$(TREE)

# The gate is test + mutation together: a green suite that no mutation can turn
# red is not evidence of anything.
uir-j2p-gate: uir-j2p-test uir-j2p-mutation

.PHONY: uir-j2p-deps uir-j2p-test uir-j2p-mutation uir-j2p-survey uir-j2p-survey-noindex uir-j2p-evidence uir-j2p-gate
"""

path.write_text(text + block.replace("\\t", "\t"), encoding="utf-8")
print("appended uir-j2p targets to Makefile")
PY

echo
echo "next:"
echo "  cd $REPO"
echo "  make uir-j2p-deps"
echo "  make uir-j2p-gate      # 119 tests + 32 mutations"
echo "  make uir-j2p-survey TREE=engines"
