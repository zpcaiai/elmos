"""Kubernetes deployment, rollback, recovery and failure-injection boundary."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import AuthorizationError, ContractError
from .external import AdapterOutcome, OutcomeStatus
from .models import bytes_digest, digest, is_sha256_digest, require_mapping, require_string, utc_now


class CommandRunner(Protocol):
    evidence_class: str

    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> Mapping[str, Any]: ...


class SubprocessCommandRunner:
    """Execute an explicit argv without a shell or inherited credentials."""

    evidence_class = "EXTERNAL_EXECUTED"

    def __init__(self, *, environment: Mapping[str, str] | None = None) -> None:
        safe_environment = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "LANG": "C"}
        safe_environment.update(dict(environment or {}))
        self.environment = safe_environment

    def run(self, argv: Sequence[str], *, timeout_seconds: int) -> Mapping[str, Any]:
        completed = subprocess.run(
            list(argv), check=False, capture_output=True, text=True, timeout=timeout_seconds, env=self.environment,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "argv_digest": digest(list(argv)),
        }


@dataclass(frozen=True, slots=True)
class FailureScenario:
    scenario_id: str
    target: str
    injection: str
    steady_state_oracle: str
    rollback_required: bool = True


FAILURE_SCENARIOS = (
    FailureScenario("pod-crash", "deployment", "delete-one-pod", "replacement-ready"),
    FailureScenario("node-drain", "node", "cordon-and-drain", "workload-rescheduled"),
    FailureScenario("database-outage", "postgresql", "deny-egress", "fail-closed-and-recover"),
    FailureScenario("object-store-outage", "object-store", "deny-egress", "unknown-outcome-reconciled"),
    FailureScenario("event-bus-rebalance", "event-bus", "restart-consumer", "no-duplicate-side-effect"),
    FailureScenario("secrets-broker-outage", "secrets-broker", "deny-egress", "new-leases-denied"),
    FailureScenario("disk-full", "pvc", "fill-quota", "write-blocked-and-alerted"),
    FailureScenario("lease-takeover", "worker", "terminate-owner", "new-fencing-token-wins"),
)


class KubernetesAdapter:
    """Exact-context Kubernetes adapter. Apply/destroy require explicit mode."""

    adapter_id = "kubernetes-kubectl"
    adapter_version = "2.0.0"
    capability = "kubernetes"

    def __init__(
        self, *, context: str, namespace: str, allowed_manifest_roots: Sequence[str],
        runner: CommandRunner | None = None, execution_mode: str = "dry-run",
    ) -> None:
        if execution_mode not in {"dry-run", "apply"}:
            raise ContractError("INVALID_INPUT", "execution_mode must be dry-run or apply")
        self.context = require_string(context, "context")
        self.namespace = require_string(namespace, "namespace")
        self.allowed_manifest_roots = tuple(Path(root).resolve() for root in allowed_manifest_roots)
        self.runner = runner or SubprocessCommandRunner()
        self.execution_mode = execution_mode

    def _manifest(self, payload: Mapping[str, Any]) -> Path:
        manifest = Path(require_string(payload.get("manifest_path"), "payload.manifest_path")).resolve()
        if not manifest.is_file() or not any(manifest == root or manifest.is_relative_to(root) for root in self.allowed_manifest_roots):
            raise AuthorizationError("MANIFEST_SCOPE_DENIED", "manifest is outside approved roots")
        raw = manifest.read_bytes()
        lowered = raw.lower()
        forbidden = (b"stringdata:", b"password:", b"private_key:", b"api_key:")
        if any(marker in lowered for marker in forbidden):
            raise ContractError("SECRET_EXPOSURE", "manifest contains an inline secret-like field")
        return manifest

    def _kubectl(self, *args: str, timeout_seconds: int = 120) -> Mapping[str, Any]:
        return self.runner.run(
            ["kubectl", "--context", self.context, "--namespace", self.namespace, *args],
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _outcome(response: Mapping[str, Any], *, action: str, evidence_class: str, side_effect: bool) -> AdapterOutcome:
        returncode = int(response.get("returncode", 1))
        raw = {
            "action": action,
            "argv_digest": response.get("argv_digest"),
            "stdout_hash": bytes_digest(str(response.get("stdout", "")).encode()),
            "stderr_hash": bytes_digest(str(response.get("stderr", "")).encode()),
            "returncode": returncode,
            "observed_at": utc_now(),
        }
        if returncode == 0:
            return AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED, result={"action": action, "completed": True},
                raw_evidence=raw, evidence_class=evidence_class, side_effect_performed=side_effect,
            )
        return AdapterOutcome(
            status=OutcomeStatus.FAILED, error={"code": "KUBECTL_FAILED", "returncode": returncode},
            raw_evidence=raw, evidence_class=evidence_class, side_effect_performed=side_effect,
        )

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        action = str(operation["action"])
        manifest = self._manifest(payload) if action in {"server-dry-run", "apply", "destroy"} else None
        evidence_class = getattr(self.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED")
        if action == "server-dry-run":
            response = self._kubectl("apply", "--server-side", "--dry-run=server", "-f", str(manifest))
            return self._outcome(response, action=action, evidence_class=evidence_class, side_effect=False)
        if action == "apply":
            if self.execution_mode != "apply":
                return AdapterOutcome(status=OutcomeStatus.NOT_RUN, error={"code": "KUBERNETES_APPLY_NOT_AUTHORIZED"}, evidence_class="NOT_RUN")
            image = require_string(payload.get("image"), "payload.image")
            required = ("approved_isolated_environment", "owner", "budget", "cleanup_ttl_minutes")
            missing = [key for key in required if not payload.get(key)]
            if re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", image) is None or missing:
                raise AuthorizationError("KUBERNETES_RELEASE_DENIED", f"immutable image and isolated-environment metadata required; missing={missing}")
            if image.encode() not in manifest.read_bytes():
                raise AuthorizationError("KUBERNETES_IMAGE_MISMATCH", "manifest image does not match the approved digest")
            response = self._kubectl("apply", "--server-side", "--field-manager=elmos-autonomy", "-f", str(manifest), timeout_seconds=300)
            result = self._outcome(response, action=action, evidence_class=evidence_class, side_effect=True)
            if result.status == OutcomeStatus.SUCCEEDED:
                return AdapterOutcome(
                    status=result.status, result={**dict(result.result), "image": image, "namespace": self.namespace},
                    raw_evidence=result.raw_evidence, evidence_class=result.evidence_class,
                    side_effect_performed=True, compensation_token=str(manifest),
                )
            return result
        if action == "rollout-status":
            deployment = require_string(payload.get("deployment"), "payload.deployment")
            response = self._kubectl("rollout", "status", f"deployment/{deployment}", "--timeout=180s", timeout_seconds=200)
            return self._outcome(response, action=action, evidence_class=evidence_class, side_effect=False)
        if action == "rollback":
            if self.execution_mode != "apply":
                return AdapterOutcome(status=OutcomeStatus.NOT_RUN, error={"code": "KUBERNETES_ROLLBACK_NOT_AUTHORIZED"}, evidence_class="NOT_RUN")
            deployment = require_string(payload.get("deployment"), "payload.deployment")
            revision = int(payload.get("revision", 0))
            if revision < 1:
                raise ContractError("INVALID_INPUT", "rollback revision must be positive")
            response = self._kubectl("rollout", "undo", f"deployment/{deployment}", f"--to-revision={revision}")
            return self._outcome(response, action=action, evidence_class=evidence_class, side_effect=True)
        if action == "destroy":
            if self.execution_mode != "apply" or payload.get("cleanup_authorized") is not True:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "KUBERNETES_DESTROY_DENIED"})
            response = self._kubectl("delete", "-f", str(manifest), "--wait=true", "--timeout=180s", timeout_seconds=200)
            return self._outcome(response, action=action, evidence_class=evidence_class, side_effect=True)
        return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "KUBERNETES_ACTION_DENIED"})

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        metadata = require_mapping(operation.get("request_metadata", {}), "request_metadata")
        deployment = metadata.get("deployment")
        if not isinstance(deployment, str):
            return AdapterOutcome(status=OutcomeStatus.UNKNOWN, evidence_class="NOT_RUN")
        response = self._kubectl("get", "deployment", deployment, "-o", "json")
        return self._outcome(
            response, action="reconcile", evidence_class=getattr(self.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED"), side_effect=False,
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        metadata = require_mapping(operation.get("request_metadata", {}), "request_metadata")
        if self.execution_mode != "apply":
            return AdapterOutcome(status=OutcomeStatus.NOT_RUN, evidence_class="NOT_RUN")
        deployment = metadata.get("deployment")
        revision = metadata.get("rollback_revision")
        if not isinstance(deployment, str) or not isinstance(revision, int) or revision < 1:
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "ROLLBACK_METADATA_MISSING"})
        response = self._kubectl("rollout", "undo", f"deployment/{deployment}", f"--to-revision={revision}")
        return self._outcome(
            response, action="compensate", evidence_class=getattr(self.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED"), side_effect=True,
        )


class KubernetesFailureAdapter:
    """Authorized, bounded failure experiments with explicit compensation."""

    adapter_id = "kubernetes-failure-experiments"
    adapter_version = "2.0.0"
    capability = "kubernetes"

    def __init__(self, kubernetes: KubernetesAdapter, *, allow_node_disruption: bool = False) -> None:
        self.kubernetes = kubernetes
        self.allow_node_disruption = allow_node_disruption

    @staticmethod
    def _scenario(value: Any) -> FailureScenario:
        scenario_id = require_string(value, "payload.scenario_id")
        scenario = next((item for item in FAILURE_SCENARIOS if item.scenario_id == scenario_id), None)
        if scenario is None:
            raise ContractError("FAILURE_SCENARIO_UNKNOWN", f"unknown failure scenario: {scenario_id}")
        return scenario

    @staticmethod
    def _resource_name(value: Any, field: str) -> str:
        name = require_string(value, field)
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?", name):
            raise ContractError("KUBERNETES_RESOURCE_INVALID", f"{field} is not a safe resource name")
        return name

    def execute(self, operation: Mapping[str, Any], payload: Mapping[str, Any]) -> AdapterOutcome:
        if operation.get("action") != "inject-failure":
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "FAILURE_ACTION_DENIED"})
        if self.kubernetes.execution_mode != "apply":
            return AdapterOutcome(status=OutcomeStatus.NOT_RUN, evidence_class="NOT_RUN")
        required = ("approved_isolated_environment", "experiment_owner", "cleanup_ttl_minutes", "cleanup_authorized")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise AuthorizationError("FAILURE_EXPERIMENT_DENIED", f"failure experiment metadata missing: {missing}")
        ttl = int(payload["cleanup_ttl_minutes"])
        if ttl < 1 or ttl > 240:
            raise ContractError("FAILURE_EXPERIMENT_TTL_INVALID", "cleanup TTL must be 1-240 minutes")
        scenario = self._scenario(payload.get("scenario_id"))
        evidence_class = getattr(self.kubernetes.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED")
        if scenario.scenario_id in {"pod-crash", "event-bus-rebalance", "lease-takeover"}:
            pod = self._resource_name(payload.get("pod"), "payload.pod")
            response = self.kubernetes._kubectl("delete", "pod", pod, "--wait=false")
            compensation = f"observe:{self._resource_name(payload.get('deployment'), 'payload.deployment')}"
        elif scenario.scenario_id == "node-drain":
            if not self.allow_node_disruption:
                return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "NODE_DISRUPTION_DENIED"})
            node = self._resource_name(payload.get("node"), "payload.node")
            response = self.kubernetes.runner.run(
                [
                    "kubectl", "--context", self.kubernetes.context, "drain", node,
                    "--ignore-daemonsets", "--delete-emptydir-data=false", "--timeout=180s",
                ],
                timeout_seconds=200,
            )
            compensation = f"uncordon:{node}"
        else:
            manifest = self.kubernetes._manifest(
                {"manifest_path": payload.get("failure_manifest_path")}
            )
            response = self.kubernetes._kubectl(
                "apply", "--server-side", "--field-manager=elmos-chaos", "-f", str(manifest)
            )
            compensation = f"delete-manifest:{manifest}"
        outcome = self.kubernetes._outcome(
            response, action=f"inject-{scenario.scenario_id}", evidence_class=evidence_class, side_effect=True
        )
        if outcome.status != OutcomeStatus.SUCCEEDED:
            return outcome
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED,
            result={
                "scenario_id": scenario.scenario_id,
                "steady_state_oracle": scenario.steady_state_oracle,
                "cleanup_ttl_minutes": ttl,
            },
            raw_evidence=outcome.raw_evidence,
            evidence_class=evidence_class,
            side_effect_performed=True,
            compensation_token=compensation,
        )

    def reconcile(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        result = operation.get("result") if isinstance(operation.get("result"), Mapping) else {}
        if not result.get("scenario_id"):
            return AdapterOutcome(status=OutcomeStatus.UNKNOWN, evidence_class="NOT_RUN")
        return AdapterOutcome(
            status=OutcomeStatus.SUCCEEDED,
            result=dict(result),
            raw_evidence={"experiment_record_present": True},
            evidence_class=getattr(self.kubernetes.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED"),
        )

    def compensate(self, operation: Mapping[str, Any]) -> AdapterOutcome:
        token = operation.get("compensation_token")
        if not isinstance(token, str):
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "CHAOS_COMPENSATION_MISSING"})
        if token.startswith("uncordon:"):
            node = token.split(":", 1)[1]
            response = self.kubernetes.runner.run(
                ["kubectl", "--context", self.kubernetes.context, "uncordon", node], timeout_seconds=120
            )
        elif token.startswith("delete-manifest:"):
            manifest = Path(token.split(":", 1)[1]).resolve()
            if not any(manifest == root or manifest.is_relative_to(root) for root in self.kubernetes.allowed_manifest_roots):
                raise AuthorizationError("MANIFEST_SCOPE_DENIED", "compensation manifest is outside approved roots")
            response = self.kubernetes._kubectl("delete", "-f", str(manifest), "--wait=true", "--timeout=180s")
        elif token.startswith("observe:"):
            deployment = token.split(":", 1)[1]
            response = self.kubernetes._kubectl(
                "rollout", "status", f"deployment/{deployment}", "--timeout=180s", timeout_seconds=200
            )
        else:
            return AdapterOutcome(status=OutcomeStatus.DENIED, error={"code": "CHAOS_COMPENSATION_INVALID"})
        return self.kubernetes._outcome(
            response,
            action="failure-compensation",
            evidence_class=getattr(self.kubernetes.runner, "evidence_class", "LOCAL_ENGINEERING_VALIDATED"),
            side_effect=True,
        )


def deployment_evidence_status(
    evidence: Mapping[str, Any],
    *,
    verifier: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    required = ("image_digest", "sbom_digest", "signature_digest", "runtime_events", "rollback_receipt", "cleanup_receipt")
    missing = [key for key in required if not evidence.get(key)]
    for key in ("image_digest", "sbom_digest", "signature_digest"):
        if not is_sha256_digest(evidence.get(key)):
            missing.append(f"{key}-invalid")
    health = require_mapping(evidence.get("health", {}), "evidence.health")
    if not all(health.get(name) is True for name in ("livez", "readyz", "metrics", "version")):
        missing.append("health")
    scenarios = evidence.get("failure_scenarios", [])
    required_scenarios = {item.scenario_id for item in FAILURE_SCENARIOS}
    passed_scenarios = {
        str(item.get("scenario_id"))
        for item in scenarios
        if isinstance(item, Mapping) and str(item.get("status", "")).upper() == "PASS"
    }
    if not required_scenarios.issubset(passed_scenarios):
        missing.append("failure-scenarios")
    independently_verified = (
        evidence.get("producer_id") != evidence.get("verifier_id")
        and evidence.get("signature_verified") is True
        and verifier is not None
        and verifier(evidence)
    )
    if not independently_verified:
        missing.append("independent-verification")
    return {
        "status": "PASS" if not missing else "BLOCKED",
        "missing": sorted(set(missing)),
        "failure_scenarios_required": sorted(required_scenarios),
        "failure_scenarios_passed": sorted(passed_scenarios),
        "independently_verified": independently_verified,
        "evidence_hash": digest(evidence),
        "external_evidence": "INDEPENDENTLY_VERIFIED" if not missing else "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
