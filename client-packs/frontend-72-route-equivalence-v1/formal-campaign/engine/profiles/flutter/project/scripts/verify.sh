#!/usr/bin/env bash
set -euo pipefail
flutter --version | grep -F "Flutter 3.44.1"
flutter pub get
flutter analyze
flutter test
