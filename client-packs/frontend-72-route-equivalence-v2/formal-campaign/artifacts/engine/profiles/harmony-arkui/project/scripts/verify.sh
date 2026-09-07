#!/usr/bin/env bash
set -euo pipefail
test "${ELMOS_HARMONYOS_RUNNER_PROFILE:-}" = "harmonyos-6.0.0-api20"
test -x "./hvigorw" || { echo "HARMONY_HVIGOR_WRAPPER_NOT_MATERIALIZED"; exit 2; }
./hvigorw clean --no-daemon
./hvigorw assembleHap --mode module -p module=entry@default -p buildMode=debug --no-daemon
