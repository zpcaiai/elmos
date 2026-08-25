#!/usr/bin/env bash
# Proves the shared-tier boundary with an external MinIO process and two independent JVMs.
# This is local engineering evidence only; it does not certify a production provider or topology.

set -euo pipefail

ELMOS_PROBE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ELMOS_PROBE_SERVER_IMAGE="${ELMOS_CAS_PROBE_SERVER_IMAGE:-minio/minio:RELEASE.2025-04-22T22-12-26Z}"
ELMOS_PROBE_CLIENT_IMAGE="${ELMOS_CAS_PROBE_CLIENT_IMAGE:-minio/mc:RELEASE.2025-04-16T18-13-26Z}"
ELMOS_PROBE_CONTAINER="elmos-cas-shared-tier-probe-$$"
ELMOS_PROBE_BUCKET="elmos-cas-two-process"
ELMOS_PROBE_ACCESS_KEY="elmos-probe"
ELMOS_PROBE_SECRET_KEY="elmos-local-probe-only"
ELMOS_PROBE_TEMP="$(mktemp -d)"
ELMOS_PROBE_OUTPUT="${ELMOS_CAS_PROBE_OUTPUT_DIR:-$ELMOS_PROBE_TEMP/evidence}"
ELMOS_PROBE_OUTPUT_IN_TEMP=1
ELMOS_PROBE_SUCCESS=0
if [[ -n "${ELMOS_CAS_PROBE_OUTPUT_DIR:-}" ]]; then
  ELMOS_PROBE_OUTPUT_IN_TEMP=0
fi

cleanup() {
  docker rm -f "$ELMOS_PROBE_CONTAINER" >/dev/null 2>&1 || true
  if [[ "$ELMOS_PROBE_SUCCESS" -ne 1 ]]; then
    echo "probe did not complete; incomplete evidence retained at: $ELMOS_PROBE_OUTPUT" >&2
  fi
  if [[ "$ELMOS_PROBE_OUTPUT_IN_TEMP" -eq 0 ]]; then
    rm -rf "$ELMOS_PROBE_TEMP"
  fi
}
trap cleanup EXIT INT TERM

mkdir -p "$ELMOS_PROBE_OUTPUT"
if find "$ELMOS_PROBE_OUTPUT" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  echo "evidence output directory must be empty: $ELMOS_PROBE_OUTPUT" >&2
  exit 2
fi
ELMOS_PROBE_CONTENT="$ELMOS_PROBE_TEMP/content.bin"
ELMOS_PROBE_WRITER_RECEIPT="$ELMOS_PROBE_OUTPUT/writer-receipt.json"
ELMOS_PROBE_READER_RECEIPT="$ELMOS_PROBE_OUTPUT/reader-receipt.json"
ELMOS_PROBE_SUMMARY="$ELMOS_PROBE_OUTPUT/probe-summary.json"
ELMOS_PROBE_STATUS="$ELMOS_PROBE_OUTPUT/probe-status.json"
printf 'ELMOS external shared tier process-boundary probe\nrun=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  >"$ELMOS_PROBE_CONTENT"
printf '%s\n' \
  '{"schema_version":1,"status":"INCOMPLETE","production_certification":"NOT_CERTIFIED"}' \
  >"$ELMOS_PROBE_STATUS"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 2
fi
if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is unavailable" >&2
  exit 2
fi
if ! docker image inspect "$ELMOS_PROBE_SERVER_IMAGE" >/dev/null 2>&1; then
  echo "preloaded MinIO server image is required: $ELMOS_PROBE_SERVER_IMAGE" >&2
  exit 2
fi
if ! docker image inspect "$ELMOS_PROBE_CLIENT_IMAGE" >/dev/null 2>&1; then
  echo "preloaded MinIO client image is required: $ELMOS_PROBE_CLIENT_IMAGE" >&2
  exit 2
fi

ELMOS_PROBE_JAVA_HOME="${ELMOS_JAVA_HOME:-}"
if [[ -z "$ELMOS_PROBE_JAVA_HOME" ]] && [[ -x /usr/libexec/java_home ]]; then
  ELMOS_PROBE_JAVA_HOME="$(/usr/libexec/java_home -v 21 2>/dev/null || true)"
