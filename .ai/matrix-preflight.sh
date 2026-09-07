#!/bin/sh
# Preflight for the full-matrix run. Exits 0 only when EVERY gate passes.
# Decision of record (2026-08-18): wait for PHP module inventory; run the FULL
# matrix, not a 202-node subset. Do not launch while any gate below is red.
set -u
E=/Users/stephen/DevProjects/AIProjects/elmos/engines/polyglot-route-engine
cd "$E" || exit 2
TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)"; export TMPDIR
fail=0
say() { printf '%-34s %s\n' "$1" "$2"; }

# 1. PHP module inventory landed?
out=$(.venv/bin/python3 -m pytest \
  "tests/test_repository_pipeline_language_matrix.py::test_repository_pipeline_converts_three_file_repository_for_every_directed_pair[php-java]" \
  -p no:cacheprovider -o addopts= -o tmp_path_retention_policy=failed -q --tb=no 2>&1 | tail -1)
case "$out" in
  *"1 passed"*) say "php-as-source (php-java)" "PASS  -- module inventory has landed" ;;
  *)            say "php-as-source (php-java)" "BLOCKED -- $out"; fail=1 ;;
esac

# 2. Disk headroom. 182 nodes consumed ~22 GB net; 222 needs more. 10 GB is the hard stop.
free_gib=$(df -k /System/Volumes/Data | tail -1 | awk '{printf "%d", $4/1048576}')
if [ "$free_gib" -ge 32 ]; then say "disk headroom" "PASS  -- ${free_gib} GiB free"
else say "disk headroom" "BLOCKED -- ${free_gib} GiB free, want >= 32"; fail=1; fi

# 3. Exclusive machine.
busy=$(ps -Ao command | grep -c '[p]ytest\|[u]v --directory')
if [ "$busy" -eq 0 ]; then say "exclusive window" "PASS  -- no other pytest/uv run"
else say "exclusive window" "BLOCKED -- $busy competing process(es)"; fail=1; fi

# 4. Node toolchain pin (the sqlite 3.53.3 restoration must still hold).
.venv/bin/python3 - <<'PY' >/tmp/_pin.out 2>&1
from elmos_polyglot_route import toolchains as T
T._verify_node_topology_identity(T._discover_node_topology()); print("OK")
PY
if grep -q OK /tmp/_pin.out; then say "node topology pin" "PASS"
else say "node topology pin" "BLOCKED -- $(tail -1 /tmp/_pin.out)"; fail=1; fi
say "  opt/sqlite ->" "$(readlink /opt/homebrew/opt/sqlite)"

# 5. Static gates.
if .venv/bin/ruff check . >/dev/null 2>&1; then say "ruff" "PASS"; else say "ruff" "BLOCKED"; fail=1; fi
if .venv/bin/mypy --strict src/elmos_polyglot_route 2>&1 | grep -q '^Success'; then say "mypy --strict" "PASS"
else say "mypy --strict" "BLOCKED"; fail=1; fi

# 6. Suite shape (report, never assert a fixed number -- it changes with languages).
n=$(.venv/bin/python3 -m pytest tests/test_repository_pipeline_language_matrix.py \
      -p no:cacheprovider -o addopts= -q --collect-only 2>/dev/null | tail -1 | awk '{print $1}')
say "collected nodes" "$n"

echo
[ "$fail" -eq 0 ] && echo "PREFLIGHT: GO" || echo "PREFLIGHT: NO-GO"
exit "$fail"
