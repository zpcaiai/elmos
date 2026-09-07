"""Eight exact, bounded foundation operations; contracts never mint effect authority.

This module validates and compiles caller-supplied contracts. Compatibility and
policy evaluations are local analyses, not trusted provider evidence or permits.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    LocalSemanticRuntime,
    _exact_mapping,
    _inputs,
    _mapping,
    _response,
    _sequence,
    _text,
    _topological_order,
)
from .store import FoundryStore

FOUNDATION_SEMANTIC_SKILLS = frozenset(
    {
        "architecture-decision-record",
        "capability-taxonomy-governance",
        "compatibility-matrix-manager",
        "tenancy-scope-contract",
        "evidence-contract",
        "policy-contract",
        "data-usage-consent-contract",
        "release-bundle-contract",
    }
)


def _strings(value: Any, label: str, *, minimum: int = 1) -> list[str]:
    items = [
        _text(item, label, maximum=512)
        for item in _sequence(value, label, minimum=minimum, maximum=1310)
    ]
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicates")
    return items


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 2**53:
        raise ValueError(f"{label} must be a bounded integer >= {minimum}")
    return int(value)


def _scope(value: Any, scope: TenantScope) -> Mapping[str, Any]:
    obj = _mapping(value, "scope")
    for key in ("tenant_id", "project_id"):
        if obj.get(key) != getattr(scope, key):
            raise ValueError(f"{key} does not match authenticated scope")
    return obj


def _result(
    skill: str, payload: Mapping[str, Any], primary: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _response(
        LocalSemanticRuntime._foundation_outputs(
            skill,
            _inputs(payload),
            {
                **primary,
                "effect_authorized": False,
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        )
    )


class FoundationSemantics:
    def __init__(self, catalog: CatalogView) -> None:
        self.catalog = catalog

    def architecture_decision_record(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        requirement = _exact_mapping(
            values["business requirement"], "requirement", {"purpose", "acceptance"}
        )
        if requirement["purpose"] != scope.purpose:
            raise ValueError("ADR purpose differs from authenticated scope")
        _strings(requirement["acceptance"], "acceptance")
        adr = _exact_mapping(
            values["architecture decision"],
            "ADR",
            {
                "id",
                "title",
                "context",
                "owner",
                "version",
                "alternatives",
                "selected",
                "assumptions",
                "consequences",
                "exit_conditions",
                "supersedes",
                "rollback_digest",
            },
        )
        for key in ("id", "owner", "version", "selected"):
            require_identifier(adr[key], key)
        for key in ("title", "context"):
            _text(adr[key], key)
        for key in ("assumptions", "consequences", "exit_conditions"):
            _strings(adr[key], key)
        alternatives = _sequence(adr["alternatives"], "alternatives", minimum=2, maximum=32)
        ids: set[str] = set()
        for raw in alternatives:
            alternative = _exact_mapping(raw, "alternative", {"id", "description", "tradeoffs"})
            identity = require_identifier(alternative["id"], "alternative.id")
            if identity in ids:
                raise ValueError("duplicate ADR alternative")
            ids.add(identity)
            _text(alternative["description"], "alternative.description")
            _strings(alternative["tradeoffs"], "alternative.tradeoffs")
        if adr["selected"] not in ids:
            raise ValueError("selected ADR alternative does not exist")
        previous = adr["supersedes"]
        if previous is not None:
            validate_digest(previous, "supersedes")
        validate_digest(adr["rollback_digest"], "rollback_digest")
        normalized = {
            **adr,
            "alternatives": sorted(alternatives, key=lambda item: item["id"]),
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
        }
        return _result(
            skill,
            payload,
            {
                "adr": canonical_value(normalized),
                "adr_digest": canonical_digest(normalized),
                "search_terms": sorted(set(str(adr["title"]).casefold().split())),
                "approval_status": "NOT_RUN",
            },
        )

    def capability_taxonomy_governance(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        requirement = _exact_mapping(
            _inputs(payload)["business requirement"], "requirement", {"purpose", "acceptance"}
        )
        if requirement["purpose"] != scope.purpose:
            raise ValueError("taxonomy purpose differs from authenticated scope")
        _strings(requirement["acceptance"], "acceptance")
        inventory = _exact_mapping(
            _inputs(payload)["runtime capability inventory"],
            "taxonomy",
            {"version", "capabilities"},
        )
        require_identifier(inventory["version"], "taxonomy.version")
        records: dict[str, Mapping[str, Any]] = {}
        boundaries: set[tuple[str, str]] = set()
        for raw in _sequence(inventory["capabilities"], "capabilities", maximum=1310):
            row = _exact_mapping(
                raw,
                "capability",
                {
                    "name",
                    "domain",
                    "boundary",
                    "owner",
                    "risk",
                    "maturity",
                    "dependencies",
                },
            )
            for key in ("name", "domain", "owner"):
                require_identifier(row[key], key)
            name = str(row["name"])
            if name not in self.catalog.atomic_skills or name in records:
                raise ValueError("taxonomy identity is unknown or duplicate")
            boundary = _text(row["boundary"], "boundary").strip().casefold()
            key_pair = (str(row["domain"]), boundary)
            if key_pair in boundaries:
                raise ValueError("duplicate capability domain and boundary")
            boundaries.add(key_pair)
            if row["risk"] not in {"low", "medium", "high", "critical", "research"}:
                raise ValueError("unknown taxonomy risk")
            if row["maturity"] not in {"DECLARED", "PREPARE_ONLY", "LOCAL"}:
                raise ValueError("taxonomy cannot assert production maturity")
            actual = self.catalog.atomic_skills[name]["capability_state"]
            if row["maturity"] == "LOCAL" and actual != "LOCAL":
                raise ValueError("taxonomy maturity exceeds the exact implemented binding")
            dependencies = _strings(row["dependencies"], "dependencies", minimum=0)
            records[name] = {**row, "dependencies": dependencies}
        order = _topological_order({name: row["dependencies"] for name, row in records.items()})
        result = {
            "version": inventory["version"],
            "capabilities": [records[n] for n in sorted(records)],
        }
        return _result(
            skill,
            payload,
            {
                "taxonomy": result,
                "topological_order": list(order),
                "taxonomy_digest": canonical_digest(result),
            },
        )

    def compatibility_matrix_manager(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        query = _exact_mapping(
            values["business requirement"], "compatibility query", {"source", "target"}
        )
        inventory = _exact_mapping(
            values["runtime capability inventory"], "matrix", {"version", "rows"}
        )
        require_identifier(inventory["version"], "matrix.version")

        def exact_tuple(raw: Any) -> Mapping[str, Any]:
            row = _exact_mapping(raw, "version tuple", {"kind", "name", "version", "environment"})
            for key, value in row.items():
                _text(value, key, maximum=256)
                if (
                    value != value.strip()
                    or value.casefold()
                    in {
                        "latest",
                        "unknown",
                        "unbound",
                        "stable",
                        "nightly",
                        "main",
                        "master",
                        "head",
                        "current",
                        "next",
                        "lts",
                    }
                    or any(c in value for c in "*<>=~^")
                    or (
                        key == "version"
                        and "x" in value.casefold().replace("-", ".").replace("_", ".").split(".")
                    )
                ):
                    raise ValueError("compatibility requires exact versions and environment")
            return row

        source, target = exact_tuple(query["source"]), exact_tuple(query["target"])
        rows: dict[str, Mapping[str, Any]] = {}
        for raw in _sequence(inventory["rows"], "matrix.rows", minimum=0):
            row = _exact_mapping(
                raw, "matrix.row", {"source", "target", "status", "evidence_digest"}
            )
            key = canonical_digest([exact_tuple(row["source"]), exact_tuple(row["target"])])
            if key in rows:
                raise ValueError("duplicate directional compatibility tuple")
            if row["status"] not in {"SUPPORTED", "UNSUPPORTED", "UNKNOWN", "NOT_RUN"}:
                raise ValueError("unknown compatibility status")
            if row["status"] == "SUPPORTED":
                validate_digest(row["evidence_digest"], "evidence_digest")
            elif row["evidence_digest"] is not None:
                validate_digest(row["evidence_digest"], "evidence_digest")
            rows[key] = row
        match = rows.get(canonical_digest([source, target]))
        return _result(
            skill,
            payload,
            {
                "source": source,
                "target": target,
                "declared_status": "UNKNOWN" if match is None else match["status"],
                "matrix_digest": canonical_digest([rows[key] for key in sorted(rows)]),
                "evidence_verification": "NOT_RUN",
                "runtime_compatible": False,
            },
        )

    def tenancy_scope_contract(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        request = _exact_mapping(
            _inputs(payload)["business requirement"],
            "scope contract",
            {
                "tenant_id",
                "project_id",
                "actor_id",
                "environment_id",
                "workspace_digest",
                "revision_set_id",
                "purpose",
                "resources",
            },
        )
        _scope(request, scope)
        for key in ("actor_id", "environment_id", "workspace_digest", "revision_set_id", "purpose"):
            if request[key] != getattr(scope, key):
                raise ValueError(f"scope contract mismatched {key}")
        resources: dict[str, Mapping[str, Any]] = {}
        ranks = {
            "platform": 0,
            "organization": 1,
            "tenant": 2,
            "project": 3,
            "repository": 4,
            "branch": 5,
            "task": 6,
            "user": 7,
        }
        for raw in _sequence(request["resources"], "resources", maximum=2048):
            row = _exact_mapping(
                raw, "resource", {"id", "kind", "parent_id", "tenant_id", "project_id"}
            )
            _scope(row, scope)
            identity = require_identifier(row["id"], "resource.id")
            if (
                identity in resources
                or not isinstance(row["kind"], str)
                or row["kind"] not in ranks
            ):
                raise ValueError("duplicate or unknown scope resource")
            resources[identity] = row
        graph: dict[str, list[str]] = {}
        for identity, row in resources.items():
            parent = row["parent_id"]
            graph[identity] = [] if parent is None else [require_identifier(parent, "parent_id")]
            if parent is None and row["kind"] != "platform":
                raise ValueError("scope tree requires a platform root")
            if parent is not None:
                previous = resources.get(str(parent))
                if previous is None or ranks[str(previous["kind"])] >= ranks[str(row["kind"])]:
                    raise ValueError("scope hierarchy parent is absent or out of order")
        if sum(row["parent_id"] is None for row in resources.values()) != 1:
            raise ValueError("scope tree must have exactly one root")
        order = _topological_order(graph)
        return _result(
            skill,
            payload,
            {
                "scope_digest": canonical_digest(request),
                "resource_order": list(order),
                "authority_source": "host-context",
                "resource_ownership_verification": "NOT_RUN",
            },
        )

    def evidence_contract(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        requirement = _exact_mapping(
            _inputs(payload)["business requirement"],
            "evidence contract",
            {
                "subject_digest",
                "executor",
                "verifier",
                "obligations",
            },
        )
        validate_digest(requirement["subject_digest"], "subject_digest")
        executor = require_identifier(requirement["executor"], "executor")
        verifier = require_identifier(requirement["verifier"], "verifier")
        if executor == verifier:
            raise ValueError("evidence executor and independent verifier must differ")
        obligations: dict[str, Mapping[str, Any]] = {}
        for raw in _sequence(requirement["obligations"], "obligations", maximum=1024):
            row = _exact_mapping(
                raw,
                "obligation",
                {"id", "kind", "mandatory", "corpus", "replay", "artifact_digest"},
            )
            identity = require_identifier(row["id"], "obligation.id")
            if identity in obligations or row["kind"] not in {
                "compile",
                "test",
                "differential",
                "proof",
                "security",
                "human-approval",
            }:
                raise ValueError("duplicate or unsupported evidence obligation")
            if type(row["mandatory"]) is not bool:
                raise ValueError("mandatory must be boolean")
            if row["corpus"] not in {"development", "negative", "holdout", "representative"}:
                raise ValueError("unknown evidence corpus")
            for argument in _sequence(row["replay"], "replay arguments", maximum=256):
                _text(argument, "replay argument", maximum=4096)
            validate_digest(row["artifact_digest"], "artifact_digest")
            obligations[identity] = {**row, "status": "NOT_RUN"}
        if not any(row["mandatory"] for row in obligations.values()):
            raise ValueError("evidence contract needs a mandatory obligation")
        contract = {**requirement, "obligations": [obligations[n] for n in sorted(obligations)]}
        return _result(
            skill,
            payload,
            {
                "contract": contract,
                "contract_digest": canonical_digest(contract),
                "verification_complete": False,
            },
        )

    def policy_contract(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        values = _inputs(payload)
        policy = _exact_mapping(values["policy profile"], "policy", {"version", "default", "rules"})
        require_identifier(policy["version"], "policy.version")
        if policy["default"] != "DENY":
            raise ValueError("policy default must be DENY")
        request = _exact_mapping(
            values["business requirement"],
            "policy request",
            {
                "tenant_id",
                "project_id",
                "action",
                "resource",
                "purpose",
            },
        )
        _scope(request, scope)
        for key in ("action", "resource", "purpose"):
            _text(request[key], key)
        matches: list[str] = []
        decisions: set[str] = set()
        ids: set[str] = set()
        rules: list[Mapping[str, Any]] = []
        for raw in _sequence(policy["rules"], "rules", minimum=0, maximum=1024):
            rule = _exact_mapping(raw, "rule", {"id", "effect", "match", "obligations"})
            identity = require_identifier(rule["id"], "rule.id")
            if identity in ids or rule["effect"] not in {"ALLOW", "DENY"}:
                raise ValueError("duplicate rule or unsupported effect")
            ids.add(identity)
            match = _exact_mapping(rule["match"], "rule.match", set(request))
            for key, value in match.items():
                if not isinstance(value, str) or not value or "*" in value:
                    raise ValueError("policy match requires exact non-wildcard values")
            obligations = _strings(rule["obligations"], "obligations", minimum=0)
            if obligations:
                raise ValueError(
                    "mandatory policy obligations have no configured enforcement handler"
                )
            rules.append(rule)
            if match == request:
                matches.append(identity)
                decisions.add(str(rule["effect"]))
        decision = "ALLOW" if "ALLOW" in decisions and "DENY" not in decisions else "DENY"
        compiled = {**policy, "rules": sorted(rules, key=lambda row: str(row["id"]))}
        return _result(
            skill,
            payload,
            {
                "compiled_policy": compiled,
                "policy_digest": canonical_digest(compiled),
                "simulation_decision": decision,
                "matched_rules": sorted(matches),
                "enforcement_status": "NOT_RUN",
            },
        )

    def data_usage_consent_contract(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        request = _exact_mapping(
            _inputs(payload)["business requirement"],
            "consent contract",
            {
                "tenant_id",
                "project_id",
                "subject_digest",
                "purpose",
                "uses",
                "issued_at",
                "expires_at",
                "retention_until",
                "evaluated_at",
                "revoked",
            },
        )
        _scope(request, scope)
        validate_digest(request["subject_digest"], "subject_digest")
        _text(request["purpose"], "purpose")
        uses = _exact_mapping(
            request["uses"],
            "uses",
            {
                "retrieve",
                "record",
                "label",
                "train",
                "aggregate",
                "export",
                "delete",
                "retain",
            },
        )
        if any(value not in {"ALLOW", "DENY"} for value in uses.values()):
            raise ValueError("each consent use requires explicit ALLOW or DENY")
        if type(request["revoked"]) is not bool:
            raise ValueError("revoked must be boolean")
        for key in ("issued_at", "expires_at", "retention_until", "evaluated_at"):
            _integer(request[key], key)
        if not request["issued_at"] < request["expires_at"] <= request["retention_until"]:
            raise ValueError("consent validity and retention interval are invalid")
        active = (
            not request["revoked"]
            and request["purpose"] == scope.purpose
            and request["issued_at"] <= request["evaluated_at"] < request["expires_at"]
        )
        decisions = {name: value if active else "DENY" for name, value in uses.items()}
        return _result(
            skill,
            payload,
            {
                "consent_digest": canonical_digest(request),
                "declared_use_decisions": decisions,
                "consent_receipt_verification": "NOT_RUN",
                "training_authorized": False,
                "export_authorized": False,
            },
        )

    def release_bundle_contract(
        self,
        skill: str,
        payload: Mapping[str, Any],
        scope: TenantScope,
        invocation: str,
    ) -> Mapping[str, Any]:
        request = _exact_mapping(
            _inputs(payload)["business requirement"],
            "release bundle",
            {
                "version",
                "tenant_id",
                "project_id",
                "components",
                "skills",
                "rollback_digest",
            },
        )
        _scope(request, scope)
        require_identifier(request["version"], "release.version")
        validate_digest(request["rollback_digest"], "rollback_digest")
        components = _exact_mapping(
            request["components"],
            "components",
            {
                "model",
                "adapter",
                "knowledge",
                "toolchain",
                "policy",
                "evaluation",
            },
        )
        for key, value in components.items():
            validate_digest(value, key)
        pinned: dict[str, Mapping[str, Any]] = {}
        for raw in _sequence(request["skills"], "skills", maximum=1310):
            row = _exact_mapping(raw, "skill", {"name", "version", "source_sha256"})
            name = require_identifier(row["name"], "skill.name")
            actual = self.catalog.atomic_skills.get(name)
            if actual is None or name in pinned:
                raise ValueError("unknown or duplicate release Skill")
            if (
                row["version"] != actual["version"]
                or row["source_sha256"] != actual["source_sha256"]
            ):
                raise ValueError("release Skill version or source digest mismatch")
            pinned[name] = row
        bundle = {
            **request,
            "skills": [pinned[name] for name in sorted(pinned)],
            "catalog_digest": self.catalog.content_sha256,
        }
        return _result(
            skill,
            payload,
            {
                "bundle": bundle,
                "bundle_digest": canonical_digest(bundle),
                "signature_status": "NOT_RUN",
                "published": False,
            },
        )


def build_foundation_handlers(
    catalog: CatalogView, store: FoundryStore | None
) -> dict[str, LocalHandler]:
    runtime = FoundationSemantics(catalog)
    return {
        "architecture-decision-record": runtime.architecture_decision_record,
        "capability-taxonomy-governance": runtime.capability_taxonomy_governance,
        "compatibility-matrix-manager": runtime.compatibility_matrix_manager,
        "tenancy-scope-contract": runtime.tenancy_scope_contract,
        "evidence-contract": runtime.evidence_contract,
        "policy-contract": runtime.policy_contract,
        "data-usage-consent-contract": runtime.data_usage_consent_contract,
        "release-bundle-contract": runtime.release_bundle_contract,
    }
