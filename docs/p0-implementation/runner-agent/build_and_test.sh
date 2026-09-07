#!/usr/bin/env bash
# Build the Runner Agent and run its acceptance suite with a JDK alone.
#
# Deliberately independent of Maven: the agent has no dependencies, so the whole
# build is two javac invocations. This is the fastest way to verify a change and
# it is what the container build does too.
set -euo pipefail

cd "$(dirname "$0")"
rm -rf target
mkdir -p target/classes target/test-classes

echo "==> compiling main sources"
javac -Xlint:all -Werror -d target/classes $(find src/main/java -name '*.java')

echo "==> compiling acceptance suite"
javac -d target/test-classes -cp target/classes $(find src/test/java -name '*.java')

echo "==> packaging"
printf 'Main-Class: io.elmos.runner.RunnerAgentMain\n' > target/manifest.txt
jar --create --file target/elmos-runner-agent.jar --manifest target/manifest.txt -C target/classes .
echo "    $(du -h target/elmos-runner-agent.jar | cut -f1) target/elmos-runner-agent.jar"

echo "==> running acceptance suite"
java -cp target/classes:target/test-classes io.elmos.runner.AgentSelfTest
