#!/usr/bin/env bash
# Executes the CAS writer and reader on two independently attested Kubernetes nodes.
# The script consumes an existing immutable credential Secret and a digest-pinned probe image;
# it never creates, prints, copies, or persists credential values.

set -euo pipefail

fail() {
  printf 'multi-host CAS probe: %s\n' "$1" >&2
  exit 2
}

required_environment() {
  local name="$1"
  local value="${!name:-}"
  [[ -n "$value" ]] || fail "missing required environment variable: $name"
  printf '%s' "$value"
}

for command_name in kubectl python3 shasum; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is required"
done

ELMOS_MULTIHOST_CONTEXT="$(required_environment ELMOS_CAS_K8S_CONTEXT)"
ELMOS_MULTIHOST_NAMESPACE="$(required_environment ELMOS_CAS_K8S_NAMESPACE)"
ELMOS_MULTIHOST_IMAGE="$(required_environment ELMOS_CAS_K8S_PROBE_IMAGE)"
ELMOS_MULTIHOST_SERVICE_ACCOUNT="$(required_environment ELMOS_CAS_K8S_SERVICE_ACCOUNT)"
ELMOS_MULTIHOST_CREDENTIAL_SECRET="$(required_environment ELMOS_CAS_K8S_CREDENTIAL_SECRET)"
ELMOS_MULTIHOST_ENDPOINT="$(required_environment ELMOS_CAS_K8S_ENDPOINT)"
ELMOS_MULTIHOST_BUCKET="$(required_environment ELMOS_CAS_K8S_BUCKET)"
ELMOS_MULTIHOST_OUTPUT="$(required_environment ELMOS_CAS_MULTIHOST_OUTPUT_DIR)"
ELMOS_MULTIHOST_HOST_LABEL="${ELMOS_CAS_K8S_HOST_ATTESTATION_LABEL:-elmos.io/host-attestation-id}"
ELMOS_MULTIHOST_CLASSPATH="${ELMOS_CAS_K8S_JAVA_CLASSPATH:-/app/test-classes:/app/classes:/app/object-storage-classes}"
ELMOS_MULTIHOST_TIMEOUT="${ELMOS_CAS_K8S_TIMEOUT_SECONDS:-600}"
ELMOS_MULTIHOST_KEEP="${ELMOS_CAS_K8S_KEEP_RESOURCES:-0}"

