"""Exact provider-free semantic handlers for the Foundry safety core.

These handlers implement bounded, deterministic control-plane behavior for an
explicit allowlist of atomic Skills.  They never infer implementation from a
Skill name, call a provider, train a model, mutate a repository, or claim
independent evidence.  Every other atomic Skill remains adapter-required.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
import re
from typing import Any, Callable, Protocol, cast

from .adapters import AdapterBinding, AdapterRegistry, EffectClass
from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .store import FoundryStore, StoreError


LOCAL_SEMANTIC_VERSION = "1.0.0"

LOCAL_SEMANTIC_SKILLS: frozenset[str] = frozenset(
    {
        "artifact-identity-and-hashing",
        "typed-skill-contract",
        "package-conformance-validator",
        "capability-dependency-graph",
        "hierarchical-skill-registry",
        "progressive-skill-disclosure",
        "skill-activation-router",
        "skill-dependency-resolver",
        "environment-owned-authority",
        "least-privilege-tool-authorization",
        "workspace-attachment-ownership-fencing",
        "tamper-evident-audit-log",
        "artifact-normalization",
        "provenance-and-lineage-capture",
        "sensitive-data-and-secret-detection",
        "experience-episode-capture",
        "tenant-memory-isolation-and-replay",
        "dataset-contract-and-schema",
        "dataset-quarantine-management",
        "task-canonicalization-and-normalization",
        "evidence-aggregation-and-completeness",
        "uncertainty-and-abstention-evaluation",
        "health-warmup-and-readiness",
        "complexity-risk-cost-latency-routing",
        "model-version-pinning-determinism",
        "tool-call-schema-and-policy-check",
    }
)


class CatalogView(Protocol):
    content_sha256: str
    discovery: Mapping[str, Any]
    atomic_skills: Mapping[str, Mapping[str, Any]]
    meta_skills: Mapping[str, Mapping[str, Any]]


LocalHandler = Callable[[str, Mapping[str, Any], TenantScope, str], Mapping[str, Any]]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_mapping(value: Any, label: str, keys: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != keys:
        raise ValueError(
            f"{label} keys are not exact; missing={sorted(keys - set(result))}, "
            f"extra={sorted(set(result) - keys)}"
        )
    return result


def _sequence(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 10_000,
) -> Sequence[Any]:
    if minimum < 0 or maximum < minimum:
        raise ValueError("sequence bounds are invalid")
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not minimum <= len(value) <= maximum
    ):
        raise ValueError(f"{label} must contain {minimum}..{maximum} items")
    return value


def _text(value: Any, label: str, *, maximum: int = 16_384) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{label} must be non-empty and bounded")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result != result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result


def _inputs(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(payload.get("inputs"), "inputs")


def _response(outputs: Mapping[str, Any], *, status: str = "SUCCEEDED") -> Mapping[str, Any]:
    return {
        "status": status,
        "outputs": outputs,
        "evidence_state": "COLLECTED_SELF_ATTESTED" if status == "SUCCEEDED" else "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def _topological_order(graph: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    nodes = set(graph)
    unresolved = sorted(
        (node, dependency)
        for node, dependencies in graph.items()
        for dependency in dependencies
        if dependency not in nodes
    )
    if unresolved:
        raise ValueError(f"dependency graph has unresolved edges: {unresolved[:8]}")
    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, dependencies in graph.items():
        if node in dependencies:
            raise ValueError(f"dependency graph has a self edge: {node}")
        for dependency in dependencies:
            indegree[node] += 1
            outgoing[dependency].append(node)
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for successor in sorted(outgoing[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(ordered) != len(nodes):
        raise ValueError("dependency graph contains a cycle")
    return tuple(ordered)


_SECRET_KEY = re.compile(
    r"(?i)(?:^|[-_])(authorization|cookie|credential|password|private[-_]?key|secret|token|api[-_]?key)(?:$|[-_])"
)
_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|((?:password|api[-_]?key|secret|token)\s*[:=]\s*)[^\s,;]+"
)


def _redact(value: Any, path: str = "$") -> tuple[Any, list[Mapping[str, str]]]:
    findings: list[Mapping[str, str]] = []
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            if not isinstance(raw_key, str):
                raise ValueError("sensitive-data input keys must be strings")
            child_path = f"{path}.{raw_key}"
            if _SECRET_KEY.search(raw_key):
                result[raw_key] = "[REDACTED]"
                findings.append({"path": child_path, "kind": "sensitive-key"})
            else:
                result[raw_key], nested = _redact(child, child_path)
                findings.extend(nested)
        return result, findings
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        redacted: list[Any] = []
        for index, child in enumerate(value):
            normalized, nested = _redact(child, f"{path}[{index}]")
            redacted.append(normalized)
            findings.extend(nested)
        return redacted, findings
    if isinstance(value, str):
        replaced, count = _SECRET_VALUE.subn(
            lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]",
            value,
        )
        if count:
            findings.append({"path": path, "kind": "sensitive-value-pattern"})
        return replaced, findings
    return value, findings


def _schema_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_simple_schema(value: Any, schema: Mapping[str, Any], label: str) -> None:
    allowed = {"type", "required", "properties", "items", "additionalProperties", "enum"}
    if set(schema) - allowed:
        raise ValueError(f"{label} contains unsupported Schema keywords")
    expected_type = schema.get("type")
    if not isinstance(expected_type, str) or not _schema_type(value, expected_type):
        raise ValueError(f"{label} type mismatch")
    enum = schema.get("enum")
    if enum is not None:
        choices = _sequence(enum, f"{label}.enum", maximum=256)
        if value not in choices:
            raise ValueError(f"{label} is outside its enum")
    if expected_type == "object":
        obj = _mapping(value, label)
        properties = _mapping(schema.get("properties", {}), f"{label}.properties")
        required_raw = schema.get("required", [])
        if not isinstance(required_raw, list) or any(not isinstance(item, str) for item in required_raw):
            raise ValueError(f"{label}.required must be a string array")
        missing = sorted(set(required_raw) - set(obj))
        if missing:
            raise ValueError(f"{label} missing required properties: {missing}")
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{label} must set additionalProperties=false")
        extra = sorted(set(obj) - set(properties))
        if extra:
            raise ValueError(f"{label} has undeclared properties: {extra}")
        for key, child in obj.items():
            child_schema = _mapping(properties[key], f"{label}.properties.{key}")
            _validate_simple_schema(child, child_schema, f"{label}.{key}")
    elif expected_type == "array":
        item_schema = _mapping(schema.get("items"), f"{label}.items")
        for index, child in enumerate(cast(list[Any], value)):
            _validate_simple_schema(child, item_schema, f"{label}[{index}]")


class LocalSemanticRuntime:
    """Register and execute the exact local semantic allowlist."""

    def __init__(self, catalog: CatalogView, *, store: FoundryStore | None = None) -> None:
        self.catalog = catalog
        self.store = store
        handlers: dict[str, LocalHandler] = {
            "artifact-identity-and-hashing": self.artifact_identity_and_hashing,
            "typed-skill-contract": self.typed_skill_contract,
            "package-conformance-validator": self.package_conformance_validator,
            "capability-dependency-graph": self.capability_dependency_graph,
            "hierarchical-skill-registry": self.hierarchical_skill_registry,
            "progressive-skill-disclosure": self.progressive_skill_disclosure,
            "skill-activation-router": self.skill_activation_router,
            "skill-dependency-resolver": self.skill_dependency_resolver,
            "environment-owned-authority": self.environment_owned_authority,
            "least-privilege-tool-authorization": self.least_privilege_tool_authorization,
            "workspace-attachment-ownership-fencing": self.workspace_attachment_ownership_fencing,
            "tamper-evident-audit-log": self.tamper_evident_audit_log,
            "artifact-normalization": self.artifact_normalization,
            "provenance-and-lineage-capture": self.provenance_and_lineage_capture,
            "sensitive-data-and-secret-detection": self.sensitive_data_and_secret_detection,
            "experience-episode-capture": self.experience_episode_capture,
            "tenant-memory-isolation-and-replay": self.tenant_memory_isolation_and_replay,
            "dataset-contract-and-schema": self.dataset_contract_and_schema,
            "dataset-quarantine-management": self.dataset_quarantine_management,
            "task-canonicalization-and-normalization": self.task_canonicalization_and_normalization,
            "evidence-aggregation-and-completeness": self.evidence_aggregation_and_completeness,
            "uncertainty-and-abstention-evaluation": self.uncertainty_and_abstention_evaluation,
            "health-warmup-and-readiness": self.health_warmup_and_readiness,
            "complexity-risk-cost-latency-routing": self.complexity_risk_cost_latency_routing,
            "model-version-pinning-determinism": self.model_version_pinning_determinism,
            "tool-call-schema-and-policy-check": self.tool_call_schema_and_policy_check,
        }
        if set(handlers) != LOCAL_SEMANTIC_SKILLS:
            raise RuntimeError("local semantic handler registry is not exact")
        missing = sorted(LOCAL_SEMANTIC_SKILLS - set(catalog.atomic_skills))
        if missing:
            raise RuntimeError(f"local semantic Skills are absent from the exact catalog: {missing}")
        self.handlers = handlers

    def register(self, registry: AdapterRegistry) -> AdapterRegistry:
        for skill_name in sorted(self.handlers):
            contract = {
                "schema_version": "elmos.foundry.local-semantic-binding.v1",
                "skill_name": skill_name,
                "version": LOCAL_SEMANTIC_VERSION,
                "catalog_digest": self.catalog.content_sha256,
                "effect_class": EffectClass.LOCAL_DETERMINISTIC.value,
            }
            registry.register(
                AdapterBinding(
                    adapter_id=f"local.{skill_name}",
                    version=LOCAL_SEMANTIC_VERSION,
                    digest=canonical_digest(contract).removeprefix("sha256:"),
                    exact_skills=(skill_name,),
                    effect_class=EffectClass.LOCAL_DETERMINISTIC,
                    metadata={
                        "authority": "repository-owned-exact-handler",
                        "catalog_digest": self.catalog.content_sha256,
                    },
                ),
                self.handlers[skill_name],
            )
        return registry

    @staticmethod
    def _foundation_outputs(
        skill_name: str, values: Mapping[str, Any], primary: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        identity = canonical_digest(
            {
                "schema_version": "elmos.foundry.local-foundation-result.v1",
                "skill_name": skill_name,
                "inputs": values,
                "primary": primary,
            }
        )
        architecture = _mapping(values["architecture decision"], "architecture decision")
        policy = _mapping(values["policy profile"], "policy profile")
        runtime = _mapping(values["runtime capability inventory"], "runtime capability inventory")
        return {
            "typed contract": primary,
            "compatibility declaration": {
                "runtime_version": runtime.get("runtime_version", "UNBOUND"),
                "architecture_digest": canonical_digest(architecture),
                "exact_native_tuple": "UNBOUND",
            },
            "evidence obligation": {
                "required_gates": policy.get("required_gates", []),
                "independent_verification": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
            "release identity": {
                "content_digest": identity,
                "release_status": "LOCAL_EXECUTED_SELF_ATTESTED",
                "external_evidence_status": "NOT_RUN",
            },
        }

    def artifact_identity_and_hashing(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        artifact = {
            "schema_version": "elmos.foundry.artifact-identity.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "invocation_id": invocation_id,
            "content_digest": canonical_digest(values),
            "canonicalization": "bounded-canonical-json-v1",
        }
        return _response(self._foundation_outputs(skill_name, values, artifact))

    def typed_skill_contract(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        requirement = _exact_mapping(
            values["business requirement"],
            "business requirement",
            {"skill_name", "purpose", "acceptance"},
        )
        architecture = _exact_mapping(
            values["architecture decision"],
            "architecture decision",
            {"owner", "version", "rollback"},
        )
        policy = _exact_mapping(
            values["policy profile"],
            "policy profile",
            {"allowed_tools", "required_gates", "side_effects"},
        )
        runtime = _exact_mapping(
            values["runtime capability inventory"],
            "runtime capability inventory",
            {"runtime_version", "capabilities"},
        )
        contract = {
            "schema_version": "elmos.foundry.typed-skill-contract.v1",
            "skill_name": require_identifier(requirement["skill_name"], "skill_name"),
            "purpose": _text(requirement["purpose"], "purpose"),
            "acceptance": canonical_value(requirement["acceptance"]),
            "owner": require_identifier(architecture["owner"], "owner"),
            "version": require_identifier(architecture["version"], "version"),
            "rollback": canonical_value(architecture["rollback"]),
            "allowed_tools": sorted(
                require_identifier(item, "allowed_tool")
                for item in _sequence(policy["allowed_tools"], "allowed_tools", maximum=256)
            ),
            "required_gates": sorted(
                require_identifier(item, "required_gate")
                for item in _sequence(policy["required_gates"], "required_gates", maximum=256)
            ),
            "side_effects": canonical_value(policy["side_effects"]),
            "runtime_version": _text(runtime["runtime_version"], "runtime_version"),
            "capabilities": sorted(
                require_identifier(item, "capability")
                for item in _sequence(runtime["capabilities"], "capabilities", maximum=512)
            ),
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
        }
        return _response(self._foundation_outputs(skill_name, values, contract))

    def package_conformance_validator(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        package = _exact_mapping(
            values["business requirement"],
            "business requirement",
            {"package_name", "version", "skills", "owner", "rollback"},
        )
        skills = _sequence(package["skills"], "package.skills", maximum=10_000)
        names = [require_identifier(item, "package.skill") for item in skills]
        violations: list[str] = []
        if len(names) != len(set(names)):
            violations.append("duplicate-skill-identity")
        if package["version"] != "3.0.0":
            violations.append("package-version-not-exact")
        if not package["rollback"]:
            violations.append("rollback-missing")
        conformance = {
            "schema_version": "elmos.foundry.package-conformance.v1",
            "package_name": require_identifier(package["package_name"], "package_name"),
            "version": _text(package["version"], "package.version"),
            "owner": require_identifier(package["owner"], "package.owner"),
            "skill_count": len(names),
            "skill_set_digest": canonical_digest(sorted(names)),
            "violations": violations,
            "decision": "PASS_LOCAL_STRUCTURE" if not violations else "FAIL",
        }
        return _response(self._foundation_outputs(skill_name, values, conformance))

    def capability_dependency_graph(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        inventory = _exact_mapping(
            values["runtime capability inventory"],
            "runtime capability inventory",
            {"nodes"},
        )
        graph: dict[str, tuple[str, ...]] = {}
        for index, raw in enumerate(_sequence(inventory["nodes"], "nodes")):
            node = _exact_mapping(raw, f"nodes[{index}]", {"id", "dependencies"})
            node_id = require_identifier(node["id"], f"nodes[{index}].id")
            if node_id in graph:
                raise ValueError(f"duplicate graph node: {node_id}")
            graph[node_id] = tuple(
                require_identifier(item, "dependency")
                for item in _sequence(node["dependencies"], "dependencies")
            ) if node["dependencies"] else ()
        ordered = _topological_order(graph)
        primary = {
            "schema_version": "elmos.foundry.capability-dag.v1",
            "nodes": [{"id": node, "dependencies": list(graph[node])} for node in sorted(graph)],
            "topological_order": list(ordered),
            "edge_count": sum(len(item) for item in graph.values()),
            "graph_digest": canonical_digest(graph),
        }
        return _response(self._foundation_outputs(skill_name, values, primary))

    def hierarchical_skill_registry(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        packs: dict[str, list[str]] = defaultdict(list)
        for name, record in self.catalog.atomic_skills.items():
            packs[str(record["pack"])].append(name)
        registry = {
            "schema_version": "elmos.foundry.hierarchical-registry.v1",
            "catalog_digest": self.catalog.content_sha256,
            "atomic_skill_count": len(self.catalog.atomic_skills),
            "meta_skill_count": len(self.catalog.meta_skills),
            "packs": [
                {"pack": pack, "skills": sorted(names), "count": len(names)}
                for pack, names in sorted(packs.items())
            ],
        }
        return _response(self._skill_runtime_outputs(skill_name, values, registry))

    def progressive_skill_disclosure(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        task = _mapping(values["task contract"], "task contract")
        pack = require_identifier(task.get("pack"), "task contract.pack")
        limit_raw = task.get("candidate_limit", self.catalog.discovery["candidate_limit"])
        if isinstance(limit_raw, bool) or not isinstance(limit_raw, int) or not 1 <= limit_raw <= 16:
            raise ValueError("candidate_limit must be an integer in [1,16]")
        candidates = sorted(
            name
            for name, record in self.catalog.atomic_skills.items()
            if record["pack"] == pack
        )
        if not candidates:
            raise ValueError("task contract references an unknown pack")
        primary = {
            "pack": pack,
            "exposed": candidates[:limit_raw],
            "candidate_count": min(len(candidates), limit_raw),
            "total_pack_skills": len(candidates),
            "startup_exposure": "meta-only",
        }
        return _response(self._skill_runtime_outputs(skill_name, values, primary))

    def skill_activation_router(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        task = _mapping(values["task contract"], "task contract")
        pack = require_identifier(task.get("pack"), "task contract.pack")
        query = _text(task.get("query"), "task contract.query")
        tokens = tuple(sorted(set(re.findall(r"[a-z0-9]+", query.casefold()))))
        candidates = [
            name
            for name, record in sorted(self.catalog.atomic_skills.items())
            if record["pack"] == pack
        ]
        scored = sorted(
            (
                (-sum(token in name for token in tokens), name)
                for name in candidates
                if any(token in name for token in tokens)
            )
        )
        activated = [name for _, name in scored[:8]]
        primary = {
            "pack": pack,
            "query_digest": canonical_digest(query),
            "activated": activated,
            "activation_count": len(activated),
            "decision": "ROUTED" if activated else "ABSTAIN",
        }
        return _response(self._skill_runtime_outputs(skill_name, values, primary))

    def skill_dependency_resolver(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        semantic_ir = _mapping(values["semantic IR"], "semantic IR")
        requested = tuple(
            require_identifier(item, "requested_skill")
            for item in _sequence(semantic_ir.get("requested_skills"), "requested_skills")
        )
        unknown = sorted(set(requested) - set(self.catalog.atomic_skills))
        if unknown:
            raise ValueError(f"unknown requested Skills: {unknown}")
        closure: set[str] = set()

        def visit(name: str) -> None:
            if name in closure:
                return
            closure.add(name)
            for dependency in self.catalog.atomic_skills[name]["dependencies"]:
                visit(str(dependency))

        for name in requested:
            visit(name)
        graph = {
            name: tuple(
                str(item)
                for item in self.catalog.atomic_skills[name]["dependencies"]
                if item in closure
            )
            for name in closure
        }
        primary = {
            "requested": sorted(requested),
            "closure": list(_topological_order(graph)),
            "dependency_count": len(closure) - len(set(requested)),
            "graph_digest": canonical_digest(graph),
        }
        return _response(self._skill_runtime_outputs(skill_name, values, primary))

    def _skill_runtime_outputs(
        self, skill_name: str, values: Mapping[str, Any], primary: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {
            "skill package": primary,
            "activation rules": {
                "meta_only_startup": True,
                "candidate_limit": self.catalog.discovery["candidate_limit"],
                "activation_limit": self.catalog.discovery["activation_limit"],
            },
            "workflow DAG": {
                "skill": skill_name,
                "dependencies": list(self.catalog.atomic_skills[skill_name]["dependencies"]),
            },
            "evidence bundle": {
                "input_digest": canonical_digest(values),
                "catalog_digest": self.catalog.content_sha256,
                "evidence_state": "COLLECTED_SELF_ATTESTED",
                "certification_status": "NOT_CERTIFIED",
            },
        }

    @staticmethod
    def _security_outputs(
        skill_name: str, values: Mapping[str, Any], decision: str, reasons: Sequence[str]
    ) -> Mapping[str, Any]:
        event = {
            "event_type": f"{skill_name}.evaluated",
            "decision": decision,
            "reason_codes": list(reasons),
            "request_digest": canonical_digest(values),
        }
        return {
            "policy decision": {"decision": decision, "reason_codes": list(reasons)},
            "audit event": {**event, "event_digest": canonical_digest(event)},
            "security evidence": {
                "evidence_state": "COLLECTED_SELF_ATTESTED",
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
            "incident action": {
                "required": decision != "ALLOW",
                "action": "DENY_AND_AUDIT" if decision != "ALLOW" else "NONE",
            },
        }

    def environment_owned_authority(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        identity = _mapping(values["identity"], "identity")
        request = _mapping(values["request context"], "request context")
        reasons: list[str] = []
        expected = {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "actor_id": scope.actor_id,
            "environment_id": scope.environment_id,
        }
        for key, expected_value in expected.items():
            source = identity if key in {"tenant_id", "project_id", "actor_id"} else request
            if source.get(key) != expected_value:
                reasons.append(f"{key}-mismatch")
        if request.get("authority_source") != "host":
            reasons.append("authority-not-host-owned")
        if request.get("authorized") is not True:
            reasons.append("request-not-authorized")
        decision = "DENY"
        if not reasons:
            reasons.append("trusted-authorization-receipt-verifier-unbound")
            decision = "EVIDENCE_PENDING"
        return _response(self._security_outputs(skill_name, values, decision, reasons))

    def least_privilege_tool_authorization(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        request = _mapping(values["request context"], "request context")
        policy = _mapping(values["policy profile"], "policy profile")
        requested = {
            require_identifier(item, "requested_tool")
            for item in _sequence(
                request.get("requested_tools"),
                "requested_tools",
                minimum=0,
                maximum=256,
            )
        }
        leased_raw = policy.get("leased_tools")
        leased = {
            require_identifier(item, "leased_tool")
            for item in _sequence(
                leased_raw, "leased_tools", minimum=0, maximum=256
            )
        }
        reasons = [f"unleased-tool:{item}" for item in sorted(requested - leased)]
        if policy.get("default_deny") is not True:
            reasons.append("policy-not-default-deny")
        decision = "DENY"
        if not reasons:
            reasons.append("trusted-tool-lease-verifier-unbound")
            decision = "EVIDENCE_PENDING"
        return _response(self._security_outputs(skill_name, values, decision, reasons))

    def workspace_attachment_ownership_fencing(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        provenance = _mapping(values["artifact provenance"], "artifact provenance")
        reasons: list[str] = []
        for field, expected in {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "workspace_digest": scope.workspace_digest,
            "revision_set_id": scope.revision_set_id,
        }.items():
            if provenance.get(field) != expected:
                reasons.append(f"{field}-mismatch")
        decision = "DENY"
        if not reasons:
            reasons.append("trusted-provenance-receipt-verifier-unbound")
            decision = "EVIDENCE_PENDING"
        return _response(self._security_outputs(skill_name, values, decision, reasons))

    def tamper_evident_audit_log(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        if self.store is None:
            outputs = self._security_outputs(
                skill_name, values, "DENY", ("durable-audit-store-unavailable",)
            )
            return _response(outputs, status="FAILED")
        request = _mapping(values["request context"], "request context")
        aggregate_id = require_identifier(request.get("aggregate_id"), "aggregate_id")
        payload_digest = canonical_digest(values)
        event_id = "evt-" + canonical_digest(
            {
                "skill": skill_name,
                "invocation_id": invocation_id,
                "payload_digest": payload_digest,
            }
        ).removeprefix("sha256:")[:32]
        try:
            events = self.store.list_events(scope, aggregate_id)
            existing = next((event for event in events if event.event_id == event_id), None)
            if existing is None:
                event = self.store.append_event(
                    scope,
                    aggregate_id,
                    "security-audit",
                    {"request_digest": payload_digest, "decision": "RECORDED"},
                    event_id=event_id,
                )
            else:
                if existing.payload.get("request_digest") != payload_digest:
                    raise ValueError("idempotent audit event payload conflict")
                event = existing
            intact = self.store.verify_event_chain(scope, aggregate_id)
        except StoreError as exc:
            raise ValueError("durable audit operation failed closed") from exc
        decision = "ALLOW" if intact else "DENY"
        outputs = dict(self._security_outputs(skill_name, values, decision, ()))
        outputs["audit event"] = {
            "event_id": event.event_id,
            "aggregate_id": event.aggregate_id,
            "sequence": event.sequence,
            "event_digest": event.event_digest,
            "chain_intact": intact,
        }
        return _response(outputs)

    @staticmethod
    def _knowledge_outputs(
        values: Mapping[str, Any],
        normalized: Any,
        *,
        findings: Sequence[Mapping[str, str]] = (),
        secret_scan_status: str = "NOT_RUN",
    ) -> Mapping[str, Any]:
        sources = sorted(values)
        provenance = [
            {"source_type": name, "content_digest": canonical_digest(values[name])}
            for name in sources
        ]
        return {
            "normalized artifact": {
                "content": normalized,
                "content_digest": canonical_digest(normalized),
                "instructions_authoritative": False,
                "secret_findings": list(findings),
                "secret_scan_coverage": secret_scan_status,
            },
            "source provenance": {
                "sources": provenance,
                "lineage_digest": canonical_digest(provenance),
            },
            "rights classification": {
                "status": "SOURCE_DECLARATION_REQUIRED",
                "global_training_eligible": False,
            },
            "freshness status": {
                "status": "SOURCE_TIMESTAMP_UNBOUND",
                "external_verification": "NOT_RUN",
            },
        }

    def artifact_normalization(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        normalized = canonical_value(values)
        return _response(self._knowledge_outputs(values, normalized))

    def provenance_and_lineage_capture(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        lineage = {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "workspace_digest": scope.workspace_digest,
            "revision_set_id": scope.revision_set_id,
            "sources": [
                {"kind": key, "digest": canonical_digest(value)}
                for key, value in sorted(values.items())
            ],
        }
        return _response(self._knowledge_outputs(values, lineage))

    def sensitive_data_and_secret_detection(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        redacted, findings = _redact(values)
        return _response(
            self._knowledge_outputs(
                values,
                redacted,
                findings=findings,
                secret_scan_status="LOCAL_HEURISTIC_SELF_ATTESTED",
            )
        )

    @staticmethod
    def _memory_outputs(
        episode: Mapping[str, Any], record: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        outcome = episode.get("outcome", {})
        return {
            "experience episode": episode,
            "memory record": record,
            "failure signature": {
                "digest": canonical_digest({"outcome": outcome, "episode": episode.get("episode_id")}),
                "classification": "LOCAL_DETERMINISTIC",
            },
            "repair pattern": {
                "status": "NOT_INFERRED",
                "reason": "a captured trajectory is evidence, not an automatically approved repair",
            },
        }

    def experience_episode_capture(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        if self.store is None:
            return _response(
                self._memory_outputs(
                    {"status": "NOT_RUN"},
                    {"status": "DURABLE_STORE_REQUIRED"},
                ),
                status="FAILED",
            )
        trace = _mapping(values["agent trace"], "agent trace")
        tests = _mapping(values["test result"], "test result")
        sanitized, findings = _redact(
            {
                "trajectory": trace.get("trajectory"),
                "tool_event": values["tool event"],
                "patch": values["patch"],
                "human_feedback": values["human feedback"],
                "outcome": tests.get("outcome"),
            }
        )
        task_type = require_identifier(trace.get("task_type"), "agent trace.task_type")
        task_goal = _text(trace.get("task_goal"), "agent trace.task_goal")
        reward = _number(tests.get("reward_score"), "test result.reward_score")
        if not 0 <= reward <= 1:
            raise ValueError("reward_score must be in [0,1]")
        episode_body = {
            "schema_version": "elmos.foundry.experience-episode.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "task_type": task_type,
            "task_goal_digest": canonical_digest(task_goal),
            "sanitized": sanitized,
            "redaction_findings": findings,
            "reward_score": reward,
            "independent_verification": "NOT_RUN",
        }
        episode_id = "episode-" + canonical_digest(episode_body).removeprefix("sha256:")[:32]
        aggregate_id = "memory-" + canonical_digest(
            {"tenant": scope.tenant_id, "project": scope.project_id, "task_type": task_type}
        ).removeprefix("sha256:")[:24]
        event_id = "evt-" + canonical_digest(
            {"episode_id": episode_id, "invocation_id": invocation_id}
        ).removeprefix("sha256:")[:32]
        episode = {**episode_body, "episode_id": episode_id, "outcome": tests.get("outcome", {})}
        try:
            events = self.store.list_events(scope, aggregate_id)
            existing = next((event for event in events if event.event_id == event_id), None)
            if existing is None:
                event = self.store.append_event(
                    scope, aggregate_id, "experience-captured", episode, event_id=event_id
                )
            else:
                if existing.payload != canonical_value(episode):
                    raise ValueError("experience idempotency conflict")
                event = existing
            intact = self.store.verify_event_chain(scope, aggregate_id)
        except StoreError as exc:
            raise ValueError("experience persistence failed closed") from exc
        record = {
            "aggregate_id": aggregate_id,
            "event_id": event.event_id,
            "sequence": event.sequence,
            "event_digest": event.event_digest,
            "chain_intact": intact,
        }
        return _response(self._memory_outputs(episode, record))

    def tenant_memory_isolation_and_replay(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        if self.store is None:
            return _response(
                self._memory_outputs(
                    {"status": "NOT_RUN"}, {"status": "DURABLE_STORE_REQUIRED"}
                ),
                status="FAILED",
            )
        trace = _mapping(values["agent trace"], "agent trace")
        aggregate_id = require_identifier(trace.get("aggregate_id"), "aggregate_id")
        try:
            events = self.store.list_events(scope, aggregate_id)
            intact = self.store.verify_event_chain(scope, aggregate_id)
        except StoreError as exc:
            raise ValueError("memory replay failed closed") from exc
        episodes = [dict(event.payload) for event in events if event.event_type == "experience-captured"]
        replay = {
            "status": "REPLAYED" if intact else "BLOCKED_TAMPERED",
            "aggregate_id": aggregate_id,
            "episode_count": len(episodes),
            "episodes": episodes,
            "chain_intact": intact,
        }
        return _response(
            self._memory_outputs(
                replay,
                {
                    "tenant_id": scope.tenant_id,
                    "project_id": scope.project_id,
                    "aggregate_id": aggregate_id,
                },
            ),
            status="SUCCEEDED" if intact else "FAILED",
        )

    @staticmethod
    def _dataset_outputs(
        dataset: Mapping[str, Any], lineage: Mapping[str, Any], decision: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return {
            "versioned dataset": dataset,
            "dataset card": {
                "dataset_id": dataset.get("dataset_id"),
                "item_count": len(cast(Sequence[Any], dataset.get("items", []))),
                "raw_customer_content_stored": False,
                "independent_corpus_status": "NOT_ESTABLISHED",
            },
            "lineage graph": lineage,
            "training eligibility decision": {
                **decision,
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        }

    def dataset_contract_and_schema(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        episode_input = _mapping(values["experience episode"], "experience episode")
        episodes = _sequence(episode_input.get("episodes"), "episodes", maximum=100_000)
        evidence = _mapping(values["verification evidence"], "verification evidence")
        consent = episode_input.get("training_consent")
        claimed_consent = consent == "allow"
        claimed_independent_verification = (
            evidence.get("verdict") == "PASS" and evidence.get("independent") is True
        )
        # Both fields above are caller-controlled package inputs. They are useful
        # candidates for a later authorization workflow, but neither is trusted
        # consent nor independent evidence. This local handler therefore never
        # grants training eligibility.
        eligible = False
        items: list[Mapping[str, Any]] = []
        for index, raw in enumerate(episodes):
            episode = _mapping(raw, f"episodes[{index}]")
            episode_id = require_identifier(episode.get("episode_id"), "episode_id")
            bucket = int(canonical_digest(episode_id)[-8:], 16) % 100
            split = "train" if bucket < 80 else "validation" if bucket < 90 else "holdout"
            items.append(
                {
                    "item_id": "item-" + canonical_digest(episode).removeprefix("sha256:")[:32],
                    "episode_id": episode_id,
                    "split": split,
                    "content_digest": canonical_digest(episode),
                    "quarantine": not eligible,
                }
            )
        dataset_body = {
            "schema_version": "elmos.foundry.dataset-contract.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "items": items,
            "split_algorithm": "sha256-bucket-80-10-10-v1",
        }
        dataset_id = "dataset-" + canonical_digest(dataset_body).removeprefix("sha256:")[:32]
        dataset = {**dataset_body, "dataset_id": dataset_id}
        lineage = {
            "dataset_id": dataset_id,
            "episode_digests": [item["content_digest"] for item in items],
            "knowledge_object_digest": canonical_digest(values["knowledge object"]),
            "human_feedback_digest": canonical_digest(values["human feedback"]),
            "evidence_digest": canonical_digest(evidence),
        }
        decision = {
            "decision": "EVIDENCE_PENDING",
            "eligible": False,
            "input_claims_only": {
                "training_consent_claimed": claimed_consent,
                "independent_verification_claimed": claimed_independent_verification,
            },
            "reason_codes": [
                "trusted-request-bound-consent-verifier-required",
                "trusted-independent-evidence-verifier-required",
            ],
        }
        return _response(self._dataset_outputs(dataset, lineage, decision))

    def dataset_quarantine_management(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        dataset_input = _mapping(values["experience episode"], "experience episode")
        items: list[dict[str, Any]] = []
        for raw_item in _sequence(
            dataset_input.get("dataset_items"),
            "dataset_items",
            minimum=0,
            maximum=100_000,
        ):
            item = _mapping(raw_item, "dataset item")
            item_id = require_identifier(item.get("item_id"), "item_id")
            declared_digest = item.get("content_digest")
            if declared_digest is not None:
                validate_digest(declared_digest, "dataset_item.content_digest")
            items.append(
                {
                    "item_id": item_id,
                    "source_record_digest": canonical_digest(item),
                    "content_digest": declared_digest or canonical_digest(item),
                    "quarantine": True,
                    "raw_content_stored": False,
                }
            )
        evidence = _mapping(values["verification evidence"], "verification evidence")
        requested = {
            require_identifier(item, "quarantine_item_id")
            for item in _sequence(
                evidence.get("quarantine_item_ids"),
                "quarantine_item_ids",
                minimum=0,
            )
        }
        known = {str(item["item_id"]) for item in items}
        unknown = sorted(requested - known)
        if unknown:
            raise ValueError(f"quarantine references unknown items: {unknown}")
        for item in items:
            item["quarantine"] = item["item_id"] in requested
        body = {
            "schema_version": "elmos.foundry.dataset-quarantine.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "items": items,
            "quarantined_item_ids": sorted(requested),
        }
        dataset = {
            **body,
            "dataset_id": "dataset-" + canonical_digest(body).removeprefix("sha256:")[:32],
        }
        decision = {
            "decision": "DENY_QUARANTINED_ITEMS" if requested else "NO_CHANGE",
            "eligible": False,
            "reason_codes": ["quarantine-is-non-training"] if requested else [],
        }
        return _response(
            self._dataset_outputs(
                dataset,
                {"source_dataset_digest": canonical_digest(dataset_input)},
                decision,
            )
        )

    def task_canonicalization_and_normalization(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        canonical = canonical_value(values)
        task_id = "task-" + canonical_digest(canonical).removeprefix("sha256:")[:32]
        if isinstance(canonical, dict):
            content_shape = "object"
            top_level_item_count = len(canonical)
        elif isinstance(canonical, list):
            content_shape = "array"
            top_level_item_count = len(canonical)
        else:
            content_shape = type(canonical).__name__
            top_level_item_count = 1
        dataset = {
            "dataset_id": task_id,
            "schema_version": "elmos.foundry.canonical-task.v1",
            "items": [
                {
                    "item_id": task_id,
                    "split": "unassigned",
                    "content_digest": canonical_digest(canonical),
                    "content_shape": content_shape,
                    "top_level_item_count": top_level_item_count,
                    "raw_content_stored": False,
                }
            ],
        }
        return _response(
            self._dataset_outputs(
                dataset,
                {"task_digest": canonical_digest(canonical)},
                {
                    "decision": "NOT_EVALUATED_FOR_TRAINING",
                    "eligible": False,
                    "reason_codes": ["normalization-is-not-training-authorization"],
                },
            )
        )

    @staticmethod
    def _evidence_outputs(
        scores: Mapping[str, Any], counterexamples: Sequence[Mapping[str, Any]], decision: str
    ) -> Mapping[str, Any]:
        bundle = {
            "scores": scores,
            "counterexamples": list(counterexamples),
            "decision": decision,
            "evidence_state": "COLLECTED_SELF_ATTESTED",
            "external_evidence_status": "NOT_RUN",
            "independent_verifier": False,
            "certification_status": "NOT_CERTIFIED",
        }
        return {
            "scores": scores,
            "counterexamples": list(counterexamples),
            "evidence bundle": {**bundle, "bundle_digest": canonical_digest(bundle)},
            "certification decision": {
                "decision": decision,
                "certified": False,
                "certification_status": "NOT_CERTIFIED",
            },
        }

    def evidence_aggregation_and_completeness(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        policy = _mapping(values["policy"], "policy")
        required = {
            require_identifier(item, "required_gate")
            for item in _sequence(policy.get("required_gates"), "required_gates", maximum=256)
        }
        trace = _sequence(values["trace"], "trace", minimum=0, maximum=10_000)
        observed: dict[str, str] = {}
        for index, raw in enumerate(trace):
            record = _exact_mapping(raw, f"trace[{index}]", {"gate", "status", "digest"})
            gate = require_identifier(record["gate"], "gate")
            if gate not in required:
                raise ValueError(f"trace[{index}] references an undeclared gate")
            if gate in observed:
                raise ValueError(f"trace[{index}] duplicates gate {gate}")
            validate_digest(record["digest"], "evidence.digest")
            status = _text(record["status"], "evidence.status")
            if status not in {
                "PASS",
                "FAIL",
                "NOT_RUN",
                "UNKNOWN",
                "INCONCLUSIVE",
                "BLOCKED",
            }:
                raise ValueError(f"trace[{index}] has an unsupported evidence status")
            observed[gate] = status
        counterexamples = [
            {"gate": gate, "status": observed.get(gate, "NOT_RUN")}
            for gate in sorted(required)
            if observed.get(gate) != "PASS"
        ]
        complete = not counterexamples
        scores = {
            "required": len(required),
            "passed": len(required) - len(counterexamples),
            "complete": complete,
            "candidate_digest": canonical_digest(values["candidate output"]),
            "baseline_digest": canonical_digest(values["baseline"]),
            "repository_snapshot_digest": canonical_digest(values["repository snapshot"]),
        }
        decision = "READY_FOR_EXTERNAL_GATE" if complete else "DENY"
        return _response(self._evidence_outputs(scores, counterexamples, decision))

    def uncertainty_and_abstention_evaluation(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        candidate = _mapping(values["candidate output"], "candidate output")
        confidence = _number(candidate.get("confidence"), "candidate confidence")
        policy = _mapping(values["policy"], "policy")
        threshold = _number(policy.get("minimum_confidence"), "minimum_confidence")
        status = candidate.get("status")
        uncertain = status in {"UNKNOWN", "INCONCLUSIVE", "NOT_RUN"} or confidence < threshold
        counterexamples = [] if not uncertain else [
            {"code": "ABSTENTION_REQUIRED", "status": status, "confidence": confidence}
        ]
        scores = {
            "confidence": confidence,
            "minimum_confidence": threshold,
            "abstain": uncertain,
        }
        return _response(
            self._evidence_outputs(scores, counterexamples, "ABSTAIN" if uncertain else "READY_FOR_EXTERNAL_GATE")
        )

    @staticmethod
    def _serving_outputs(
        request: Mapping[str, Any], selected: Mapping[str, Any] | None, decision: str
    ) -> Mapping[str, Any]:
        route = {
            "decision": decision,
            "request_digest": canonical_digest(request),
            "selected_candidate": selected,
            "provider_execution_status": "NOT_RUN",
        }
        return {
            "routed request": route,
            "structured response": {
                "status": decision,
                "provider_response": None,
                "external_evidence_status": "NOT_RUN",
            },
            "usage record": {
                "provider_calls": 0,
                "estimated_only": True,
                "billable_usage": "NOT_RUN",
            },
            "serving evidence": {
                "route_digest": canonical_digest(route),
                "evidence_state": "COLLECTED_SELF_ATTESTED",
                "certification_status": "NOT_CERTIFIED",
            },
        }

    @staticmethod
    def _serving_values(values: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any]]:
        request = _mapping(values["inference request"], "inference request")
        policy = _mapping(values["tenant policy"], "tenant policy")
        registry = _mapping(values["model registry"], "model registry")
        capacity = _mapping(values["capacity state"], "capacity state")
        candidates = [
            _mapping(item, "model candidate")
            for item in _sequence(
                registry.get("candidates"),
                "model candidates",
                minimum=0,
                maximum=64,
            )
        ]
        return request, candidates, policy, capacity

    @staticmethod
    def _candidate_identity(
        candidate: Mapping[str, Any], index: int
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        raw_candidate_id = candidate.get("candidate_id")
        try:
            candidate_id = require_identifier(raw_candidate_id, "candidate_id")
        except (TypeError, ValueError):
            return None, {
                "candidate_index": index,
                "code": "CANDIDATE_ID_INVALID",
            }
        version = candidate.get("version")
        if (
            not isinstance(version, str)
            or not version.strip()
            or version != version.strip()
            or any(token in version for token in ("*", ">", "<", "~", "^"))
            or version.casefold() == "latest"
        ):
            return None, {
                "candidate_index": index,
                "candidate_id": candidate_id,
                "code": "MODEL_VERSION_NOT_EXACT",
            }
        digest = candidate.get("artifact_digest")
        try:
            validate_digest(digest, "artifact_digest")
        except (TypeError, ValueError):
            return None, {
                "candidate_index": index,
                "candidate_id": candidate_id,
                "code": "ARTIFACT_DIGEST_INVALID",
            }
        return {
            "candidate_id": candidate_id,
            "version": version,
            "artifact_digest": digest,
        }, None

    def health_warmup_and_readiness(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        request, candidates, _, capacity = self._serving_values(values)
        ready: list[Mapping[str, Any]] = []
        invalid: list[Mapping[str, Any]] = []
        for index, candidate in enumerate(candidates):
            identity, error = self._candidate_identity(candidate, index)
            if error is not None:
                invalid.append(error)
                continue
            assert identity is not None
            if candidate.get("health") == "AVAILABLE" and candidate.get("warmup") == "PASS":
                ready.append({**identity, "health": "AVAILABLE", "warmup": "PASS"})
        if capacity.get("status") != "AVAILABLE" or invalid:
            ready = []
        selected = sorted(ready, key=lambda item: str(item["candidate_id"]))[0] if ready else None
        outputs = dict(
            self._serving_outputs(
                request, selected, "READY_FOR_EXTERNAL_GATE" if selected else "BLOCKED"
            )
        )
        outputs["serving evidence"] = {
            **cast(Mapping[str, Any], outputs["serving evidence"]),
            "invalid_candidates": invalid,
        }
        return _response(outputs)

    def complexity_risk_cost_latency_routing(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        request, candidates, policy, capacity = self._serving_values(values)
        max_cost = _number(policy.get("max_cost_usd"), "max_cost_usd")
        max_latency = _number(policy.get("max_latency_ms"), "max_latency_ms")
        accepted: list[Mapping[str, Any]] = []
        invalid: list[Mapping[str, Any]] = []
        if capacity.get("status") == "AVAILABLE":
            for index, candidate in enumerate(candidates):
                identity, identity_error = self._candidate_identity(candidate, index)
                if identity_error is not None:
                    invalid.append(identity_error)
                    continue
                assert identity is not None
                try:
                    cost = _number(candidate.get("estimated_cost_usd"), "candidate.cost")
                    latency = _number(candidate.get("estimated_latency_ms"), "candidate.latency")
                    quality = _number(candidate.get("quality_score"), "candidate.quality")
                except (TypeError, ValueError):
                    invalid.append(
                        {
                            "candidate_index": index,
                            "candidate_id": identity["candidate_id"],
                            "code": "ROUTING_METRICS_INVALID",
                        }
                    )
                    continue
                if (
                    candidate.get("health") == "AVAILABLE"
                    and candidate.get("warmup") == "PASS"
                    and cost <= max_cost
                    and latency <= max_latency
                    and 0 <= quality <= 1
                ):
                    accepted.append(
                        {
                            **identity,
                            "health": "AVAILABLE",
                            "warmup": "PASS",
                            "estimated_cost_usd": cost,
                            "estimated_latency_ms": latency,
                            "quality_score": quality,
                        }
                    )
        if invalid:
            accepted = []
        selected = (
            sorted(
                accepted,
                key=lambda item: (
                    -float(item["quality_score"]),
                    float(item["estimated_cost_usd"]),
                    float(item["estimated_latency_ms"]),
                    str(item["candidate_id"]),
                ),
            )[0]
            if accepted
            else None
        )
        outputs = dict(
            self._serving_outputs(
                request, selected, "READY_FOR_EXTERNAL_GATE" if selected else "BLOCKED"
            )
        )
        outputs["serving evidence"] = {
            **cast(Mapping[str, Any], outputs["serving evidence"]),
            "invalid_candidates": invalid,
        }
        return _response(outputs)

    def model_version_pinning_determinism(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        request, candidates, _, _ = self._serving_values(values)
        identities: list[Mapping[str, Any]] = []
        invalid: list[Mapping[str, Any]] = []
        for index, candidate in enumerate(candidates):
            identity, error = self._candidate_identity(candidate, index)
            if error is not None:
                invalid.append(error)
            else:
                assert identity is not None
                identities.append(identity)
        selected = (
            sorted(identities, key=lambda item: str(item["candidate_id"]))[0]
            if identities and not invalid
            else None
        )
        decision = "READY_FOR_EXTERNAL_GATE" if selected else "BLOCKED"
        outputs = dict(self._serving_outputs(request, selected, decision))
        outputs["serving evidence"] = {
            **cast(Mapping[str, Any], outputs["serving evidence"]),
            "invalid_candidates": invalid,
        }
        return _response(outputs)

    def tool_call_schema_and_policy_check(
        self, skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        request, _, policy, _ = self._serving_values(values)
        calls = _sequence(
            request.get("tool_calls"), "tool_calls", minimum=0, maximum=256
        )
        schemas = _mapping(policy.get("tool_schemas"), "tool_schemas")
        allowed = {
            require_identifier(item, "allowed_tool")
            for item in _sequence(
                policy.get("allowed_tools"),
                "allowed_tools",
                minimum=0,
                maximum=256,
            )
        }
        violations: list[Mapping[str, Any]] = []
        for index, raw in enumerate(calls):
            call = _exact_mapping(raw, f"tool_calls[{index}]", {"tool", "arguments"})
            tool = require_identifier(call["tool"], "tool")
            if tool not in allowed:
                violations.append({"index": index, "tool": tool, "code": "TOOL_NOT_ALLOWED"})
                continue
            raw_schema = schemas.get(tool)
            if not isinstance(raw_schema, Mapping):
                violations.append({"index": index, "tool": tool, "code": "SCHEMA_UNBOUND"})
                continue
            try:
                _validate_simple_schema(call["arguments"], raw_schema, f"tool_calls[{index}].arguments")
            except ValueError as exc:
                violations.append(
                    {"index": index, "tool": tool, "code": "SCHEMA_INVALID", "detail": str(exc)}
                )
        decision = "READY_FOR_EXTERNAL_GATE" if not violations else "BLOCKED"
        outputs = dict(self._serving_outputs(request, None, decision))
        outputs["serving evidence"] = {
            **cast(Mapping[str, Any], outputs["serving evidence"]),
            "tool_call_violations": violations,
            "validated_call_count": len(calls) - len(violations),
        }
        return _response(outputs)


def build_local_adapter_registry(
    catalog: CatalogView,
    *,
    store: FoundryStore | None = None,
) -> AdapterRegistry:
    """Build the exact repository-owned local registry with no provider bindings."""

    return LocalSemanticRuntime(catalog, store=store).register(AdapterRegistry())


__all__ = [
    "LOCAL_SEMANTIC_SKILLS",
    "LOCAL_SEMANTIC_VERSION",
    "LocalSemanticRuntime",
    "build_local_adapter_registry",
]