fi
if [[ -z "$ELMOS_PROBE_JAVA_HOME" ]] || [[ ! -x "$ELMOS_PROBE_JAVA_HOME/bin/java" ]]; then
  echo "JDK 21 is required; set ELMOS_JAVA_HOME" >&2
  exit 2
fi
ELMOS_PROBE_JAVA_VERSION="$($ELMOS_PROBE_JAVA_HOME/bin/java -XshowSettings:properties -version \
  2>&1 | awk -F'= ' '/java.specification.version =/{print $2; exit}')"
if [[ "$ELMOS_PROBE_JAVA_VERSION" != "21" ]]; then
  echo "JDK 21 is required; observed specification version: ${ELMOS_PROBE_JAVA_VERSION:-unknown}" >&2
  exit 2
fi
if ! command -v mvn >/dev/null 2>&1; then
  echo "Maven is required" >&2
  exit 2
fi

cd "$ELMOS_PROBE_REPO"
JAVA_HOME="$ELMOS_PROBE_JAVA_HOME" PATH="$ELMOS_PROBE_JAVA_HOME/bin:$PATH" \
  mvn -q -pl modules/cas -am -DskipTests test-compile

ELMOS_PROBE_SOURCE_INPUTS=(
  modules/cas/src/main/java/io/elmos/cas/CasDigest.java
  modules/cas/src/main/java/io/elmos/cas/CasExceptions.java
  modules/cas/src/main/java/io/elmos/cas/CasStore.java
  modules/cas/src/main/java/io/elmos/cas/CasText.java
  modules/cas/src/main/java/io/elmos/cas/S3CasStore.java
  modules/cas/src/test/java/io/elmos/cas/S3CasStoreProcessProbe.java
  modules/object-storage/src/main/java/io/elmos/storage/SigV4Presigner.java
  scripts/cas/run-two-process-shared-tier-probe.sh
)
ELMOS_PROBE_CLASS_INPUTS=(
  modules/cas/target/classes/io/elmos/cas/CasDigest*.class
  modules/cas/target/classes/io/elmos/cas/CasExceptions*.class
  modules/cas/target/classes/io/elmos/cas/CasStore*.class
  modules/cas/target/classes/io/elmos/cas/CasText*.class
  modules/cas/target/classes/io/elmos/cas/S3CasStore*.class
  modules/cas/target/test-classes/io/elmos/cas/S3CasStoreProcessProbe*.class
  modules/object-storage/target/classes/io/elmos/storage/SigV4Presigner*.class
)
for ELMOS_PROBE_CLASS in "${ELMOS_PROBE_CLASS_INPUTS[@]}"; do
  if [[ ! -f "$ELMOS_PROBE_CLASS" ]]; then
    echo "expected compiled probe input is missing: $ELMOS_PROBE_CLASS" >&2
    exit 3
  fi
done
shasum -a 256 "${ELMOS_PROBE_SOURCE_INPUTS[@]}" \
  >"$ELMOS_PROBE_OUTPUT/source-files.before.sha256"
shasum -a 256 "${ELMOS_PROBE_CLASS_INPUTS[@]}" \
  >"$ELMOS_PROBE_OUTPUT/class-files.before.sha256"
"$ELMOS_PROBE_JAVA_HOME/bin/java" -version \
  >"$ELMOS_PROBE_OUTPUT/java-version.txt" 2>&1
JAVA_HOME="$ELMOS_PROBE_JAVA_HOME" PATH="$ELMOS_PROBE_JAVA_HOME/bin:$PATH" mvn -version \
  >"$ELMOS_PROBE_OUTPUT/maven-version.txt" 2>&1
shasum -a 256 "$ELMOS_PROBE_CONTENT" >"$ELMOS_PROBE_OUTPUT/content.sha256"
docker image inspect "$ELMOS_PROBE_SERVER_IMAGE" --format '{{json .RepoDigests}} {{json .Id}}' \
  >"$ELMOS_PROBE_OUTPUT/minio-server-image.txt"
docker image inspect "$ELMOS_PROBE_CLIENT_IMAGE" --format '{{json .RepoDigests}} {{json .Id}}' \
  >"$ELMOS_PROBE_OUTPUT/minio-client-image.txt"
docker version --format '{{json .Server.Version}} {{json .Server.Os}} {{json .Server.Arch}}' \
  >"$ELMOS_PROBE_OUTPUT/docker-server.txt"

