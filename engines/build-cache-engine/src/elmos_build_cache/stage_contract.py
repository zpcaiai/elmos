"""Stage Contract registry.

A stage cannot execute unless its contract validates. The contract is the
single authority for: which artifacts it consumes and produces, which of those
are required, which files it may export from the sandbox, which fingerprint
dimensions its ActionKey depends on, its determinism class, its cache policy
and validation floor, its writable roots, its side effects, and its checkpoint
policy.

Runtime guards, documentation and key dimensions are all *derived* from this
one object, so they cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import schemas
from .canonical import digest_of
from .enums import CacheMode, Determinism, FileClass, ValidationLevel
from .errors import ContractViolation, NotFound
from .fingerprint import EXCLUDED_DIMENSIONS, StageFingerprintSpec
from .staging import WRITABLE_ROOTS

SCHEMA_VERSION = "1.0.0"
CONTRACT_SCHEMA_ID = "elmos.stage-contract/v1"


@dataclass(frozen=True)
class PortSpec:
    name: str
    schema: str
    required: bool = True
    staging_class: FileClass | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "schema": self.schema, "required": self.required}
        if self.staging_class is not None:
            data["staging_class"] = str(self.staging_class)
        return data


@dataclass(frozen=True)
class SideEffectSpec:
    name: str
    effect_type: str
    idempotent: bool
    compensatable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "effect_type": self.effect_type,
            "idempotent": self.idempotent,
            "compensatable": self.compensatable,
        }


@dataclass(frozen=True)
class StageContract:
    stage_id: str
    stage_version: str
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]
    fingerprint_include: tuple[str, ...]
    fingerprint_exclude: tuple[str, ...] = ()
    declared_environment: tuple[str, ...] = ()
    cache_mode: CacheMode = CacheMode.READ_WRITE
    negative_cache: bool = False
    minimum_validation_level: ValidationLevel = ValidationLevel.TEST_VERIFIED
    determinism: Determinism = Determinism.DETERMINISTIC
    writable_roots: tuple[str, ...] = ("generated/pending", "scratch")
    source_access: str = "read-only"
    undeclared_output_policy: str = "quarantine"
    checkpoint_stage_boundary: bool = True
    checkpoint_interval_seconds: int = 30
    checkpoint_partition_key: str | None = None
    side_effects: tuple[SideEffectSpec, ...] = ()
    resources: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stage_id": self.stage_id,
            "stage_version": self.stage_version,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
            "fingerprint": {
                "include": list(self.fingerprint_include),
                "exclude": list(self.fingerprint_exclude),
                "declared_environment": list(self.declared_environment),
            },
            "cache_policy": {
                "mode": str(self.cache_mode),
                "negative_cache": self.negative_cache,
                "minimum_validation_level": str(self.minimum_validation_level),
            },
            "workspace": {
                "source": self.source_access,
                "writable_roots": list(self.writable_roots),
                "undeclared_output_policy": self.undeclared_output_policy,
            },
            "determinism": str(self.determinism),
            "checkpoint_policy": {
                "stage_boundary": self.checkpoint_stage_boundary,
                "interval_seconds": self.checkpoint_interval_seconds,
                "partition_key": self.checkpoint_partition_key,
            },
            "side_effects": [effect.to_dict() for effect in self.side_effects],
            "minimum_validation_level": str(self.minimum_validation_level),
            "resources": self.resources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageContract:
        schemas.validate("stage-contract", data)
        fingerprint = data.get("fingerprint", {})
        cache_policy = data.get("cache_policy", {})
        workspace = data.get("workspace", {})
        checkpoint = data.get("checkpoint_policy", {})
        return cls(
            stage_id=data["stage_id"],
            stage_version=data["stage_version"],
            inputs=tuple(_port(item) for item in data["inputs"]),
            outputs=tuple(_port(item) for item in data["outputs"]),
            fingerprint_include=tuple(fingerprint.get("include", ())),
            fingerprint_exclude=tuple(fingerprint.get("exclude", ())),
            declared_environment=tuple(fingerprint.get("declared_environment", ())),
            cache_mode=CacheMode(cache_policy.get("mode", "read-write")),
            negative_cache=bool(cache_policy.get("negative_cache", False)),
            minimum_validation_level=ValidationLevel(
                cache_policy.get(
                    "minimum_validation_level", data.get("minimum_validation_level", "TEST_VERIFIED")
                )
            ),
            determinism=Determinism(data["determinism"]),
            writable_roots=tuple(workspace.get("writable_roots", ("generated/pending", "scratch"))),
            source_access=workspace.get("source", "read-only"),
            undeclared_output_policy=workspace.get("undeclared_output_policy", "quarantine"),
            checkpoint_stage_boundary=bool(checkpoint.get("stage_boundary", True)),
            checkpoint_interval_seconds=int(checkpoint.get("interval_seconds", 30)),
            checkpoint_partition_key=checkpoint.get("partition_key"),
            side_effects=tuple(
                SideEffectSpec(
                    name=item.get("name", item.get("effect_type", "effect")),
                    effect_type=item["effect_type"],
                    idempotent=bool(item.get("idempotent", False)),
                    compensatable=bool(item.get("compensatable", False)),
                )
                for item in data.get("side_effects", [])
            ),
            resources=data.get("resources", {}),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )

    # -- derived surfaces -------------------------------------------------
    def digest(self) -> str:
        """Contract identity. Participates in the ActionKey via the spec below."""
        return digest_of(self.to_dict())

    def fingerprint_spec(self) -> StageFingerprintSpec:
        return StageFingerprintSpec(
            stage_id=self.stage_id,
            stage_version=self.stage_version,
            stage_contract_schema=f"{CONTRACT_SCHEMA_ID}#{self.digest()[:19]}",
            include=self.fingerprint_include,
            declared_environment=self.declared_environment,
            exclude=self.fingerprint_exclude,
        )

    def required_outputs(self) -> tuple[str, ...]:
        return tuple(port.name for port in self.outputs if port.required)

    def exportable_classes(self) -> dict[str, FileClass]:
        return {
            port.name: port.staging_class
            for port in self.outputs
            if port.staging_class is not None
        }

    def guard(self) -> RuntimeGuard:
        return RuntimeGuard(self)

    def documentation(self) -> str:
        lines = [
            f"# Stage `{self.stage_id}` v{self.stage_version}",
            "",
            f"- determinism: **{self.determinism}**",
            f"- cache mode: `{self.cache_mode}`, validation floor `{self.minimum_validation_level}`",
            f"- writable roots: {', '.join(self.writable_roots)}",
            f"- undeclared output policy: `{self.undeclared_output_policy}`",
            f"- contract digest: `{self.digest()}`",
            "",
            "## Inputs",
        ]
        lines += [
            f"- `{port.name}` ({port.schema}){'' if port.required else ' — optional'}"
            for port in self.inputs
        ]
        lines += ["", "## Outputs"]
        lines += [
            f"- `{port.name}` ({port.schema}){'' if port.required else ' — optional'}"
            f"{f' → {port.staging_class}' if port.staging_class else ''}"
            for port in self.outputs
        ]
        lines += ["", "## Fingerprint dimensions", ""]
        lines += [f"- `{name}`" for name in sorted(self.fingerprint_include)]
        if self.side_effects:
            lines += ["", "## Side effects", ""]
            lines += [
                f"- `{effect.name}` ({effect.effect_type}) "
                f"idempotent={effect.idempotent} compensatable={effect.compensatable}"
                for effect in self.side_effects
            ]
        return "\n".join(lines) + "\n"


def _port(item: dict[str, Any]) -> PortSpec:
    staging = item.get("staging_class")
    return PortSpec(
        name=item["name"],
        schema=item["schema"],
        required=bool(item.get("required", True)),
        staging_class=FileClass(staging) if staging else None,
    )


class RuntimeGuard:
    """Enforces at runtime exactly what the contract declared."""

    def __init__(self, contract: StageContract) -> None:
        self.contract = contract
        self._declared_outputs: set[str] = set()

    def check_write_root(self, root: str) -> None:
        if root not in self.contract.writable_roots:
            raise ContractViolation(
                "stage wrote outside its declared writable roots",
                stage_id=self.contract.stage_id,
                root=root,
                allowed=sorted(self.contract.writable_roots),
            )
        if root not in WRITABLE_ROOTS:
            raise ContractViolation("root is not writable in any workspace", root=root)

    def declare_output(self, name: str) -> PortSpec:
        for port in self.contract.outputs:
            if port.name == name:
                self._declared_outputs.add(name)
                return port
        raise ContractViolation(
            "stage produced an undeclared output port",
            stage_id=self.contract.stage_id,
            output=name,
            declared=[port.name for port in self.contract.outputs],
        )

    def check_complete(self) -> None:
        missing = sorted(set(self.contract.required_outputs()) - self._declared_outputs)
        if missing:
            raise ContractViolation(
                "stage did not produce all required outputs",
                stage_id=self.contract.stage_id,
                missing=missing,
            )

    def check_environment(self, observed: dict[str, str]) -> dict[str, list[str]]:
        audit = self.contract.fingerprint_spec().audit_environment(observed)
        if audit["undeclared"] and self.contract.determinism is Determinism.DETERMINISTIC:
            raise ContractViolation(
                "deterministic stage read undeclared environment values",
                stage_id=self.contract.stage_id,
                undeclared=audit["undeclared"],
            )
        return audit


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LintFinding:
    severity: str
    code: str
    message: str
    stage_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "stage_id": self.stage_id,
        }


def lint_contract(contract: StageContract) -> list[LintFinding]:
    """Catch the contract mistakes that silently destroy hit rate or safety."""
    findings: list[LintFinding] = []

    def add(severity: str, code: str, message: str) -> None:
        findings.append(LintFinding(severity, code, message, contract.stage_id))

    forbidden = sorted(set(contract.fingerprint_include) & EXCLUDED_DIMENSIONS)
    if forbidden:
        add("ERROR", "EXCLUDED_DIMENSION", f"run-scoped dimensions in the key: {forbidden}")

    if not contract.outputs:
        add("ERROR", "NO_OUTPUTS", "a stage with no declared outputs can export nothing")
    if not any(port.required for port in contract.outputs):
        add("WARN", "NO_REQUIRED_OUTPUT", "no output is required, so completeness cannot be checked")

    if "input_artifact_digests" not in contract.fingerprint_include:
        add("ERROR", "MISSING_INPUT_DIGESTS", "the key ignores input artifacts and would over-reuse")
    if "source_semantic_digest" in contract.fingerprint_include and (
        "dependency_public_interface_digests" not in contract.fingerprint_include
    ):
        add(
            "WARN",
            "BROAD_INVALIDATION",
            "semantic digest without dependency interface digests invalidates more than necessary",
        )

    if contract.determinism is Determinism.NONDETERMINISTIC_CANDIDATE_ONLY and contract.cache_mode.may_write:
        add(
            "ERROR",
            "NONDETERMINISTIC_WRITE",
            "candidate-only stages must not populate the exact cache",
        )
    if contract.determinism is Determinism.SEEDED and "model_snapshot_digest" not in contract.fingerprint_include:
        add("ERROR", "UNPINNED_MODEL", "seeded stage does not pin a model snapshot in its key")

    for root in contract.writable_roots:
        if root not in WRITABLE_ROOTS:
            add("ERROR", "UNDECLARED_PATH", f"writable root {root!r} is outside the workspace contract")
    if contract.source_access != "read-only":
        add("ERROR", "MUTABLE_SOURCE", "the source snapshot must be read-only")
    if contract.undeclared_output_policy not in ("quarantine", "reject"):
        add("ERROR", "UNDECLARED_OUTPUT_POLICY", "undeclared output policy must quarantine or reject")

    if contract.minimum_validation_level is ValidationLevel.QUARANTINED:
        add("ERROR", "MISSING_VALIDATION_FLOOR", "validation floor cannot be QUARANTINED")
    if (
        contract.minimum_validation_level is ValidationLevel.UNVERIFIED
        and contract.cache_mode.may_read
    ):
        add("WARN", "LOW_VALIDATION_FLOOR", "reads accept UNVERIFIED results")

    for effect in contract.side_effects:
        if not effect.idempotent and not effect.compensatable:
            add(
                "ERROR",
                "UNSAFE_SIDE_EFFECT",
                f"side effect {effect.name!r} is neither idempotent nor compensatable",
            )

    for port in list(contract.inputs) + list(contract.outputs):
        if "@latest" in port.schema or port.schema.endswith("/latest"):
            add("ERROR", "MUTABLE_ALIAS", f"port {port.name!r} references a mutable schema alias")
        if "/" not in port.schema:
            add("WARN", "UNVERSIONED_SCHEMA", f"port {port.name!r} has no schema version")

    if contract.negative_cache and contract.determinism is not Determinism.DETERMINISTIC:
        add("ERROR", "UNSAFE_NEGATIVE_CACHE", "only deterministic stages may negative-cache failures")

    return findings


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------
class StageContractRegistry:
    """Holds the contracts and the producer/consumer capability DAG."""

    def __init__(self, external_schemas: Iterable[str] = ()) -> None:
        self._contracts: dict[str, StageContract] = {}
        #: Schemas supplied from outside the stage DAG (e.g. the repository
        #: snapshot, which the snapshot engine produces before any stage runs).
        self.external_schemas: set[str] = set(external_schemas)

    def register(self, contract: StageContract, allow_lint_warnings: bool = True) -> StageContract:
        findings = lint_contract(contract)
        errors = [finding for finding in findings if finding.severity == "ERROR"]
        if errors:
            raise ContractViolation(
                "stage contract failed lint",
                stage_id=contract.stage_id,
                findings=[finding.to_dict() for finding in errors],
            )
        if not allow_lint_warnings and findings:
            raise ContractViolation(
                "stage contract has lint warnings",
                stage_id=contract.stage_id,
                findings=[finding.to_dict() for finding in findings],
            )
        key = contract.stage_id
        existing = self._contracts.get(key)
        if existing is not None and existing.digest() != contract.digest():
            if existing.stage_version == contract.stage_version:
                raise ContractViolation(
                    "contract changed without a version bump",
                    stage_id=key,
                    stage_version=contract.stage_version,
                )
        self._contracts[key] = contract
        return contract

    def get(self, stage_id: str) -> StageContract:
        try:
            return self._contracts[stage_id]
        except KeyError as exc:
            raise NotFound("stage is not registered", stage_id=stage_id) from exc

    def __contains__(self, stage_id: object) -> bool:
        return stage_id in self._contracts

    def stage_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._contracts))

    def load_directory(self, directory: Path) -> list[StageContract]:
        loaded: list[StageContract] = []
        for path in sorted(Path(directory).glob("*.stage-contract.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            loaded.append(self.register(StageContract.from_dict(data)))
        return loaded

    def capability_edges(self) -> list[tuple[str, str, str]]:
        """``(producer, consumer, schema)`` edges implied by matching schemas."""
        edges: list[tuple[str, str, str]] = []
        producers: dict[str, list[str]] = {}
        for contract in self._contracts.values():
            for port in contract.outputs:
                producers.setdefault(port.schema, []).append(contract.stage_id)
        for contract in self._contracts.values():
            for port in contract.inputs:
                for producer in sorted(producers.get(port.schema, [])):
                    if producer != contract.stage_id:
                        edges.append((producer, contract.stage_id, port.schema))
        return sorted(set(edges))

    def validate_compatibility(self) -> list[LintFinding]:
        """Every required input must have some registered producer."""
        findings: list[LintFinding] = []
        produced = {port.schema for contract in self._contracts.values() for port in contract.outputs}
        for contract in self._contracts.values():
            for port in contract.inputs:
                if port.required and port.schema not in produced and port.schema not in self.external_schemas:
                    findings.append(
                        LintFinding(
                            "ERROR",
                            "UNSATISFIED_INPUT",
                            f"required input {port.name!r} ({port.schema}) has no registered producer",
                            contract.stage_id,
                        )
                    )
        return findings

    def digest(self) -> str:
        return digest_of({stage: contract.digest() for stage, contract in sorted(self._contracts.items())})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "registry_digest": self.digest(),
            "external_schemas": sorted(self.external_schemas),
            "stages": [contract.to_dict() for _, contract in sorted(self._contracts.items())],
            "edges": [list(edge) for edge in self.capability_edges()],
        }


# --------------------------------------------------------------------------
# the ELMOS conversion pipeline
# --------------------------------------------------------------------------
_ANALYSIS_DIMENSIONS = (
    "stage_id",
    "stage_version",
    "stage_contract_schema",
    "input_artifact_digests",
    "target_language",
    "toolchain_digest",
    "rule_pack_digest",
    "declared_environment",
    "feature_flags",
)

_GENERATION_DIMENSIONS = _ANALYSIS_DIMENSIONS + (
    "dependency_public_interface_digests",
    "target_framework",
    "target_runtime",
    "prompt_template_digest",
    "model_snapshot_digest",
    "decoding_parameters",
)

_BUILD_DIMENSIONS = _ANALYSIS_DIMENSIONS + (
    "target_framework",
    "target_runtime",
    "target_triple",
    "compiler_flags",
    "dependency_lock_digests",
)


def default_pipeline() -> list[StageContract]:
    """The conversion stages ELMOS runs, as contracts rather than prose."""

    def contract(
        stage_id: str,
        inputs: Sequence[tuple[str, str, bool]],
        outputs: Sequence[tuple[str, str, bool, FileClass | None]],
        dimensions: tuple[str, ...],
        determinism: Determinism = Determinism.DETERMINISTIC,
        validation: ValidationLevel = ValidationLevel.COMPILE_VERIFIED,
        partition_key: str | None = None,
        side_effects: Sequence[SideEffectSpec] = (),
    ) -> StageContract:
        return StageContract(
            stage_id=stage_id,
            stage_version="1.0.0",
            inputs=tuple(PortSpec(name, schema, required) for name, schema, required in inputs),
            outputs=tuple(
                PortSpec(name, schema, required, staging) for name, schema, required, staging in outputs
            ),
            fingerprint_include=dimensions,
            declared_environment=("LANG", "TZ", "ELMOS_TARGET_PROFILE"),
            determinism=determinism,
            minimum_validation_level=validation,
            checkpoint_partition_key=partition_key,
            side_effects=tuple(side_effects),
        )

    return [
        contract(
            "repository-discovery",
            [("snapshot", "elmos.snapshot/v1", True)],
            [("inventory", "elmos.inventory/v1", True, FileClass.STAGED_INTERMEDIATE)],
            _ANALYSIS_DIMENSIONS,
            validation=ValidationLevel.UNVERIFIED,
        ),
        contract(
            "source-parse",
            [("inventory", "elmos.inventory/v1", True)],
            [("cst", "elmos.cst/v1", True, FileClass.STAGED_INTERMEDIATE)],
            _ANALYSIS_DIMENSIONS,
            validation=ValidationLevel.UNVERIFIED,
            partition_key="file_id",
        ),
        contract(
            "normalize",
            [("cst", "elmos.cst/v1", True)],
            [("ast", "elmos.ast/v1", True, FileClass.STAGED_INTERMEDIATE)],
            _ANALYSIS_DIMENSIONS,
            validation=ValidationLevel.UNVERIFIED,
        ),
        contract(
            "semantic-analysis",
            [("ast", "elmos.ast/v1", True)],
            [
                ("symbols", "elmos.symbol-graph/v1", True, FileClass.STAGED_INTERMEDIATE),
                ("types", "elmos.type-graph/v1", True, FileClass.STAGED_INTERMEDIATE),
                ("calls", "elmos.call-graph/v1", True, FileClass.STAGED_INTERMEDIATE),
                ("dataflow", "elmos.dataflow-graph/v1", False, FileClass.STAGED_INTERMEDIATE),
            ],
            _ANALYSIS_DIMENSIONS,
            validation=ValidationLevel.UNVERIFIED,
            partition_key="module_id",
        ),
        contract(
            "semantic-ir",
            [
                ("symbols", "elmos.symbol-graph/v1", True),
                ("types", "elmos.type-graph/v1", True),
                ("calls", "elmos.call-graph/v1", True),
            ],
            [("ir", "elmos.semantic-ir/v3", True, FileClass.STAGED_INTERMEDIATE)],
            _ANALYSIS_DIMENSIONS,
            validation=ValidationLevel.UNVERIFIED,
        ),
        contract(
            "mapping-plan",
            [("ir", "elmos.semantic-ir/v3", True)],
            [("mapping_plan", "elmos.mapping-plan/v2", True, FileClass.STAGED_INTERMEDIATE)],
            _GENERATION_DIMENSIONS,
            determinism=Determinism.SEEDED,
            validation=ValidationLevel.UNVERIFIED,
        ),
        contract(
            "target-code-generation",
            [("ir", "elmos.semantic-ir/v3", True), ("mapping_plan", "elmos.mapping-plan/v2", True)],
            [
                ("generated_tree", "elmos.file-tree/v1", True, FileClass.PUBLISH_CANDIDATE),
                ("source_maps", "elmos.source-map/v1", True, FileClass.STAGED_INTERMEDIATE),
            ],
            _GENERATION_DIMENSIONS,
            determinism=Determinism.SEEDED,
            validation=ValidationLevel.TEST_VERIFIED,
            partition_key="symbol_id",
        ),
        contract(
            "dependency-conversion",
            [("ir", "elmos.semantic-ir/v3", True)],
            [("dependency_manifest", "elmos.dependency-manifest/v1", True, FileClass.PUBLISH_CANDIDATE)],
            _BUILD_DIMENSIONS,
            validation=ValidationLevel.COMPILE_VERIFIED,
        ),
        contract(
            "compile",
            [
                ("generated_tree", "elmos.file-tree/v1", True),
                ("dependency_manifest", "elmos.dependency-manifest/v1", True),
            ],
            [("build_output", "elmos.build-output/v1", True, FileClass.SEALED_ARTIFACT)],
            _BUILD_DIMENSIONS,
            validation=ValidationLevel.COMPILE_VERIFIED,
        ),
        contract(
            "test",
            [("build_output", "elmos.build-output/v1", True)],
            [("test_report", "elmos.test-report/v1", True, FileClass.SEALED_ARTIFACT)],
            _BUILD_DIMENSIONS,
            validation=ValidationLevel.TEST_VERIFIED,
            partition_key="test_shard",
        ),
        contract(
            "behavior-validation",
            [("test_report", "elmos.test-report/v1", True)],
            [("behavior_report", "elmos.behavior-report/v1", True, FileClass.SEALED_ARTIFACT)],
            _BUILD_DIMENSIONS,
            validation=ValidationLevel.BEHAVIOR_VERIFIED,
        ),
        contract(
            "repair",
            [("test_report", "elmos.test-report/v1", True), ("ir", "elmos.semantic-ir/v3", True)],
            [("patches", "elmos.patch-set/v1", False, FileClass.STAGED_INTERMEDIATE)],
            _GENERATION_DIMENSIONS,
            determinism=Determinism.SEEDED,
            validation=ValidationLevel.TEST_VERIFIED,
        ),
        contract(
            "certification",
            [
                ("behavior_report", "elmos.behavior-report/v1", True),
                ("generated_tree", "elmos.file-tree/v1", True),
            ],
            [("evidence_bundle", "elmos.evidence-bundle/v1", True, FileClass.SEALED_ARTIFACT)],
            _BUILD_DIMENSIONS,
            validation=ValidationLevel.PRODUCTION_CERTIFIED,
            side_effects=(SideEffectSpec("issue-certificate", "certificate", idempotent=True),),
        ),
    ]


#: Produced by the snapshot engine before the stage DAG starts.
EXTERNAL_SCHEMAS: tuple[str, ...] = ("elmos.snapshot/v1",)


def default_registry() -> StageContractRegistry:
    registry = StageContractRegistry(external_schemas=EXTERNAL_SCHEMAS)
    for contract in default_pipeline():
        registry.register(contract)
    return registry


def registry_from(
    contracts: Iterable[StageContract], external_schemas: Iterable[str] = EXTERNAL_SCHEMAS
) -> StageContractRegistry:
    registry = StageContractRegistry(external_schemas=external_schemas)
    for contract in contracts:
        registry.register(contract)
    return registry
