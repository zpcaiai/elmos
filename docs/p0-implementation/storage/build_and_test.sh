#!/usr/bin/env bash
# Build and verify the dependency-free storage core.
#
# The two Spring adapters under spring/ are NOT built here: they need Spring on
# the classpath and belong in modules/persistence and apps/control-plane. They
# are delivered as source for that move.
set -euo pipefail

cd "$(dirname "$0")"
rm -rf target
mkdir -p target/classes target/test-classes

echo "==> compiling storage core"
javac -Xlint:all -Werror -d target/classes $(find src/main/java -name '*.java')

echo "==> compiling tests"
javac -d target/test-classes -cp target/classes $(find src/test/java -name '*.java')

echo "==> SigV4 presigner, pinned to the published AWS vector"
java -cp target/classes:target/test-classes io.elmos.storage.SigV4PresignerTest

echo "==> S3 object store against a live fake endpoint"
java -cp target/classes:target/test-classes io.elmos.storage.S3ObjectStoreTest