docker run -d --rm --name "$ELMOS_PROBE_CONTAINER" \
  -p 127.0.0.1::9000 \
  -e "MINIO_ROOT_USER=$ELMOS_PROBE_ACCESS_KEY" \
  -e "MINIO_ROOT_PASSWORD=$ELMOS_PROBE_SECRET_KEY" \
  "$ELMOS_PROBE_SERVER_IMAGE" server /data >"$ELMOS_PROBE_OUTPUT/container-id.txt"

ELMOS_PROBE_PORT="$(docker port "$ELMOS_PROBE_CONTAINER" 9000/tcp | sed -n '1s/.*://p')"
if [[ -z "$ELMOS_PROBE_PORT" ]]; then
  echo "could not resolve the published MinIO port" >&2
  exit 3
fi
ELMOS_PROBE_ENDPOINT="http://127.0.0.1:$ELMOS_PROBE_PORT"

ELMOS_PROBE_READY=0
for _ in $(seq 1 60); do
  if curl -fsS "$ELMOS_PROBE_ENDPOINT/minio/health/ready" >/dev/null 2>&1; then
    ELMOS_PROBE_READY=1
    break
  fi
  sleep 1
done
if [[ "$ELMOS_PROBE_READY" -ne 1 ]]; then
  docker logs "$ELMOS_PROBE_CONTAINER" >&2 || true
  echo "MinIO did not become ready within 60 seconds" >&2
  exit 3
fi

docker run --rm --add-host host.docker.internal:host-gateway \
  -e "ELMOS_PROBE_ENDPOINT=http://host.docker.internal:$ELMOS_PROBE_PORT" \
  -e "ELMOS_PROBE_ACCESS_KEY=$ELMOS_PROBE_ACCESS_KEY" \
  -e "ELMOS_PROBE_SECRET_KEY=$ELMOS_PROBE_SECRET_KEY" \
  -e "ELMOS_PROBE_BUCKET=$ELMOS_PROBE_BUCKET" \
  --entrypoint /bin/sh "$ELMOS_PROBE_CLIENT_IMAGE" -c \
  'mc alias set probe "$ELMOS_PROBE_ENDPOINT" "$ELMOS_PROBE_ACCESS_KEY" "$ELMOS_PROBE_SECRET_KEY" >/dev/null && mc mb --ignore-existing "probe/$ELMOS_PROBE_BUCKET" >/dev/null'

ELMOS_PROBE_CLASSPATH="modules/cas/target/test-classes:modules/cas/target/classes:modules/object-storage/target/classes"
export ELMOS_CAS_PROBE_ENDPOINT="$ELMOS_PROBE_ENDPOINT"
export ELMOS_CAS_PROBE_BUCKET="$ELMOS_PROBE_BUCKET"
export ELMOS_CAS_PROBE_ACCESS_KEY="$ELMOS_PROBE_ACCESS_KEY"
export ELMOS_CAS_PROBE_SECRET_KEY="$ELMOS_PROBE_SECRET_KEY"

"$ELMOS_PROBE_JAVA_HOME/bin/java" -cp "$ELMOS_PROBE_CLASSPATH" io.elmos.cas.S3CasStoreProcessProbe \
  write "$ELMOS_PROBE_CONTENT" "$ELMOS_PROBE_WRITER_RECEIPT" &
ELMOS_PROBE_WRITER_SHELL_PID=$!
wait "$ELMOS_PROBE_WRITER_SHELL_PID"

"$ELMOS_PROBE_JAVA_HOME/bin/java" -cp "$ELMOS_PROBE_CLASSPATH" io.elmos.cas.S3CasStoreProcessProbe \
  read "$ELMOS_PROBE_CONTENT" "$ELMOS_PROBE_READER_RECEIPT" &
ELMOS_PROBE_READER_SHELL_PID=$!
wait "$ELMOS_PROBE_READER_SHELL_PID"

docker inspect "$ELMOS_PROBE_CONTAINER" \
  --format '{{json .Config.Image}} {{json .Image}} {{json .State.StartedAt}}' \
  >"$ELMOS_PROBE_OUTPUT/minio-container.txt"