[[ "$ELMOS_MULTIHOST_NAMESPACE" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] \
  || fail "namespace is not a DNS label"
[[ "$ELMOS_MULTIHOST_SERVICE_ACCOUNT" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] \
  || fail "service account is not a DNS label"
[[ "$ELMOS_MULTIHOST_CREDENTIAL_SECRET" =~ ^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$ ]] \
  || fail "credential secret is not a DNS label"
[[ "$ELMOS_MULTIHOST_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] \
  || fail "probe image must be pinned by sha256 digest"
[[ "$ELMOS_MULTIHOST_HOST_LABEL" =~ ^([a-z0-9]([-a-z0-9.]*[a-z0-9])?\.)*[a-z0-9]([-a-z0-9.]*[a-z0-9])?/[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])$ ]] \
  || fail "host attestation label is not a qualified Kubernetes label name"
if [[ ! "$ELMOS_MULTIHOST_TIMEOUT" =~ ^[0-9]+$ ]] \
  || (( ELMOS_MULTIHOST_TIMEOUT < 60 || ELMOS_MULTIHOST_TIMEOUT > 1800 )); then
  fail "timeout must be an integer between 60 and 1800 seconds"
fi
[[ "$ELMOS_MULTIHOST_KEEP" == "0" || "$ELMOS_MULTIHOST_KEEP" == "1" ]] \
  || fail "ELMOS_CAS_K8S_KEEP_RESOURCES must be 0 or 1"
if [[ "$ELMOS_MULTIHOST_ENDPOINT" != https://* ]]; then
  [[ "${ELMOS_CAS_K8S_ALLOW_INSECURE_TEST_ENDPOINT:-0}" == "1" ]] \
    || fail "shared-tier endpoint must use HTTPS"
fi

mkdir -p "$ELMOS_MULTIHOST_OUTPUT"
if find "$ELMOS_MULTIHOST_OUTPUT" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  fail "evidence output directory must be empty: $ELMOS_MULTIHOST_OUTPUT"
fi

ELMOS_MULTIHOST_TEMP="$(mktemp -d)"
ELMOS_MULTIHOST_RUN="$(date -u +%Y%m%d%H%M%S)-$$"
ELMOS_MULTIHOST_RUN_SHORT="${ELMOS_MULTIHOST_RUN: -18}"
ELMOS_MULTIHOST_CONFIG_MAP="elmos-cas-probe-${ELMOS_MULTIHOST_RUN_SHORT}"
ELMOS_MULTIHOST_WRITER_JOB="elmos-cas-w-${ELMOS_MULTIHOST_RUN_SHORT}"
ELMOS_MULTIHOST_READER_JOB="elmos-cas-r-${ELMOS_MULTIHOST_RUN_SHORT}"
ELMOS_MULTIHOST_CREATED=0
ELMOS_MULTIHOST_COMPLETE=0

kube() {
  kubectl --context "$ELMOS_MULTIHOST_CONTEXT" --namespace "$ELMOS_MULTIHOST_NAMESPACE" "$@"
}

cleanup() {
  if [[ "$ELMOS_MULTIHOST_CREATED" -eq 1 && "$ELMOS_MULTIHOST_KEEP" -eq 0 ]]; then
    kube delete job "$ELMOS_MULTIHOST_WRITER_JOB" "$ELMOS_MULTIHOST_READER_JOB" \
      --ignore-not-found --wait=false >/dev/null 2>&1 || true
    kube delete configmap "$ELMOS_MULTIHOST_CONFIG_MAP" \
      --ignore-not-found --wait=false >/dev/null 2>&1 || true
  fi
  rm -rf "$ELMOS_MULTIHOST_TEMP"
  if [[ "$ELMOS_MULTIHOST_COMPLETE" -ne 1 ]]; then
    printf 'multi-host CAS probe incomplete; retained evidence: %s\n' \
      "$ELMOS_MULTIHOST_OUTPUT" >&2
  fi
}
trap cleanup EXIT INT TERM

printf '%s\n' \
  '{"schema_version":1,"status":"INCOMPLETE","certification":"NOT_CERTIFIED"}' \
  >"$ELMOS_MULTIHOST_OUTPUT/probe-status.json"

kubectl config get-contexts "$ELMOS_MULTIHOST_CONTEXT" -o name 2>/dev/null \
  | grep -Fxq "$ELMOS_MULTIHOST_CONTEXT" \
  || fail "Kubernetes context does not exist"
kube get namespace "$ELMOS_MULTIHOST_NAMESPACE" >/dev/null 2>&1 \
  || fail "namespace is unavailable"
kube get serviceaccount "$ELMOS_MULTIHOST_SERVICE_ACCOUNT" >/dev/null 2>&1 \
  || fail "service account is unavailable"

for resource in configmaps jobs; do
  [[ "$(kube auth can-i create "$resource")" == "yes" ]] \
    || fail "current identity cannot create $resource in the probe namespace"
  [[ "$(kube auth can-i delete "$resource")" == "yes" ]] \
    || fail "current identity cannot clean up $resource in the probe namespace"
done

ELMOS_MULTIHOST_SECRET_SHAPE="$(kube get secret "$ELMOS_MULTIHOST_CREDENTIAL_SECRET" -o json \
  | python3 -c '
import json, sys
value = json.load(sys.stdin)
keys = set(value.get("data", {}))
expected = {"ELMOS_CAS_PROBE_ACCESS_KEY", "ELMOS_CAS_PROBE_SECRET_KEY"}
print("ok" if value.get("immutable") is True and keys == expected else "bad")
')"
[[ "$ELMOS_MULTIHOST_SECRET_SHAPE" == "ok" ]] \
  || fail "credential Secret must be immutable and contain only the two exact probe keys"

kubectl --context "$ELMOS_MULTIHOST_CONTEXT" get nodes -o json \
  >"$ELMOS_MULTIHOST_TEMP/nodes.json"
ELMOS_MULTIHOST_READY_NODES="$(python3 - "$ELMOS_MULTIHOST_HOST_LABEL" \
  "$ELMOS_MULTIHOST_TEMP/nodes.json" <<'PY'
import json
import pathlib
import sys

label = sys.argv[1]
document = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
count = 0
for node in document.get("items", []):
    conditions = {item.get("type"): item.get("status") for item in node.get("status", {}).get("conditions", [])}
    labels = node.get("metadata", {}).get("labels", {})
    if conditions.get("Ready") == "True" and not node.get("spec", {}).get("unschedulable", False) and labels.get(label):
        count += 1
print(count)
PY
)"
if [[ ! "$ELMOS_MULTIHOST_READY_NODES" =~ ^[0-9]+$ ]] \
  || (( ELMOS_MULTIHOST_READY_NODES < 2 )); then
  fail "at least two Ready schedulable nodes with the host-attestation label are required"
fi

printf 'ELMOS multi-host CAS probe\nrun=%s\n' "$ELMOS_MULTIHOST_RUN" \
  >"$ELMOS_MULTIHOST_TEMP/content.bin"
shasum -a 256 "$ELMOS_MULTIHOST_TEMP/content.bin" \
  >"$ELMOS_MULTIHOST_OUTPUT/content.sha256"

kube create configmap "$ELMOS_MULTIHOST_CONFIG_MAP" \
  --from-file=content.bin="$ELMOS_MULTIHOST_TEMP/content.bin" >/dev/null
ELMOS_MULTIHOST_CREATED=1

create_job() {
  local mode="$1"
  local job_name="$2"
  local excluded_hostname="${3:-}"
  python3 - "$mode" "$job_name" "$excluded_hostname" \
    "$ELMOS_MULTIHOST_IMAGE" "$ELMOS_MULTIHOST_SERVICE_ACCOUNT" \
    "$ELMOS_MULTIHOST_CREDENTIAL_SECRET" "$ELMOS_MULTIHOST_CONFIG_MAP" \
    "$ELMOS_MULTIHOST_ENDPOINT" "$ELMOS_MULTIHOST_BUCKET" \
    "$ELMOS_MULTIHOST_CLASSPATH" "$ELMOS_MULTIHOST_HOST_LABEL" \
    <<'PY' | kube create -f - >/dev/null
import json
import sys

(
    mode,
    name,
    excluded_hostname,
    image,
    service_account,
    secret,
    config_map,
    endpoint,
    bucket,
    classpath,
    host_attestation_label,
) = sys.argv[1:]

pod_spec = {
    "automountServiceAccountToken": False,
    "serviceAccountName": service_account,
    "restartPolicy": "Never",
    "securityContext": {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    },
    "containers": [
        {
            "name": "probe",
            "image": image,
            "imagePullPolicy": "IfNotPresent",
            "command": ["/bin/sh", "-ceu"],
            "args": [
                'java -cp "$ELMOS_CAS_PROBE_CLASSPATH" '
                'io.elmos.cas.S3CasStoreProcessProbe "$ELMOS_CAS_PROBE_MODE" '
                '/probe/content.bin /tmp/receipt.json; cat /tmp/receipt.json'
            ],
            "env": [
                {"name": "ELMOS_CAS_PROBE_MODE", "value": mode},
                {"name": "ELMOS_CAS_PROBE_ENDPOINT", "value": endpoint},
                {"name": "ELMOS_CAS_PROBE_BUCKET", "value": bucket},
                {"name": "ELMOS_CAS_PROBE_CLASSPATH", "value": classpath},
                {
                    "name": "ELMOS_CAS_PROBE_ACCESS_KEY",
                    "valueFrom": {"secretKeyRef": {"name": secret, "key": "ELMOS_CAS_PROBE_ACCESS_KEY"}},
                },
                {
                    "name": "ELMOS_CAS_PROBE_SECRET_KEY",
                    "valueFrom": {"secretKeyRef": {"name": secret, "key": "ELMOS_CAS_PROBE_SECRET_KEY"}},
                },
            ],
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "1", "memory": "512Mi"},
            },
            "securityContext": {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
            },
            "volumeMounts": [
                {"name": "content", "mountPath": "/probe", "readOnly": True},
                {"name": "tmp", "mountPath": "/tmp"},
            ],
        }
    ],
    "volumes": [
        {"name": "content", "configMap": {"name": config_map}},
        {"name": "tmp", "emptyDir": {"sizeLimit": "16Mi"}},
    ],
}
match_expressions = [{"key": host_attestation_label, "operator": "Exists"}]
if excluded_hostname:
    match_expressions.append(
        {
            "key": "kubernetes.io/hostname",
            "operator": "NotIn",
            "values": [excluded_hostname],
        }
    )
pod_spec["affinity"] = {
    "nodeAffinity": {
        "requiredDuringSchedulingIgnoredDuringExecution": {
            "nodeSelectorTerms": [{"matchExpressions": match_expressions}]
        }
    }
}

document = {
    "apiVersion": "batch/v1",
    "kind": "Job",
    "metadata": {"name": name, "labels": {"app.kubernetes.io/name": "elmos-cas-multihost-probe"}},
    "spec": {
        "backoffLimit": 0,
        "activeDeadlineSeconds": 300,
        "template": {
            "metadata": {"labels": {"app.kubernetes.io/name": "elmos-cas-multihost-probe"}},
            "spec": pod_spec,
        },
    },
}
json.dump(document, sys.stdout, separators=(",", ":"))
PY
}

wait_for_job() {
  local job_name="$1"
  if ! kube wait --for=condition=complete "job/$job_name" \
    --timeout="${ELMOS_MULTIHOST_TIMEOUT}s" >/dev/null; then
    kube get job "$job_name" -o yaml >"$ELMOS_MULTIHOST_OUTPUT/${job_name}.failure.yaml" 2>&1 || true
    kube logs "job/$job_name" >"$ELMOS_MULTIHOST_OUTPUT/${job_name}.failure.log" 2>&1 || true
    fail "job did not complete: $job_name"
  fi
}

job_pod() {
  kube get pods -l "job-name=$1" -o json \
    | python3 -c '
import json, sys
items = json.load(sys.stdin).get("items", [])
if len(items) != 1:
    raise SystemExit("job must own exactly one pod")
print(items[0]["metadata"]["name"])
'
}

extract_receipt() {
  local log_path="$1"
  local receipt_path="$2"
  python3 - "$log_path" "$receipt_path" <<'PY'
import json
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
start = text.find("{")
if start < 0:
    raise SystemExit("receipt JSON is missing from pod log")
value = json.loads(text[start:])
path = pathlib.Path(sys.argv[2])
path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

node_receipt() {
  local pod_name="$1"
  local output_path="$2"
  local pod_json="$ELMOS_MULTIHOST_TEMP/${pod_name}.json"
  local node_json="$ELMOS_MULTIHOST_TEMP/${pod_name}.node.json"
  kube get pod "$pod_name" -o json >"$pod_json"
  local node_name
  node_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["spec"]["nodeName"])' "$pod_json")"
  kubectl --context "$ELMOS_MULTIHOST_CONTEXT" get node "$node_name" -o json >"$node_json"
  python3 - "$node_json" "$ELMOS_MULTIHOST_HOST_LABEL" "$output_path" <<'PY'
import hashlib
import json
import pathlib
import sys

node = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
label = sys.argv[2]
metadata = node.get("metadata", {})
status = node.get("status", {})
node_info = status.get("nodeInfo", {})
attestation = metadata.get("labels", {}).get(label, "")
fields = {
    "node_uid": metadata.get("uid", ""),
    "machine_id": node_info.get("machineID", ""),
    "system_uuid": node_info.get("systemUUID", ""),
    "provider_id": node.get("spec", {}).get("providerID", ""),
    "host_attestation_id": attestation,
}
if any(not value for value in fields.values()):
    raise SystemExit("node identity or host attestation is incomplete")
receipt = {
    "schema_version": 1,
    "identity_hashes": {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for key, value in fields.items()
    },
    "kubelet_version": node_info.get("kubeletVersion", ""),
    "operating_system": node_info.get("operatingSystem", ""),
    "architecture": node_info.get("architecture", ""),
}
pathlib.Path(sys.argv[3]).write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
}

create_job write "$ELMOS_MULTIHOST_WRITER_JOB"
wait_for_job "$ELMOS_MULTIHOST_WRITER_JOB"
ELMOS_MULTIHOST_WRITER_POD="$(job_pod "$ELMOS_MULTIHOST_WRITER_JOB")"
ELMOS_MULTIHOST_WRITER_NODE="$(kube get pod "$ELMOS_MULTIHOST_WRITER_POD" -o jsonpath='{.spec.nodeName}')"
ELMOS_MULTIHOST_WRITER_HOSTNAME="$(kubectl --context "$ELMOS_MULTIHOST_CONTEXT" \
  get node "$ELMOS_MULTIHOST_WRITER_NODE" -o jsonpath='{.metadata.labels.kubernetes\.io/hostname}')"
[[ -n "$ELMOS_MULTIHOST_WRITER_HOSTNAME" ]] \
  || fail "writer node has no kubernetes.io/hostname label"
kube logs "$ELMOS_MULTIHOST_WRITER_POD" >"$ELMOS_MULTIHOST_OUTPUT/writer.log"
extract_receipt "$ELMOS_MULTIHOST_OUTPUT/writer.log" \
  "$ELMOS_MULTIHOST_OUTPUT/writer-receipt.json"
node_receipt "$ELMOS_MULTIHOST_WRITER_POD" \
  "$ELMOS_MULTIHOST_OUTPUT/writer-node-receipt.json"

create_job read "$ELMOS_MULTIHOST_READER_JOB" "$ELMOS_MULTIHOST_WRITER_HOSTNAME"
wait_for_job "$ELMOS_MULTIHOST_READER_JOB"
ELMOS_MULTIHOST_READER_POD="$(job_pod "$ELMOS_MULTIHOST_READER_JOB")"
kube logs "$ELMOS_MULTIHOST_READER_POD" >"$ELMOS_MULTIHOST_OUTPUT/reader.log"
extract_receipt "$ELMOS_MULTIHOST_OUTPUT/reader.log" \
  "$ELMOS_MULTIHOST_OUTPUT/reader-receipt.json"
node_receipt "$ELMOS_MULTIHOST_READER_POD" \
  "$ELMOS_MULTIHOST_OUTPUT/reader-node-receipt.json"

python3 - "$ELMOS_MULTIHOST_OUTPUT" "$ELMOS_MULTIHOST_ENDPOINT" \
  "$ELMOS_MULTIHOST_BUCKET" "$ELMOS_MULTIHOST_IMAGE" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
endpoint = sys.argv[2]
bucket = sys.argv[3]
image = sys.argv[4]
writer = json.loads((root / "writer-receipt.json").read_text(encoding="utf-8"))
reader = json.loads((root / "reader-receipt.json").read_text(encoding="utf-8"))
writer_node = json.loads((root / "writer-node-receipt.json").read_text(encoding="utf-8"))
reader_node = json.loads((root / "reader-node-receipt.json").read_text(encoding="utf-8"))

required = {
    "schema_version", "operation", "process_id", "observed_at", "endpoint",
    "bucket", "digest", "size_bytes", "verified",
}
for label, receipt, operation in (
    ("writer", writer, "write"),
    ("reader", reader, "read"),
):
    if set(receipt) != required or receipt.get("schema_version") != 1:
        raise SystemExit(f"{label} receipt shape is invalid")
    if receipt.get("operation") != operation or receipt.get("verified") is not True:
        raise SystemExit(f"{label} did not complete the expected verified operation")
    if receipt.get("endpoint") != endpoint or receipt.get("bucket") != bucket:
        raise SystemExit(f"{label} endpoint or bucket is not bound to this run")
if writer["digest"] != reader["digest"] or writer["size_bytes"] != reader["size_bytes"]:
    raise SystemExit("writer and reader content identities differ")

identity_keys = {"node_uid", "machine_id", "system_uuid", "provider_id", "host_attestation_id"}
for key in identity_keys:
    if writer_node["identity_hashes"].get(key) == reader_node["identity_hashes"].get(key):
        raise SystemExit(f"writer and reader do not have distinct {key}")

summary = {
    "schema_version": 1,
    "status": "PASS",
    "evidence_class": "MULTI_KUBERNETES_NODE_EXECUTED_SELF_ATTESTED",
    "boundary": "DISTINCT_NODE_MACHINE_PROVIDER_AND_HOST_ATTESTATION_IDENTITIES",
    "topology": "TWO_SCHEDULER_DISTINCT_KUBERNETES_NODES",
    "probe_image_digest": image.rsplit("@sha256:", 1)[1],
    "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
    "bucket_sha256": hashlib.sha256(bucket.encode("utf-8")).hexdigest(),
    "writer": {"receipt": writer, "node": writer_node},
    "reader": {"receipt": reader, "node": reader_node},
    "production_certification": "NOT_CERTIFIED",
    "limitations": [
        "cluster and host-attestation administration was not independently verified by this runner",
        "this probe does not certify KMS, disaster recovery, region failover, or production load",
    ],
}
(root / "probe-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(root / "probe-status.json").write_text(
    '{"schema_version":1,"status":"COMPLETE","certification":"NOT_CERTIFIED"}\n',
    encoding="utf-8",
)
print(
    "PASS Kubernetes multi-node CAS probe",
    f"digest={writer['digest']}",
    "certification=NOT_CERTIFIED",
)
PY

ELMOS_MULTIHOST_COMPLETE=1
printf 'evidence: %s\n' "$ELMOS_MULTIHOST_OUTPUT"
