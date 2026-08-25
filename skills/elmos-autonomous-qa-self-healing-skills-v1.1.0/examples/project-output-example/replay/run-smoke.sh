#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../project"
npm ci
npm run test:smoke