docker logs "$ELMOS_PROBE_CONTAINER" >"$ELMOS_PROBE_OUTPUT/minio.log" 2>&1
shasum -a 256 "${ELMOS_PROBE_SOURCE_INPUTS[@]}" \
  >"$ELMOS_PROBE_OUTPUT/source-files.after.sha256"
shasum -a 256 "${ELMOS_PROBE_CLASS_INPUTS[@]}" \
  >"$ELMOS_PROBE_OUTPUT/class-files.after.sha256"
if ! cmp -s "$ELMOS_PROBE_OUTPUT/source-files.before.sha256" \
    "$ELMOS_PROBE_OUTPUT/source-files.after.sha256"; then
  echo "probe source inputs changed during execution" >&2
  exit 4
fi
if ! cmp -s "$ELMOS_PROBE_OUTPUT/class-files.before.sha256" \
    "$ELMOS_PROBE_OUTPUT/class-files.after.sha256"; then
  echo "probe bytecode inputs changed during execution" >&2
  exit 4
fi

python3 - "$ELMOS_PROBE_WRITER_RECEIPT" "$ELMOS_PROBE_READER_RECEIPT" \
  "$ELMOS_PROBE_CONTENT" "$ELMOS_PROBE_ENDPOINT" "$ELMOS_PROBE_BUCKET" \
  "$ELMOS_PROBE_SUMMARY" "$ELMOS_PROBE_STATUS" <<'PY'
import hashlib
import json
import os
import pathlib
import sys


def fail(message: str) -> None:
    raise SystemExit(f"receipt validation failed: {message}")


writer = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
reader = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
content = pathlib.Path(sys.argv[3]).read_bytes()
endpoint = sys.argv[4]
bucket = sys.argv[5]
summary_path = pathlib.Path(sys.argv[6])
status_path = pathlib.Path(sys.argv[7])
required = {
    "schema_version", "operation", "process_id", "observed_at", "endpoint",
    "bucket", "digest", "size_bytes", "verified",
}
for label, receipt in (("writer", writer), ("reader", reader)):
    if set(receipt) != required:
        fail(f"{label} receipt fields are not exact")
    if receipt["schema_version"] != 1:
        fail(f"{label} schema_version is unsupported")
    if receipt["endpoint"] != endpoint or receipt["bucket"] != bucket:
        fail(f"{label} endpoint or bucket does not match the launched store")
    if type(receipt["process_id"]) is not int or receipt["process_id"] <= 0:
        fail(f"{label} process_id is invalid")
    if receipt["verified"] is not True:
        fail(f"{label} did not verify the object bytes")
if writer["operation"] != "write" or reader["operation"] != "read":
    fail("writer/reader operations are not exact")
if writer["process_id"] == reader["process_id"]:
    fail("writer and reader must be distinct JVMs")
if writer["digest"] != reader["digest"] or writer["size_bytes"] != reader["size_bytes"]:
    fail("writer and reader did not observe the same content identity")
expected = f"sha256:{hashlib.sha256(content).hexdigest()}/{len(content)}"
if writer["digest"] != expected or writer["size_bytes"] != len(content):
    fail("JVM receipt does not match an independent content hash and size")
summary = {
    "schema_version": 1,
    "status": "PASS",
    "evidence_class": "LOCAL_EXECUTED_SELF_ATTESTED",
    "boundary": "EXTERNAL_MINIO_TWO_INDEPENDENT_JVMS",
    "topology": "SINGLE_HOST_EXTERNAL_PROCESS",
    "production_certification": "NOT_CERTIFIED",
    "writer": writer,
    "reader": reader,
}
summary_tmp = summary_path.with_name(summary_path.name + f".tmp.{os.getpid()}")
summary_tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(summary_tmp, summary_path)
status_tmp = status_path.with_name(status_path.name + f".tmp.{os.getpid()}")
status_tmp.write_text(
    '{"schema_version":1,"status":"COMPLETE","production_certification":"NOT_CERTIFIED"}\n',
    encoding="utf-8",
)
os.replace(status_tmp, status_path)
print(
    "PASS two-process shared tier",
    f"writer_pid={writer['process_id']}",
    f"reader_pid={reader['process_id']}",
    f"digest={writer['digest']}",
)
PY

ELMOS_PROBE_SUCCESS=1
echo "evidence: $ELMOS_PROBE_OUTPUT"
