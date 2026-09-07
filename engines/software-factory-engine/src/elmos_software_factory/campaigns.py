"""Executable local holdout, provider-contract, and Canary rehearsal campaigns.

The runner has no command, plugin, provider, credential, or network dispatch
surface.  It executes only checked-in Python handlers and deterministic fixtures.
Consequently its receipts are useful local engineering evidence but can never
promote independent holdout, real provider, or production execution states.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any

from . import artifact_binding as artifact_binding_module
from . import capabilities as capabilities_module
from . import canonical as canonical_module
from . import evidence_models as evidence_models_module
from . import handlers as handlers_module
from . import models as models_module
from . import public_methods as public_methods_module
from . import registry as registry_module
from . import runtime as runtime_module
from .artifact_binding import ContentReference, read_content_reference
from .capabilities import CAPABILITY_REGISTRY_DIGEST
from .canonical import canonical_digest, strict_json_copy
from .evidence_models import (
    CampaignReceipt,
    CampaignScope,
    EvidenceContractError,
    EXTERNAL_STATES,
    digest,
    exact_mapping,
    token,
)
from .public_methods import PUBLIC_METHODS, PUBLIC_METHOD_REGISTRY_DIGEST
from .runtime import SoftwareFactoryEngine, dispatch_skill


_COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_type",
        "scope",
        "target_artifact_digest",
        "environment_digest",
        "corpus_digest",
        "executor_id",
        "controls",
        "bindings",
    }
)
_CONTROLS = frozenset({"network_allowed", "provider_calls_allowed", "max_production_writes"})
_CONTENT_BINDINGS = frozenset({"target_manifest", "environment_manifest", "corpus_manifest"})
_DEVELOPMENT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "corpus_key",
        "corpus_role",
        "scope",
        "case_count",
        "case_digests",
        "cases",
        "limitations",
    }
)
_RESPONSE_FIELDS = ("provider_id", "operation", "request_digest", "state", "artifact_digest", "error_code")
_TARGET_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_set",
        "aggregate_algorithm",
        "aggregate_sha256",
        "file_count",
        "total_size_bytes",
        "scope",
        "generated_install_manifests",
        "files",
    }
)
_TARGET_ENTRY_FIELDS = frozenset({"path", "sha256", "size_bytes"})
_GENERATED_INSTALL_MANIFEST_FIELDS = frozenset(
    {"status", "compiled_manifest", "installed_manifest", "transitive_scope", "limitations"}
)
_GENERATED_MANIFEST_REFERENCE_FIELDS = frozenset({"path", "sha256"})
_ENVIRONMENT_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_key",
        "operating_system",
        "python",
        "jsonschema",
        "network_required",
        "production_access",
        "provider_access",
        "authorized_scope",
        "scope",
        "local_test_commands",
        "limitations",
    }
)
_ENVIRONMENT_SCOPE_FIELDS = frozenset({"tenant_id", "project_id", "policy_revision", "source_revision"})
_CORPUS_COMMON_FIELDS = frozenset(
    {
        "schema_version",
        "corpus_key",
        "campaign_type",
        "corpus_role",
        "input_state",
        "campaign_ref",
        "scope",
        "corpus_digest",
        "limitations",
    }
)
_TARGET_AGGREGATE_ALGORITHM = (
    "SHA-256 over UTF-8 lines '<sha256>\\t<size_bytes>\\t<repository_relative_path>\\n' "
    "in LC_ALL=C path order"
)
_MAX_TARGET_FILES = 512
_MAX_TARGET_TOTAL_BYTES = 64 * 1024 * 1024
_RUNTIME_SOURCE_PREFIX = "engines/software-factory-engine/src/elmos_software_factory"
_RUNTIME_SOURCE_FILES = (
    "__init__.py",
    "__main__.py",
    "archive_contracts.py",
    "artifact_binding.py",
    "campaigns.py",
    "canonical.py",
    "capabilities.py",
    "capability_registry.json",
    "cli.py",
    "evidence_intake.py",
    "evidence_models.py",
    "handlers.py",
    "models.py",
    "public_method_registry.json",
    "public_methods.py",
    "registry.py",
    "runtime.py",
    "skill_registry.json",
)


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceContractError(f"bound JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _bound_json(reference: object, root: Path, label: str) -> tuple[Mapping[str, Any], ContentReference]:
    parsed = ContentReference.from_mapping(reference)
    if parsed.path == ".":
        raise EvidenceContractError(f"{label} path must identify a file below evidence_root")
    if parsed.media_type != "application/json":
        raise EvidenceContractError(f"{label} media_type must be application/json")
    raw = read_content_reference(parsed, root)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                EvidenceContractError(f"{label} contains invalid number {item}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError(f"{label} must be strict UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{label} must contain a JSON object")
    return value, parsed


def _bounded_strings(
    value: object,
    label: str,
    *,
    maximum: int = 256,
    require_sorted: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise EvidenceContractError(f"{label} must be a non-empty array of at most {maximum} strings")
    parsed: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or len(item) > 1024:
            raise EvidenceContractError(f"{label}[{index}] must be a non-empty bounded string")
        parsed.append(item)
    if len(set(parsed)) != len(parsed):
        raise EvidenceContractError(f"{label} must contain unique values")
    if require_sorted and parsed != sorted(parsed):
        raise EvidenceContractError(f"{label} must be sorted")
    return tuple(parsed)


def _sha256_hex(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EvidenceContractError(f"{label} must be lowercase SHA-256 hex")
    return value


def _walk_code(code: CodeType) -> tuple[CodeType, ...]:
    values = [code]
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            values.extend(_walk_code(constant))
    return tuple(values)


def _code_key(code: CodeType) -> tuple[str, str, int]:
    return code.co_qualname, code.co_name, code.co_firstlineno


def _code_constant(value: object) -> object:
    if isinstance(value, CodeType):
        return {"type": "code", "value": _code_contract(value)}
    if value is None:
        return {"type": "none"}
    if value is Ellipsis:
        return {"type": "ellipsis"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value.hex()}
    if isinstance(value, complex):
        return {"type": "complex", "real": value.real.hex(), "imag": value.imag.hex()}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if isinstance(value, tuple):
        return {"type": "tuple", "value": [_code_constant(item) for item in value]}
    if isinstance(value, slice):
        return {
            "type": "slice",
            "start": _code_constant(value.start),
            "stop": _code_constant(value.stop),
            "step": _code_constant(value.step),
        }
    if isinstance(value, frozenset):
        items = [_code_constant(item) for item in value]
        return {"type": "frozenset", "value": sorted(items, key=canonical_digest)}
    raise EvidenceContractError(
        f"runtime code contains unsupported constant type {type(value).__name__}"
    )


def _code_contract(code: CodeType) -> Mapping[str, Any]:
    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "stacksize": code.co_stacksize,
        "flags": code.co_flags,
        "code": code.co_code.hex(),
        "consts": [_code_constant(item) for item in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "name": code.co_name,
        "qualname": code.co_qualname,
        "firstlineno": code.co_firstlineno,
        "linetable": code.co_linetable.hex(),
        "exceptiontable": code.co_exceptiontable.hex(),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
    }


def _loaded_module_code_record(
    module: ModuleType,
    *,
    source_bytes: bytes,
    expected_file: str,
    package_root: Path,
) -> Mapping[str, str | int]:
    """Bind every source-defined loaded function/method to freshly compiled target bytes."""

    expected_path = (package_root / expected_file).resolve(strict=True)
    try:
        compiled = compile(
            source_bytes,
            str(expected_path),
            "exec",
            dont_inherit=True,
            optimize=sys.flags.optimize,
        )
    except (SyntaxError, ValueError, TypeError) as exc:
        raise EvidenceContractError(
            f"runtime module {module.__name__} target source cannot be compiled"
        ) from exc

    loaded: dict[tuple[str, str, int], CodeType] = {}
    class_names: set[str] = set()

    def add_callable(value: object) -> None:
        function = value
        if isinstance(value, (classmethod, staticmethod)):
            function = value.__func__
        candidates = (
            (value.fget, value.fset, value.fdel) if isinstance(value, property) else (function,)
        )
        for candidate in candidates:
            if candidate is None or not inspect.isfunction(candidate):
                continue
            if candidate.__module__ != module.__name__:
                continue
            code = candidate.__code__
            try:
                origin = Path(code.co_filename).resolve(strict=True)
            except OSError:
                continue
            if origin != expected_path:
                continue
            loaded[_code_key(code)] = code

    for name, value in vars(module).items():
        if inspect.isfunction(value):
            add_callable(value)
        elif inspect.isclass(value) and value.__module__ == module.__name__:
            class_names.add(name)
            for member in vars(value).values():
                add_callable(member)

    expected: dict[tuple[str, str, int], CodeType] = {}
    for code in _walk_code(compiled):
        if code.co_name in {"<module>", "__annotate__"} or code.co_name.startswith("<"):
            continue
        if "<locals>" in code.co_qualname:
            continue
        if "." not in code.co_qualname and code.co_qualname in class_names:
            continue
        expected[_code_key(code)] = code
    if set(loaded) != set(expected):
        missing = sorted(set(expected) - set(loaded))
        extra = sorted(set(loaded) - set(expected))
        raise EvidenceContractError(
            f"runtime callable inventory drifted for {module.__name__}: "
            f"missing={missing} extra={extra}"
        )

    rows: list[Mapping[str, str | int]] = []
    for key in sorted(loaded):
        observed = _code_contract(loaded[key])
        compiled_contract = _code_contract(expected[key])
        if observed != compiled_contract:
            raise EvidenceContractError(
                f"runtime callable {module.__name__}.{key[0]} loaded bytecode differs from target bytes"
            )
        rows.append(
            {
                "qualname": key[0],
                "name": key[1],
                "firstlineno": key[2],
                "code_digest": canonical_digest(observed),
            }
        )
    return {
        "module": module.__name__,
        "source_path": f"{_RUNTIME_SOURCE_PREFIX}/{expected_file}",
        "source_artifact_digest": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
        "callable_count": len(rows),
        "loaded_code_digest": canonical_digest(rows),
    }


def _strict_registry_document(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceContractError(f"{label} target bytes are not strict JSON") from exc
    if not isinstance(value, Mapping):
        raise EvidenceContractError(f"{label} target bytes must contain an object")
    return value


def _loaded_capability_registry_digest() -> str:
    values = [
        {
            "skill_name": item.skill_name,
            "action": item.action,
            "mode": item.mode,
            "required_inputs": list(item.required_inputs),
        }
        for item in capabilities_module.CAPABILITY_CONTRACTS.values()
    ]
    return canonical_digest({"schema_version": "1.0", "capabilities": values})


def _loaded_public_method_registry_digest() -> str:
    values = [
        {
            "method": item.method,
            "package_id": item.package_id,
            "action": item.action,
            "execution_mode": item.execution_mode,
            "required_inputs": list(item.required_inputs),
            "domain_errors": list(item.domain_errors),
            "platform_errors": list(item.platform_errors),
        }
        for item in public_methods_module.PUBLIC_METHODS.values()
    ]
    return canonical_digest({"schema_version": "1.0", "methods": values})


def _loaded_skill_registry_digest() -> str:
    registry = registry_module.DEFAULT_SKILL_REGISTRY
    registry.validate()
    root = registry.bindings.get(registry_module.ROOT_SKILL_NAME)
    if root is None:
        raise EvidenceContractError("loaded runtime Skill registry omits its root binding")
    packages = [
        {
            "package_id": item.package_id,
            "name": item.name,
            "dependencies": list(item.dependencies),
            "operation": item.operation,
            "adapter_actions": sorted(item.adapter_actions),
            "skills": list(item.child_skills),
        }
        for item in registry.packages.values()
    ]
    return canonical_digest(
        {
            "schema_version": "1.0",
            "root_skill": {"name": root.name, "operation": root.operation},
            "packages": packages,
        }
    )


def _runtime_binding_digest(entries: Mapping[str, Mapping[str, Any]]) -> str:
    package_root = Path(__file__).resolve(strict=True).parent
    rows: list[Mapping[str, Any]] = []
    artifacts: dict[str, bytes] = {}
    for name in _RUNTIME_SOURCE_FILES:
        target_path = f"{_RUNTIME_SOURCE_PREFIX}/{name}"
        entry = entries.get(target_path)
        if entry is None:
            raise EvidenceContractError(f"target manifest omits required runtime artifact {target_path}")
        raw_digest = _sha256_hex(entry.get("sha256"), f"target runtime artifact {target_path}.sha256")
        size = entry.get("size_bytes")
        reference = ContentReference.from_mapping(
            {
                "path": name,
                "sha256": f"sha256:{raw_digest}",
                "size_bytes": size,
                "media_type": "application/octet-stream",
            }
        )
        artifacts[name] = read_content_reference(reference, package_root)
        rows.append({"path": target_path, "sha256": f"sha256:{raw_digest}", "size_bytes": size})

    if dispatch_skill is not runtime_module.dispatch_skill:
        raise EvidenceContractError("campaign dispatcher is not the verified runtime dispatcher")
    if SoftwareFactoryEngine is not runtime_module.SoftwareFactoryEngine:
        raise EvidenceContractError("campaign engine class is not the verified runtime engine")
    runtime_namespace = vars(runtime_module)
    if runtime_namespace.get("handle") is not handlers_module.handle:
        raise EvidenceContractError("runtime handler entrypoint identity drifted")
    if runtime_namespace.get("DEFAULT_SKILL_REGISTRY") is not registry_module.DEFAULT_SKILL_REGISTRY:
        raise EvidenceContractError("runtime Skill registry object identity drifted")
    if runtime_namespace.get("CAPABILITY_CONTRACTS") is not capabilities_module.CAPABILITY_CONTRACTS:
        raise EvidenceContractError("runtime capability registry object identity drifted")
    if runtime_namespace.get("PUBLIC_METHODS") is not public_methods_module.PUBLIC_METHODS:
        raise EvidenceContractError("runtime public-method registry object identity drifted")
    if PUBLIC_METHODS is not public_methods_module.PUBLIC_METHODS:
        raise EvidenceContractError("campaign public-method registry object identity drifted")
    if CAPABILITY_REGISTRY_DIGEST != capabilities_module.CAPABILITY_REGISTRY_DIGEST:
        raise EvidenceContractError("campaign capability registry digest alias drifted")
    if PUBLIC_METHOD_REGISTRY_DIGEST != public_methods_module.PUBLIC_METHOD_REGISTRY_DIGEST:
        raise EvidenceContractError("campaign public-method registry digest alias drifted")

    registry_specs = (
        (
            "skill registry",
            "skill_registry.json",
            _loaded_skill_registry_digest(),
            registry_module.DEFAULT_SKILL_REGISTRY.registry_digest,
        ),
        (
            "capability registry",
            "capability_registry.json",
            _loaded_capability_registry_digest(),
            capabilities_module.CAPABILITY_REGISTRY_DIGEST,
        ),
        (
            "public-method registry",
            "public_method_registry.json",
            _loaded_public_method_registry_digest(),
            public_methods_module.PUBLIC_METHOD_REGISTRY_DIGEST,
        ),
    )
    registry_rows: list[Mapping[str, str]] = []
    for label, filename, loaded_digest, declared_digest in registry_specs:
        target_digest = canonical_digest(_strict_registry_document(artifacts[filename], label))
        if loaded_digest != target_digest or declared_digest != target_digest:
            raise EvidenceContractError(f"loaded {label} content differs from target bytes")
        registry_rows.append(
            {"name": label, "content_digest": target_digest, "source_path": filename}
        )

    module_specs = (
        (artifact_binding_module, "artifact_binding.py"),
        (capabilities_module, "capabilities.py"),
        (canonical_module, "canonical.py"),
        (evidence_models_module, "evidence_models.py"),
        (handlers_module, "handlers.py"),
        (models_module, "models.py"),
        (public_methods_module, "public_methods.py"),
        (registry_module, "registry.py"),
        (runtime_module, "runtime.py"),
        (sys.modules[__name__], "campaigns.py"),
    )
    module_rows = [
        _loaded_module_code_record(
            module,
            source_bytes=artifacts[filename],
            expected_file=filename,
            package_root=package_root,
        )
        for module, filename in module_specs
    ]
    return canonical_digest(
        {
            "runtime_artifacts": rows,
            "loaded_modules": module_rows,
            "loaded_registries": registry_rows,
        }
    )


def _verify_generated_install_manifests(
    value: object,
    *,
    entries: Mapping[str, Mapping[str, Any]],
) -> None:
    document = exact_mapping(
        value,
        _GENERATED_INSTALL_MANIFEST_FIELDS,
        "target manifest.generated_install_manifests",
    )
    if document["status"] != "LOCAL_INSTALLED_AND_CHECKED_SELF_ATTESTED":
        raise EvidenceContractError("generated install manifest status is invalid")
    for label in ("compiled_manifest", "installed_manifest"):
        reference = exact_mapping(
            document[label],
            _GENERATED_MANIFEST_REFERENCE_FIELDS,
            f"generated install manifest {label}",
        )
        raw_path = reference["path"]
        if not isinstance(raw_path, str):
            raise EvidenceContractError(f"generated install manifest {label}.path is invalid")
        target_entry = entries.get(raw_path)
        if target_entry is None:
            raise EvidenceContractError(f"generated install manifest {label} is not target-bound")
        path = ContentReference.from_mapping(
            {
                "path": raw_path,
                "sha256": f"sha256:{_sha256_hex(reference['sha256'], f'{label}.sha256')}",
                "size_bytes": target_entry.get("size_bytes"),
                "media_type": "application/json",
            }
        ).path
        if target_entry.get("sha256") != reference["sha256"] or path != raw_path:
            raise EvidenceContractError(f"generated install manifest {label} is not target-bound")
    _bounded_strings(document["transitive_scope"], "generated install transitive_scope")
    _bounded_strings(document["limitations"], "generated install limitations")


def _bounded_text(value: object, label: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EvidenceContractError(f"{label} must be a non-empty bounded string")
    return value


def _verify_environment_manifest(
    manifest: Mapping[str, Any],
    *,
    scope: CampaignScope,
) -> None:
    exact_mapping(manifest, _ENVIRONMENT_MANIFEST_FIELDS, "environment manifest")
    if manifest.get("schema_version") != 1:
        raise EvidenceContractError("environment manifest schema_version must be 1")
    token(manifest.get("environment_key"), "environment manifest.environment_key")
    for field in ("operating_system", "python", "jsonschema", "authorized_scope"):
        _bounded_text(manifest.get(field), f"environment manifest.{field}")
    for field in ("network_required", "production_access", "provider_access"):
        if manifest.get(field) is not False:
            raise EvidenceContractError(f"environment manifest.{field} must be false")
    environment_scope = exact_mapping(
        manifest.get("scope"), _ENVIRONMENT_SCOPE_FIELDS, "environment manifest.scope"
    )
    expected_scope = {
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "policy_revision": scope.policy_revision,
        "source_revision": scope.source_revision,
    }
    if dict(environment_scope) != expected_scope:
        raise EvidenceContractError("environment manifest scope differs from campaign scope")
    _bounded_strings(manifest.get("local_test_commands"), "environment manifest.local_test_commands")
    _bounded_strings(manifest.get("limitations"), "environment manifest.limitations")


def _manifest_case_ids(document: Mapping[str, Any], campaign_type: str) -> tuple[str, ...]:
    if campaign_type == "local-holdout":
        values = _array(document.get("cases"), "cases")
    elif campaign_type == "provider-contract-simulation":
        values = _array(document.get("fixtures"), "fixtures")
    else:
        rehearsal = exact_mapping(
            document.get("rehearsal"),
            frozenset(
                {
                    "mode",
                    "canary_population",
                    "initial_state",
                    "canary_state",
                    "rollback_state",
                    "events",
                    "abort_error_basis_points",
                    "expected_control_decision",
                }
            ),
            "Canary rehearsal",
        )
        values = _array(rehearsal.get("events"), "rehearsal.events")
    identities: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            raise EvidenceContractError(f"campaign case {index} must be an object")
        identities.append(token(item.get("case_id"), f"campaign case {index}.case_id"))
    if len(identities) != len(set(identities)):
        raise EvidenceContractError("campaign case identities contain duplicate case_id values")
    if identities != sorted(identities):
        raise EvidenceContractError("campaign case identities must be sorted by case_id")
    return tuple(identities)


def _verify_corpus_manifest(
    manifest: Mapping[str, Any],
    *,
    document: Mapping[str, Any],
    scope: CampaignScope,
    campaign_type: str,
    corpus_digest: str,
) -> None:
    type_fields: frozenset[str]
    if campaign_type == "local-holdout":
        type_fields = frozenset(
            {"case_count", "case_ids", "separation", "independent", "external_holdout_state"}
        )
        expected_role = "IMMUTABLE_LOCAL_INPUT"
        expected_input_state = "LOCAL_SELF_AUTHORED_NOT_INDEPENDENT"
    elif campaign_type == "provider-contract-simulation":
        type_fields = frozenset({"case_count", "case_ids", "provider_execution_state"})
        expected_role = "IMMUTABLE_OFFLINE_FIXTURE_INPUT"
        expected_input_state = "LOCAL_SELF_AUTHORED_FIXTURE_ONLY"
    else:
        type_fields = frozenset(
            {"event_count", "event_ids", "production_derived", "production_execution_state"}
        )
        expected_role = "IMMUTABLE_SYNTHETIC_INPUT"
        expected_input_state = "LOCAL_SELF_AUTHORED_SYNTHETIC_ONLY"
    exact_mapping(manifest, _CORPUS_COMMON_FIELDS | type_fields, "corpus manifest")
    if manifest.get("schema_version") != 1:
        raise EvidenceContractError("corpus manifest schema_version must be 1")
    token(manifest.get("corpus_key"), "corpus manifest.corpus_key")
    if manifest.get("campaign_type") != campaign_type:
        raise EvidenceContractError("corpus manifest campaign_type differs from campaign")
    if manifest.get("corpus_digest") != corpus_digest:
        raise EvidenceContractError("corpus manifest does not match corpus_digest")
    if manifest.get("corpus_role") != expected_role or manifest.get("input_state") != expected_input_state:
        raise EvidenceContractError("corpus manifest local evidence classification is invalid")
    token(manifest.get("campaign_ref"), "corpus manifest.campaign_ref")
    if CampaignScope.from_mapping(manifest.get("scope")) != scope:
        raise EvidenceContractError("corpus manifest scope differs from campaign scope")
    _bounded_strings(manifest.get("limitations"), "corpus manifest.limitations")
    identities = _manifest_case_ids(document, campaign_type)
    if campaign_type == "production-like-rehearsal":
        if manifest.get("event_count") != len(identities) or manifest.get("event_ids") != list(identities):
            raise EvidenceContractError("corpus manifest event inventory differs from campaign")
        if manifest.get("production_derived") is not False:
            raise EvidenceContractError("local rehearsal corpus cannot be production-derived")
        if manifest.get("production_execution_state") != "NOT_RUN":
            raise EvidenceContractError("production execution state cannot be promoted locally")
    else:
        if manifest.get("case_count") != len(identities) or manifest.get("case_ids") != list(identities):
            raise EvidenceContractError("corpus manifest case inventory differs from campaign")
        if campaign_type == "local-holdout":
            _bounded_text(manifest.get("separation"), "corpus manifest.separation")
            if manifest.get("independent") is not False:
                raise EvidenceContractError("local holdout corpus cannot claim independence")
            if manifest.get("external_holdout_state") != "NOT_RUN":
                raise EvidenceContractError("external holdout state cannot be promoted locally")
        elif manifest.get("provider_execution_state") != "NOT_RUN":
            raise EvidenceContractError("provider execution state cannot be promoted locally")


def _verify_development_manifest(
    manifest: Mapping[str, Any],
    *,
    document: Mapping[str, Any],
    scope: CampaignScope,
) -> None:
    exact_mapping(manifest, _DEVELOPMENT_MANIFEST_FIELDS, "development manifest")
    if manifest.get("schema_version") != 1:
        raise EvidenceContractError("development manifest schema_version must be 1")
    token(manifest.get("corpus_key"), "development manifest.corpus_key")
    if manifest.get("corpus_role") != "LOCAL_SELF_AUTHORED_DEVELOPMENT_INPUT":
        raise EvidenceContractError("development manifest corpus_role is invalid")
    if manifest.get("scope") != scope.as_dict():
        raise EvidenceContractError("development manifest scope differs from campaign scope")
    cases = _sorted_unique_cases(
        _array(manifest.get("cases"), "development manifest.cases"),
        "development manifest.cases",
    )
    for case in cases:
        exact_mapping(
            case,
            frozenset({"case_id", "skill_name", "request", "expected_status", "expected_error_code"}),
            f"development case {case['case_id']}",
        )
        token(case.get("skill_name"), f"development case {case['case_id']}.skill_name")
        if case.get("expected_status") not in {
            "EXECUTED",
            "BLOCKED",
            "REQUIRES_ADAPTER",
            "FAILED",
        }:
            raise EvidenceContractError(
                f"development case {case['case_id']}.expected_status is invalid"
            )
        expected_error = case.get("expected_error_code")
        if expected_error is not None:
            token(expected_error, f"development case {case['case_id']}.expected_error_code")
        strict_json_copy(case.get("request"), field=f"development case {case['case_id']}.request")
    declared_count = manifest.get("case_count")
    if isinstance(declared_count, bool) or declared_count != len(cases):
        raise EvidenceContractError("development manifest case_count is stale")
    computed = [canonical_digest(case) for case in cases]
    declared = manifest.get("case_digests")
    if declared != computed:
        raise EvidenceContractError("development manifest case_digests are stale")
    campaign_digests = document.get("development_case_digests")
    if campaign_digests != computed:
        raise EvidenceContractError(
            "campaign development_case_digests differ from the content-bound development manifest"
        )
    _bounded_strings(manifest.get("limitations"), "development manifest.limitations")


def _verify_target_manifest(
    manifest: Mapping[str, Any],
    *,
    evidence_root: Path,
    expected_aggregate: str,
    manifest_path: str,
) -> str:
    exact_mapping(manifest, _TARGET_MANIFEST_FIELDS, "target manifest")
    if manifest.get("schema_version") != 1:
        raise EvidenceContractError("target manifest schema_version must be 1")
    token(manifest.get("artifact_set"), "target manifest.artifact_set")
    if manifest.get("aggregate_algorithm") != _TARGET_AGGREGATE_ALGORITHM:
        raise EvidenceContractError("target manifest aggregate_algorithm is unsupported")
    _bounded_strings(manifest.get("scope"), "target manifest.scope")
    files = _array(manifest.get("files"), "target manifest.files", maximum=_MAX_TARGET_FILES)
    if not files:
        raise EvidenceContractError("target manifest.files must contain at least one entry")
    declared_count = manifest.get("file_count")
    declared_total = manifest.get("total_size_bytes")
    if isinstance(declared_count, bool) or declared_count != len(files):
        raise EvidenceContractError("target manifest file_count is stale")
    if (
        isinstance(declared_total, bool)
        or not isinstance(declared_total, int)
        or not 0 <= declared_total <= _MAX_TARGET_TOTAL_BYTES
    ):
        raise EvidenceContractError("target manifest total_size_bytes is invalid")
    lines: list[str] = []
    paths: list[str] = []
    entries: dict[str, Mapping[str, Any]] = {}
    observed_total = 0
    for index, item in enumerate(files):
        entry = exact_mapping(item, _TARGET_ENTRY_FIELDS, f"target manifest.files[{index}]")
        raw_digest = _sha256_hex(entry.get("sha256"), f"target manifest.files[{index}].sha256")
        reference = ContentReference.from_mapping(
            {
                "path": entry.get("path"),
                "sha256": f"sha256:{raw_digest}",
                "size_bytes": entry.get("size_bytes"),
                "media_type": "application/octet-stream",
            }
        )
        if reference.path == manifest_path:
            raise EvidenceContractError("target manifest cannot include itself")
        read_content_reference(reference, evidence_root)
        paths.append(reference.path)
        entries[reference.path] = entry
        observed_total += reference.size_bytes
        lines.append(f"{raw_digest}\t{reference.size_bytes}\t{reference.path}")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise EvidenceContractError("target manifest files must be path-sorted and unique")
    if observed_total != declared_total:
        raise EvidenceContractError("target manifest total_size_bytes is stale")
    aggregate = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    if manifest.get("aggregate_sha256") != aggregate:
        raise EvidenceContractError("target manifest aggregate_sha256 is stale")
    if f"sha256:{aggregate}" != expected_aggregate:
        raise EvidenceContractError("target manifest aggregate does not match target_artifact_digest")
    _verify_generated_install_manifests(
        manifest.get("generated_install_manifests"),
        entries=entries,
    )
    return _runtime_binding_digest(entries)


def _resolve_content_bindings(
    document: Mapping[str, Any],
    *,
    evidence_root: Path | None,
    scope: CampaignScope,
    campaign_type: str,
    target_artifact_digest: str,
    environment_digest: str,
    corpus_digest: str,
) -> str:
    if evidence_root is None:
        raise EvidenceContractError(
            "evidence_root is required to resolve content-addressed campaign bindings"
        )
    expected_binding_fields = (
        _CONTENT_BINDINGS | {"development_manifest"}
        if campaign_type == "local-holdout"
        else _CONTENT_BINDINGS
    )
    bindings = exact_mapping(document.get("bindings"), expected_binding_fields, "campaign bindings")
    target_manifest, target_reference = _bound_json(
        bindings["target_manifest"], evidence_root, "target manifest"
    )
    environment_manifest, environment_reference = _bound_json(
        bindings["environment_manifest"], evidence_root, "environment manifest"
    )
    corpus_manifest, corpus_reference = _bound_json(
        bindings["corpus_manifest"], evidence_root, "corpus manifest"
    )
    development_manifest: Mapping[str, Any] | None = None
    development_reference: ContentReference | None = None
    if campaign_type == "local-holdout":
        development_manifest, development_reference = _bound_json(
            bindings["development_manifest"], evidence_root, "development manifest"
        )
    paths = {
        target_reference.path,
        environment_reference.path,
        corpus_reference.path,
    }
    if development_reference is not None:
        paths.add(development_reference.path)
    if len(paths) != len(expected_binding_fields):
        raise EvidenceContractError("campaign content bindings must use distinct paths")
    runtime_binding_digest = _verify_target_manifest(
        target_manifest,
        evidence_root=evidence_root,
        expected_aggregate=target_artifact_digest,
        manifest_path=target_reference.path,
    )
    if environment_reference.sha256 != environment_digest:
        raise EvidenceContractError("environment manifest bytes do not match environment_digest")
    _verify_environment_manifest(environment_manifest, scope=scope)
    _verify_corpus_manifest(
        corpus_manifest,
        document=document,
        scope=scope,
        campaign_type=campaign_type,
        corpus_digest=corpus_digest,
    )
    if development_manifest is not None:
        _verify_development_manifest(
            development_manifest,
            document=document,
            scope=scope,
        )
    return runtime_binding_digest


def _common(
    document: Mapping[str, Any],
    campaign_type: str,
    *,
    evidence_root: Path | None,
) -> tuple[CampaignScope, str, str, str, str]:
    if document.get("schema_version") != "1.0":
        raise EvidenceContractError("campaign schema_version must be 1.0")
    if document.get("campaign_type") != campaign_type:
        raise EvidenceContractError(f"campaign_type must be {campaign_type}")
    scope = CampaignScope.from_mapping(document.get("scope"))
    token(document.get("executor_id"), "executor_id")
    controls = exact_mapping(document.get("controls"), _CONTROLS, "campaign controls")
    if controls["network_allowed"] is not False:
        raise EvidenceContractError("local campaign network_allowed must be false")
    if controls["provider_calls_allowed"] is not False:
        raise EvidenceContractError("local campaign provider_calls_allowed must be false")
    writes = controls["max_production_writes"]
    if isinstance(writes, bool) or writes != 0:
        raise EvidenceContractError("local campaign max_production_writes must be zero")
    target = digest(document.get("target_artifact_digest"), "target_artifact_digest")
    environment = digest(document.get("environment_digest"), "environment_digest")
    corpus = digest(document.get("corpus_digest"), "corpus_digest")
    runtime_binding = _resolve_content_bindings(
        document,
        evidence_root=evidence_root,
        scope=scope,
        campaign_type=campaign_type,
        target_artifact_digest=target,
        environment_digest=environment,
        corpus_digest=corpus,
    )
    return scope, target, environment, corpus, runtime_binding


def _array(value: object, label: str, *, maximum: int = 1000) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise EvidenceContractError(f"{label} must be an array of at most {maximum} entries")
    return value


def _sorted_unique_cases(cases: list[Any], label: str) -> tuple[Mapping[str, Any], ...]:
    if not cases:
        raise EvidenceContractError(f"{label} must contain at least one case")
    parsed: list[Mapping[str, Any]] = []
    identities: list[str] = []
    for index, value in enumerate(cases):
        if not isinstance(value, Mapping):
            raise EvidenceContractError(f"{label}[{index}] must be an object")
        identity = token(value.get("case_id"), f"{label}[{index}].case_id")
        identities.append(identity)
        parsed.append(value)
    if len(set(identities)) != len(identities):
        raise EvidenceContractError(f"{label} contains duplicate case_id values")
    if identities != sorted(identities):
        raise EvidenceContractError(f"{label} must be sorted by case_id")
    return tuple(parsed)


def _scoped_runtime_request(
    value: object,
    scope: CampaignScope,
    label: str,
) -> Mapping[str, Any]:
    request = strict_json_copy(value, field=label)
    if not isinstance(request, Mapping):
        raise EvidenceContractError(f"{label} must be an object")
    expected = {
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "correlation_id": scope.campaign_id,
        "policy_revision": scope.policy_revision,
        "source_revision": scope.source_revision,
    }
    mismatches = {
        field: {"expected": expected_value, "observed": request.get(field)}
        for field, expected_value in expected.items()
        if request.get(field) != expected_value
    }
    if mismatches:
        raise EvidenceContractError(f"{label} scope differs from campaign scope: {sorted(mismatches)}")
    return request


def _corpus_body(document: Mapping[str, Any]) -> Mapping[str, Any]:
    campaign_type = document.get("campaign_type")
    if campaign_type == "local-holdout":
        return {"campaign_type": campaign_type, "cases": document.get("cases")}
    if campaign_type == "provider-contract-simulation":
        return {
            "campaign_type": campaign_type,
            "provider_contract": document.get("provider_contract"),
            "fixtures": document.get("fixtures"),
        }
    if campaign_type == "production-like-rehearsal":
        return {"campaign_type": campaign_type, "rehearsal": document.get("rehearsal")}
    raise EvidenceContractError("campaign_type is unsupported")


def campaign_corpus_digest(document: object) -> str:
    """Return the deterministic corpus digest for authoring a campaign manifest."""

    if not isinstance(document, Mapping):
        raise EvidenceContractError("campaign must be an object")
    return canonical_digest(strict_json_copy(_corpus_body(document), field="campaign corpus"))


def _receipt(
    document: Mapping[str, Any],
    campaign_type: str,
    scope: CampaignScope,
    target: str,
    environment: str,
    corpus: str,
    runtime_binding: str,
    status: str,
    case_results: tuple[Mapping[str, Any], ...],
    limitations: tuple[str, ...],
    *,
    evidence_root: Path | None,
) -> CampaignReceipt:
    observed_runtime_binding = _resolve_content_bindings(
        document,
        evidence_root=evidence_root,
        scope=scope,
        campaign_type=campaign_type,
        target_artifact_digest=target,
        environment_digest=environment,
        corpus_digest=corpus,
    )
    if observed_runtime_binding != runtime_binding:
        raise EvidenceContractError("runtime binding changed during campaign execution")
    return CampaignReceipt.create(
        campaign_type=campaign_type,
        scope=scope,
        target_artifact_digest=target,
        environment_digest=environment,
        corpus_digest=corpus,
        runtime_binding_digest=runtime_binding,
        manifest_digest=canonical_digest(strict_json_copy(document, field="campaign")),
        status=status,
        case_results=case_results,
        limitations=limitations,
    )


def run_local_holdout(
    manifest: object,
    *,
    evidence_root: Path | None = None,
) -> CampaignReceipt:
    fields = _COMMON_FIELDS | {"development_case_digests", "cases"}
    document = exact_mapping(manifest, fields, "local holdout campaign")
    scope, target, environment, corpus, runtime_binding = _common(
        document, "local-holdout", evidence_root=evidence_root
    )
    if campaign_corpus_digest(document) != corpus:
        raise EvidenceContractError("local holdout corpus digest is stale")
    development_values = _array(document["development_case_digests"], "development_case_digests")
    if not development_values:
        raise EvidenceContractError("development_case_digests must contain at least one digest")
    development = {
        digest(value, f"development_case_digests[{index}]") for index, value in enumerate(development_values)
    }
    if len(development) != len(development_values):
        raise EvidenceContractError("development_case_digests contains duplicates")
    cases = _sorted_unique_cases(_array(document["cases"], "cases"), "cases")
    case_digests = {canonical_digest(strict_json_copy(case, field="holdout case")) for case in cases}
    overlap = sorted(development & case_digests)
    if overlap:
        return _receipt(
            document,
            "local-holdout",
            scope,
            target,
            environment,
            corpus,
            runtime_binding,
            "BLOCKED",
            ({"case_id": "corpus-separation", "status": "BLOCKED", "overlap": overlap},),
            ("SELF_ATTESTED", "INDEPENDENT_HOLDOUT_NOT_RUN", "CORPUS_OVERLAP"),
            evidence_root=evidence_root,
        )
    results: list[Mapping[str, Any]] = []
    for case in cases:
        exact_mapping(
            case,
            frozenset({"case_id", "skill_name", "request", "expected_status", "expected_error_code"}),
            f"holdout case {case['case_id']}",
        )
        skill_name = token(case["skill_name"], f"{case['case_id']}.skill_name")
        expected_status = case["expected_status"]
        expected_error = case["expected_error_code"]
        if expected_status not in {"EXECUTED", "BLOCKED", "REQUIRES_ADAPTER", "FAILED"}:
            raise EvidenceContractError(f"{case['case_id']} expected_status is invalid")
        if expected_error is not None:
            expected_error = token(expected_error, f"{case['case_id']}.expected_error_code")
        request = _scoped_runtime_request(case["request"], scope, f"{case['case_id']}.request")
        observed = dispatch_skill(skill_name, request)
        observed_error = None if observed["error"] is None else observed["error"]["code"]
        passed = observed["status"] == expected_status and observed_error == expected_error
        results.append(
            {
                "case_id": case["case_id"],
                "status": "PASSED" if passed else "FAILED",
                "case_digest": canonical_digest(case),
                "request_digest": canonical_digest(request),
                "observed_status": observed["status"],
                "observed_error_code": observed_error,
                "observed_result_digest": observed["result_digest"],
            }
        )
    status = "PASSED" if results and all(item["status"] == "PASSED" for item in results) else "FAILED"
    return _receipt(
        document,
        "local-holdout",
        scope,
        target,
        environment,
        corpus,
        runtime_binding,
        status,
        tuple(results),
        ("SELF_ATTESTED", "INDEPENDENT_HOLDOUT_NOT_RUN"),
        evidence_root=evidence_root,
    )


def _provider_case(
    engine: SoftwareFactoryEngine,
    contract: Mapping[str, Any],
    case: Mapping[str, Any],
    scope: CampaignScope,
) -> Mapping[str, Any]:
    exact_mapping(
        case,
        frozenset(
            {
                "case_id",
                "runtime_request",
                "provider_request",
                "provider_response",
                "expected_provider_state",
                "expected_mapped_error",
            }
        ),
        f"provider fixture {case['case_id']}",
    )
    request = strict_json_copy(case["provider_request"], field="provider request")
    response = exact_mapping(
        case["provider_response"], frozenset(_RESPONSE_FIELDS), "provider fixture response"
    )
    state = response["state"]
    if state not in {"SUCCEEDED", "FAILED", "UNKNOWN", "TIMEOUT"}:
        raise EvidenceContractError("provider response state is invalid")
    if response["provider_id"] != contract["provider_id"] or response["operation"] != contract["operation"]:
        raise EvidenceContractError("provider fixture identity differs from its adapter contract")
    if response["request_digest"] != canonical_digest(request):
        raise EvidenceContractError("provider response request digest is stale")
    artifact = response["artifact_digest"]
    native_error = response["error_code"]
    if state == "SUCCEEDED":
        digest(artifact, "provider response artifact_digest")
        if native_error is not None:
            raise EvidenceContractError("successful provider response cannot contain error_code")
        mapped_error = None
    else:
        if artifact is not None:
            raise EvidenceContractError("non-success provider response cannot contain artifact_digest")
        native_error = token(native_error, "provider response error_code")
        mapped_error = contract["error_map"].get(native_error, "PROVIDER_ERROR_UNMAPPED")
    runtime_request = _scoped_runtime_request(
        case["runtime_request"], scope, f"{case['case_id']}.runtime_request"
    )
    runtime_result = engine.execute_method(contract["method"], runtime_request)
    runtime_blocked = (
        runtime_result.status.value == "REQUIRES_ADAPTER"
        and runtime_result.error is not None
        and runtime_result.error.code == "ADAPTER_REQUIRED"
    )
    expected_error = case["expected_mapped_error"]
    if expected_error is not None:
        expected_error = token(expected_error, "expected_mapped_error")
    passed = state == case["expected_provider_state"] and mapped_error == expected_error and runtime_blocked
    return {
        "case_id": case["case_id"],
        "status": "PASSED" if passed else "FAILED",
        "case_digest": canonical_digest(case),
        "provider_request_digest": canonical_digest(request),
        "provider_response_digest": canonical_digest(response),
        "simulated_provider_state": state,
        "mapped_error": mapped_error,
        "bounded_runtime_state": runtime_result.status.value,
        "bounded_runtime_error": None if runtime_result.error is None else runtime_result.error.code,
        "runtime_request_digest": runtime_result.request_digest,
        "runtime_result_digest": runtime_result.result_digest,
        "skill_registry_digest": runtime_result.registry_digest,
        "capability_registry_digest": CAPABILITY_REGISTRY_DIGEST,
        "public_method_registry_digest": PUBLIC_METHOD_REGISTRY_DIGEST,
        "provider_calls_executed": False,
    }


def simulate_provider_contract(
    manifest: object,
    *,
    evidence_root: Path | None = None,
) -> CampaignReceipt:
    document = exact_mapping(
        manifest,
        _COMMON_FIELDS | {"provider_contract", "fixtures"},
        "provider contract campaign",
    )
    scope, target, environment, corpus, runtime_binding = _common(
        document, "provider-contract-simulation", evidence_root=evidence_root
    )
    if campaign_corpus_digest(document) != corpus:
        raise EvidenceContractError("provider fixture corpus digest is stale")
    contract = exact_mapping(
        document["provider_contract"],
        frozenset({"method", "provider_id", "operation", "response_fields", "error_map"}),
        "provider contract",
    )
    method = token(contract["method"], "provider contract.method")
    binding = PUBLIC_METHODS.get(method)
    if binding is None or binding.execution_mode != "requires_adapter":
        raise EvidenceContractError("provider contract method must be an exact requires_adapter API")
    token(contract["provider_id"], "provider contract.provider_id")
    token(contract["operation"], "provider contract.operation")
    if contract["operation"] != binding.action:
        raise EvidenceContractError("provider contract operation differs from the public method action")
    if contract["response_fields"] != list(_RESPONSE_FIELDS):
        raise EvidenceContractError("provider contract response_fields are not exact")
    error_map = contract["error_map"]
    if not isinstance(error_map, Mapping):
        raise EvidenceContractError("provider contract error_map must be an object")
    allowed_errors = set(binding.domain_errors) | set(binding.platform_errors)
    for native, mapped in error_map.items():
        token(native, "provider native error")
        if mapped not in allowed_errors:
            raise EvidenceContractError("provider error map targets an undeclared runtime error")
    cases = _sorted_unique_cases(_array(document["fixtures"], "fixtures"), "fixtures")
    engine = SoftwareFactoryEngine()
    results = tuple(_provider_case(engine, contract, case, scope) for case in cases)
    status = "PASSED" if results and all(item["status"] == "PASSED" for item in results) else "FAILED"
    return _receipt(
        document,
        "provider-contract-simulation",
        scope,
        target,
        environment,
        corpus,
        runtime_binding,
        status,
        results,
        ("SELF_ATTESTED", "FIXTURE_ONLY", "REAL_PROVIDER_NOT_RUN"),
        evidence_root=evidence_root,
    )


def rehearse_canary(
    manifest: object,
    *,
    evidence_root: Path | None = None,
) -> CampaignReceipt:
    document = exact_mapping(manifest, _COMMON_FIELDS | {"rehearsal"}, "production-like rehearsal campaign")
    scope, target, environment, corpus, runtime_binding = _common(
        document, "production-like-rehearsal", evidence_root=evidence_root
    )
    if campaign_corpus_digest(document) != corpus:
        raise EvidenceContractError("Canary rehearsal corpus digest is stale")
    rehearsal = exact_mapping(
        document["rehearsal"],
        frozenset(
            {
                "mode",
                "canary_population",
                "initial_state",
                "canary_state",
                "rollback_state",
                "events",
                "abort_error_basis_points",
                "expected_control_decision",
            }
        ),
        "Canary rehearsal",
    )
    if rehearsal["mode"] != "LOCAL_REHEARSAL" or rehearsal["canary_population"] != 0:
        raise EvidenceContractError("Canary rehearsal must use LOCAL_REHEARSAL with zero population")
    threshold = rehearsal["abort_error_basis_points"]
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 10_000:
        raise EvidenceContractError("abort_error_basis_points must be in [0, 10000]")
    if rehearsal["expected_control_decision"] not in {"PROMOTE", "ROLLBACK"}:
        raise EvidenceContractError("expected_control_decision must be PROMOTE or ROLLBACK")
    events = _sorted_unique_cases(_array(rehearsal["events"], "events"), "events")
    outcomes: list[str] = []
    for event in events:
        exact_mapping(event, frozenset({"case_id", "outcome"}), f"event {event['case_id']}")
        outcome = event["outcome"]
        if outcome not in {"SUCCESS", "ERROR", "UNKNOWN", "TIMEOUT"}:
            raise EvidenceContractError("Canary rehearsal event outcome is invalid")
        outcomes.append(outcome)
    initial = strict_json_copy(rehearsal["initial_state"], field="initial_state")
    canary = strict_json_copy(rehearsal["canary_state"], field="canary_state")
    rollback = strict_json_copy(rehearsal["rollback_state"], field="rollback_state")
    initial_digest = canonical_digest(initial)
    canary_digest = canonical_digest(canary)
    rollback_digest = canonical_digest(rollback)
    known = sum(outcome in {"SUCCESS", "ERROR"} for outcome in outcomes)
    failures = sum(outcome == "ERROR" for outcome in outcomes)
    error_basis_points = 10_000 if known == 0 else (failures * 10_000) // known
    uncertain = any(outcome in {"UNKNOWN", "TIMEOUT"} for outcome in outcomes)
    decision = "ROLLBACK" if uncertain or error_basis_points >= threshold else "PROMOTE"
    rollback_complete = rollback_digest == initial_digest
    canary_changed = canary_digest != initial_digest
    passed = (
        bool(events)
        and canary_changed
        and rollback_complete
        and decision == rehearsal["expected_control_decision"]
    )
    result = {
        "case_id": "canary-rehearsal",
        "status": "PASSED" if passed else "BLOCKED",
        "initial_state_digest": initial_digest,
        "canary_state_digest": canary_digest,
        "rollback_state_digest": rollback_digest,
        "event_set_digest": canonical_digest(list(events)),
        "error_basis_points": error_basis_points,
        "uncertain_outcome": uncertain,
        "control_decision": decision,
        "rollback_complete": rollback_complete,
        "network_calls_executed": False,
        "provider_calls_executed": False,
        "production_writes_executed": 0,
    }
    return _receipt(
        document,
        "production-like-rehearsal",
        scope,
        target,
        environment,
        corpus,
        runtime_binding,
        "PASSED" if passed else "BLOCKED",
        (result,),
        ("SELF_ATTESTED", "SYNTHETIC_ONLY", "PRODUCTION_NOT_RUN"),
        evidence_root=evidence_root,
    )


def run_campaign(
    manifest: object,
    *,
    evidence_root: Path | None = None,
) -> CampaignReceipt:
    if not isinstance(manifest, Mapping):
        raise EvidenceContractError("campaign must be an object")
    campaign_type = manifest.get("campaign_type")
    if campaign_type == "local-holdout":
        return run_local_holdout(manifest, evidence_root=evidence_root)
    if campaign_type == "provider-contract-simulation":
        return simulate_provider_contract(manifest, evidence_root=evidence_root)
    if campaign_type == "production-like-rehearsal":
        return rehearse_canary(manifest, evidence_root=evidence_root)
    raise EvidenceContractError("campaign_type is unsupported")


def replay_campaign(
    manifest: object,
    receipt: object,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    parsed = CampaignReceipt.from_mapping(receipt)
    observed_manifest_digest = canonical_digest(strict_json_copy(manifest, field="campaign"))
    if observed_manifest_digest != parsed.manifest_digest:
        return {
            "schema_version": "1.0",
            "status": "BLOCKED",
            "reason": "MANIFEST_DIGEST_MISMATCH",
            "manifest_digest": observed_manifest_digest,
            "expected_manifest_digest": parsed.manifest_digest,
            "external_states": dict(EXTERNAL_STATES),
        }
    replayed = run_campaign(manifest, evidence_root=evidence_root)
    matched = (
        replayed.receipt_digest == parsed.receipt_digest
        and replayed.execution_digest == parsed.execution_digest
    )
    return {
        "schema_version": "1.0",
        "status": "MATCHED" if matched else "BLOCKED",
        "reason": None if matched else "REPLAY_DIGEST_MISMATCH",
        "manifest_digest": observed_manifest_digest,
        "expected_manifest_digest": parsed.manifest_digest,
        "expected_receipt_digest": parsed.receipt_digest,
        "observed_receipt_digest": replayed.receipt_digest,
        "expected_execution_digest": parsed.execution_digest,
        "observed_execution_digest": replayed.execution_digest,
        "external_states": dict(EXTERNAL_STATES),
    }
