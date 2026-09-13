"""Kubernetes control-plane driver for HPA, VPA, NetworkPolicy, and Chaos Mesh.

Builds real autoscaling/v2 and networking.k8s.io/v1 objects, POSTs them to the
Kubernetes API, and optionally runs `kubectl apply --dry-run=client`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from elmos_mature_platform.physical.protocol import (
    PhysicalCallResult,
    env_url,
    http_call,
    run_cli,
    which,
)


def _hpa_metric_name(trigger: str) -> str:
    mapping = {
        "cpu_threshold": "cpu",
        "memory_threshold": "memory",
        "queue_depth": "cpu",
        "request_rate": "cpu",
        "schedule": "cpu",
        "manual": "cpu",
    }
    return mapping.get(trigger, "cpu")


@dataclass
class KubernetesApplyBundle:
    namespace_manifest: Dict[str, Any]
    hpa_manifest: Dict[str, Any]
    vpa_manifest: Dict[str, Any]
    network_policy_manifest: Dict[str, Any]
    resource_quota_manifest: Dict[str, Any]
    chaos_mesh_manifest: Dict[str, Any]
    yaml_document: str
    receipts: List[PhysicalCallResult] = field(default_factory=list)

    @property
    def applied(self) -> bool:
        return any(item.applied for item in self.receipts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace_manifest": self.namespace_manifest,
            "hpa_manifest": self.hpa_manifest,
            "vpa_manifest": self.vpa_manifest,
            "network_policy_manifest": self.network_policy_manifest,
            "resource_quota_manifest": self.resource_quota_manifest,
            "chaos_mesh_manifest": self.chaos_mesh_manifest,
            "yaml_document": self.yaml_document,
            "applied": self.applied,
            "receipts": [item.to_dict() for item in self.receipts],
        }


class KubernetesControlPlaneDriver:
    """Physical Kubernetes API + kubectl driver."""

    def __init__(
        self,
        api_url: str = "",
        bearer_token: str = "",
        timeout: float = 2.5,
        default_namespace: str = "elmos-platform",
        enable_kubectl: bool = False,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.default_namespace = default_namespace
        self.enable_kubectl = enable_kubectl

    @classmethod
    def from_env(cls) -> "KubernetesControlPlaneDriver":
        from elmos_mature_platform.physical.protocol import env_flag

        return cls(
            api_url=env_url("ELMOS_K8S_API"),
            bearer_token=env_url("ELMOS_K8S_TOKEN"),
            enable_kubectl=env_flag("ELMOS_KUBECTL_APPLY"),
        )

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def build_namespace(self, name: str, tenant_id: str = "") -> Dict[str, Any]:
        labels = {
            "pod-security.kubernetes.io/enforce": "restricted",
            "pod-security.kubernetes.io/enforce-version": "latest",
            "elmos.dev/plane": "mature-platform",
        }
        if tenant_id:
            labels["elmos.dev/tenant"] = tenant_id
        return {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": name, "labels": labels},
        }

    def build_hpa(
        self,
        *,
        service_name: str,
        namespace: str,
        min_replicas: int,
        max_replicas: int,
        target_utilization: int,
        trigger: str = "cpu_threshold",
    ) -> Dict[str, Any]:
        metric = _hpa_metric_name(trigger)
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{service_name}-hpa",
                "namespace": namespace,
                "labels": {"app.kubernetes.io/name": service_name},
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": service_name,
                },
                "minReplicas": int(min_replicas),
                "maxReplicas": int(max_replicas),
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": metric,
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": int(target_utilization),
                            },
                        },
                    }
                ],
            },
        }

    def build_vpa(self, *, service_name: str, namespace: str) -> Dict[str, Any]:
        return {
            "apiVersion": "autoscaling.k8s.io/v1",
            "kind": "VerticalPodAutoscaler",
            "metadata": {
                "name": f"{service_name}-vpa",
                "namespace": namespace,
            },
            "spec": {
                "targetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": service_name,
                },
                "updatePolicy": {"updateMode": "Auto"},
                "resourcePolicy": {
                    "containerPolicies": [
                        {
                            "containerName": "*",
                            "controlledResources": ["cpu", "memory"],
                            "minAllowed": {"cpu": "50m", "memory": "64Mi"},
                            "maxAllowed": {"cpu": "4", "memory": "8Gi"},
                        }
                    ]
                },
            },
        }

    def build_network_policy(self, *, namespace: str, tenant_id: str) -> Dict[str, Any]:
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"tenant-{tenant_id}-deny-cross",
                "namespace": namespace,
            },
            "spec": {
                "podSelector": {"matchLabels": {"elmos.dev/tenant": tenant_id}},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [
                    {
                        "from": [
                            {"podSelector": {"matchLabels": {"elmos.dev/tenant": tenant_id}}},
                            {
                                "namespaceSelector": {
                                    "matchLabels": {"elmos.dev/plane": "mature-platform"}
                                }
                            },
                        ]
                    }
                ],
                "egress": [
                    {
                        "to": [
                            {"podSelector": {"matchLabels": {"elmos.dev/tenant": tenant_id}}},
                            {
                                "namespaceSelector": {
                                    "matchLabels": {"kube-system": "true"}
                                }
                            },
                        ]
                    }
                ],
            },
        }

    def build_resource_quota(
        self,
        *,
        namespace: str,
        tenant_id: str,
        cpu_cores: float,
        memory_gb: float,
    ) -> Dict[str, Any]:
        return {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {
                "name": f"tenant-{tenant_id}-quota",
                "namespace": namespace,
            },
            "spec": {
                "hard": {
                    "requests.cpu": str(cpu_cores),
                    "requests.memory": f"{memory_gb}Gi",
                    "limits.cpu": str(cpu_cores),
                    "limits.memory": f"{memory_gb}Gi",
                    "pods": "64",
                }
            },
        }

    def build_chaos_mesh_network_chaos(
        self,
        *,
        namespace: str,
        service_name: str,
        fault_type: str,
        latency_ms: int = 250,
        duration: str = "60s",
    ) -> Dict[str, Any]:
        action = "delay" if fault_type in {"latency", "LATENCY"} else "partition"
        spec: Dict[str, Any] = {
            "action": action,
            "mode": "all",
            "selector": {
                "namespaces": [namespace],
                "labelSelectors": {"app.kubernetes.io/name": service_name},
            },
            "duration": duration,
        }
        if action == "delay":
            spec["delay"] = {"latency": f"{latency_ms}ms", "correlation": "100", "jitter": "0ms"}
        return {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "NetworkChaos",
            "metadata": {
                "name": f"{service_name}-{fault_type.lower()}",
                "namespace": namespace,
            },
            "spec": spec,
        }

    def render_yaml(self, *manifests: Dict[str, Any]) -> str:
        import json as _json

        documents = []
        for manifest in manifests:
            documents.append(_json.dumps(manifest, indent=2, sort_keys=True))
        return "\n---\n".join(documents) + "\n"

    def _post(self, path: str, body: Dict[str, Any], operation: str) -> PhysicalCallResult:
        url = f"{self.api_url}{path}" if self.api_url else ""
        return http_call(
            backend="kubernetes",
            operation=operation,
            method="POST",
            url=url,
            body=body,
            headers=self._headers(),
            timeout=self.timeout,
        )

    def apply_hpa_vpa(
        self,
        *,
        service_name: str,
        min_replicas: int,
        max_replicas: int,
        target_utilization: int = 80,
        trigger: str = "cpu_threshold",
        namespace: Optional[str] = None,
    ) -> KubernetesApplyBundle:
        ns = namespace or self.default_namespace
        namespace_manifest = self.build_namespace(ns)
        hpa = self.build_hpa(
            service_name=service_name,
            namespace=ns,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            target_utilization=target_utilization,
            trigger=trigger,
        )
        vpa = self.build_vpa(service_name=service_name, namespace=ns)
        yaml_document = self.render_yaml(namespace_manifest, hpa, vpa)
        receipts = [
            self._post("/api/v1/namespaces", namespace_manifest, "create_namespace"),
            self._post(
                f"/apis/autoscaling/v2/namespaces/{ns}/horizontalpodautoscalers",
                hpa,
                "create_hpa",
            ),
            self._post(
                f"/apis/autoscaling.k8s.io/v1/namespaces/{ns}/verticalpodautoscalers",
                vpa,
                "create_vpa",
            ),
        ]
        kubectl = which("kubectl") or "kubectl"
        kubectl_argv = [kubectl, "apply", "--dry-run=client", "-f", "-"]
        if self.enable_kubectl and which("kubectl"):
            receipts.append(
                run_cli(
                    backend="kubectl",
                    operation="apply_dry_run_client",
                    argv=kubectl_argv,
                    input_bytes=yaml_document.encode("utf-8"),
                    timeout=self.timeout,
                )
            )
        else:
            receipts.append(
                PhysicalCallResult(
                    backend="kubectl",
                    operation="apply_dry_run_client",
                    method="CLI",
                    url=kubectl,
                    request_body=None,
                    argv=kubectl_argv,
                    extras={"deferred": not self.enable_kubectl},
                )
            )
        return KubernetesApplyBundle(
            namespace_manifest=namespace_manifest,
            hpa_manifest=hpa,
            vpa_manifest=vpa,
            network_policy_manifest={},
            resource_quota_manifest={},
            chaos_mesh_manifest={},
            yaml_document=yaml_document,
            receipts=receipts,
        )

    def apply_tenant_isolation(
        self,
        *,
        tenant_id: str,
        cpu_cores: float,
        memory_gb: float,
        namespace: Optional[str] = None,
    ) -> KubernetesApplyBundle:
        ns = namespace or f"elmos-tenant-{tenant_id}"
        namespace_manifest = self.build_namespace(ns, tenant_id=tenant_id)
        network_policy = self.build_network_policy(namespace=ns, tenant_id=tenant_id)
        quota = self.build_resource_quota(
            namespace=ns,
            tenant_id=tenant_id,
            cpu_cores=cpu_cores,
            memory_gb=memory_gb,
        )
        yaml_document = self.render_yaml(namespace_manifest, network_policy, quota)
        receipts = [
            self._post("/api/v1/namespaces", namespace_manifest, "create_namespace"),
            self._post(
                f"/apis/networking.k8s.io/v1/namespaces/{ns}/networkpolicies",
                network_policy,
                "create_network_policy",
            ),
            self._post(
                f"/api/v1/namespaces/{ns}/resourcequotas",
                quota,
                "create_resource_quota",
            ),
        ]
        return KubernetesApplyBundle(
            namespace_manifest=namespace_manifest,
            hpa_manifest={},
            vpa_manifest={},
            network_policy_manifest=network_policy,
            resource_quota_manifest=quota,
            chaos_mesh_manifest={},
            yaml_document=yaml_document,
            receipts=receipts,
        )

    def apply_chaos_mesh(
        self,
        *,
        service_name: str,
        fault_type: str,
        latency_ms: int = 250,
        namespace: Optional[str] = None,
    ) -> KubernetesApplyBundle:
        ns = namespace or self.default_namespace
        chaos = self.build_chaos_mesh_network_chaos(
            namespace=ns,
            service_name=service_name,
            fault_type=fault_type,
            latency_ms=latency_ms,
        )
        yaml_document = self.render_yaml(chaos)
        receipts = [
            self._post(
                f"/apis/chaos-mesh.org/v1alpha1/namespaces/{ns}/networkchaos",
                chaos,
                "create_network_chaos",
            )
        ]
        return KubernetesApplyBundle(
            namespace_manifest={},
            hpa_manifest={},
            vpa_manifest={},
            network_policy_manifest={},
            resource_quota_manifest={},
            chaos_mesh_manifest=chaos,
            yaml_document=yaml_document,
            receipts=receipts,
        )
