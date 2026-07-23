
#!/usr/bin/env bash
set -euo pipefail
target=${1:?usage: ./install.sh /path/to/repository}
mkdir -p "$target"
cp -R .agents schemas templates scripts tests docs product-convergence "$target/"
cp AGENTS.md.snippet Makefile.product-convergence "$target/"
echo "Installed 32 ELMOS product-convergence skills."
