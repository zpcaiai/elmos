#!/usr/bin/env bash
# Regenerate routes/inventory.json for the thirteen-language matrix.
#
# This is the ONE step of the matrix change that could not be done from the
# cloud session: run_polyglot_routes.py validates the pinned macOS toolchain at
# import time (EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE off-Mac), so the inventory
# has to be written on this machine.
#
# Until it runs, exactly one test is red:
#   test_language_set.py::test_inventory_declares_the_complete_156_with_preserved_provenance_sets
# That red means "inventory is stale", not "the matrix is wrong".
set -euo pipefail

cd "$(dirname "$0")"
REPO="$(pwd)"
echo "repo: $REPO"

# 1. Regenerate the inventory through the repo's own authority code.
uv --directory engines/polyglot-route-engine sync --locked
uv --directory engines/polyglot-route-engine run --locked \
  python "$REPO/scripts/batch29/run_polyglot_routes.py" \
  --repo-root "$REPO" --inventory-only

# 2. Confirm the shape.
python3 - <<'PY'
import json, pathlib
inv = json.loads(pathlib.Path("routes/inventory.json").read_text())
print("route_count            :", inv["route_count"])
print("languages              :", len(inv["languages"]))
print("deprecated_languages   :", inv["deprecated_languages"])
print("pending_analyzer       :", inv["pending_analyzer_languages"])
print("cartesian_expansion    :", inv["route_policy"]["cartesian_expansion"])
print("route_sets             :", sorted(inv["route_sets"]))
for name in ("legacy-complete-30", "cpp-objc-swift-java-exact-8",
             "nine-language-completion-34", "javascript-node26-completion-18",
             "php-php85-completion-20", "kotlin-react-flutter-completion-66",
             "nine-language-complete-72", "ten-language-complete-90",
             "eleven-language-complete-110", "thirteen-language-complete-156"):
    print(f"  {name:38s} {len(inv['route_sets'][name]['route_keys'])}")
assert inv["route_count"] == 156, inv["route_count"]
assert len(inv["route_sets"]["eleven-language-complete-110"]["route_keys"]) == 110
assert len(inv["route_sets"]["javascript-node26-completion-18"]["route_keys"]) == 18
assert len(inv["route_sets"]["php-php85-completion-20"]["route_keys"]) == 20
assert len(inv["route_sets"]["cpp-objc-swift-java-exact-8"]["route_keys"]) == 8
assert len(inv["route_sets"]["kotlin-react-flutter-completion-66"]["route_keys"]) == 66
print("OK: frozen provenance sets kept their recorded sizes")
PY

# 3. Re-run the engine tests the way CI does.
uv --directory engines/polyglot-route-engine run --locked pytest tests/test_language_set.py -q
uv --directory engines/polyglot-route-engine run --locked ruff check src tests
uv --directory engines/polyglot-route-engine run --locked mypy src

echo
echo "Done.  Nothing here touches git -- review and commit yourself."
echo "Scratch tarballs the session left behind (gitignored, safe to delete):"
echo "  rm -rf $REPO/.ai-tmp/*.tgz"
