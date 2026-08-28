#!/usr/bin/env bash
set -euo pipefail
target=${1:?usage: ./install.sh /path/to/repository}
mkdir -p "$target"
cp -R .agents docs schemas templates scripts tests convergence-packs "$target/"
cp AGENTS.md.snippet Makefile.batch46-complete "$target/"
echo "Installed Batch 46 Complete: 40 skills."
