"""Commercial capability service facade and compatibility status APIs."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .authority import AuthorityProof
from .canonical import digest_object, strict_json_loads
from .contracts import CapabilityLease, Invocation, PolicyDecision
from .errors import AuthorizationError, ContractError
from .runtime import CommercialCapabilityRuntime, RuntimeReceipt

_EXPECTED_ARCHIVE_SHA256 = "7a73cf924f4ebab3eddba327ba4feeb64b8575e39f2baf03fc53315cbc868380"
_EXPECTED_ARCHIVE_BYTES = 161_254
_EXPECTED_MANIFEST_SHA256 = "84e697c6ce821f9afcc0f52831c1d0da3105102d8a2bcc0ac8333286f688e142"
_EXPECTED_HANDLER_SOURCE_SHA256 = "c55480087a8c5644e49375031882b5a4928f71df93eaf73a55c472598e32d3d6"
_EXPECTED_LOCAL_ALGORITHM_SOURCE_SHA256 = (
    "78c385a58eb5c0ccb9e090cc9ebe7d2643ad8225759fd2ff0c2a8a143af22c15"
)
_EXPECTED_COMPILED_CATALOG_SHA256 = (
    "25b8912a9dcf425982af962ac08cb3203660c7ad5e66887f8a9054a9cfa83178"
)
_EXPECTED_WRAPPER_TREE_SHA256 = (
    "062c3abac46b5364dd08f962524d60ef2ef1ef430199d4a66748bf534c761ae1"
)
_KERNEL_NAMES = (
    "K1-skill-runtime",
    "K2-repository-intelligence",
    "K3-transformation",
    "K4-build-execution",
    "K5-verification",
    "K6-security-governance",
    "K7-database-data",
    "K8-observability-evolution",
)
_CATALOG_RELATIVE = Path("docs/commercial-capability-expansion/COMPILED_SKILL_CATALOG.json")
_RECEIPT_RELATIVE = Path("docs/commercial-capability-expansion/QUALIFICATION_RECEIPT.json")
_WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
_RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
_MASTER_SKILL_ID = "elmos-commercial-capability-expansion"
_WRAPPER_FILES = ("SKILL.md", "compiled-contract.json", "agents/openai.yaml")
_MAX_PROJECTION_FILE_BYTES = 2 * 1024 * 1024
_MAX_WRAPPER_FILE_BYTES = 256 * 1024
_MAX_PROJECTION_TOTAL_BYTES = 16 * 1024 * 1024
_SOURCE_SERVICE_RELATIVE = Path(
    "engines/commercial-capability-expansion-engine/"
    "src/elmos_commercial_expansion/service.py"
)


def _validate_repository_root(repository_root: Path) -> Path:
    if not isinstance(repository_root, Path):
        raise ContractError(
            "repository_root must be an absolute pathlib.Path",
            code="REPOSITORY_ROOT_INVALID",
        )
    if (
        not repository_root.is_absolute()
        or repository_root == Path(repository_root.anchor)
        or ".." in repository_root.parts
    ):
        raise ContractError(
            "repository_root must be an absolute non-root path without traversal",
            code="REPOSITORY_ROOT_INVALID",
        )
    current = Path(repository_root.anchor)
    for component in repository_root.parts[1:]:
        current /= component
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise ContractError(
                "repository_root must identify an existing directory",
                code="REPOSITORY_ROOT_INVALID",
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ContractError(
                "repository_root components must be non-symlink directories",
                code="REPOSITORY_ROOT_INVALID",
            )
    return repository_root


def _source_checkout_repository_root() -> Path:
    module_path = Path(__file__).absolute()
    for candidate in module_path.parents:
        if candidate / _SOURCE_SERVICE_RELATIVE == module_path:
            return _validate_repository_root(candidate)
    raise ContractError(
        "installed packages require an explicit repository_root",
        code="REPOSITORY_ROOT_REQUIRED",
    )


def _select_repository_root(repository_root: Path | None) -> Path:
    if repository_root is None:
        return _source_checkout_repository_root()
    return _validate_repository_root(repository_root)


def _read_stable_file(
    path: Path,
    *,
    maximum: int,
    expected_size: int | None = None,
) -> bytes:
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size > maximum
        or (expected_size is not None and before.st_size != expected_size)
    ):
        raise ContractError("managed file is not a bounded regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise ContractError("managed file identity changed during read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise ContractError("managed file exceeds its read bound")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise ContractError("managed file changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _manifest(repository_root: Path) -> Mapping[str, Any]:
    path = repository_root / "skills/elmos-commercial-capability-expansion-skills-v2.0.0/manifest.json"
    try:
        document = _read_stable_file(path, maximum=1_048_576)
    except (ContractError, OSError):
        return {}
    if hashlib.sha256(document).hexdigest() != _EXPECTED_MANIFEST_SHA256:
        return {}
    value = strict_json_loads(document)
    return value if isinstance(value, Mapping) else {}


def _registry_facts(repository_root: Path | None = None) -> dict[str, Any]:
    from .contracts import SkillInputContract
    from .kernels import _exact_registry

    EXACT_SKILL_HANDLERS, EXACT_SKILL_INPUT_CONTRACTS = _exact_registry()

    repository = _select_repository_root(repository_root)
    manifest = _manifest(repository)
    skills = manifest.get("skills", ()) if isinstance(manifest, Mapping) else ()
    manifest_by_id: dict[str, Mapping[str, Any]] = {}
    if isinstance(skills, (tuple, list)):
        for item in skills:
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                manifest_by_id[item["id"]] = item
    registry_ids = tuple(sorted(EXACT_SKILL_HANDLERS))
    manifest_ids = tuple(sorted(manifest_by_id))
    callable_ids = {id(EXACT_SKILL_HANDLERS[item]) for item in registry_ids}
    handler_path = Path(__file__).parent / "kernels/exact_handlers.py"
    algorithm_path = Path(__file__).parent / "kernels/_local_algorithms.py"
    handler_source_sha256 = None
    algorithm_source_sha256 = None
    try:
        handler_source = _read_stable_file(handler_path, maximum=2 * 1024 * 1024)
    except (ContractError, OSError):
        pass
    else:
        handler_source_sha256 = hashlib.sha256(handler_source).hexdigest()
    try:
        algorithm_source = _read_stable_file(algorithm_path, maximum=2 * 1024 * 1024)
    except (ContractError, OSError):
        pass
    else:
        algorithm_source_sha256 = hashlib.sha256(algorithm_source).hexdigest()
    contract_documents = {
        item: {
            "ephemeral_sensitive_fields": sorted(
                EXACT_SKILL_INPUT_CONTRACTS[item].ephemeral_sensitive_fields
            ),
            "optional": sorted(EXACT_SKILL_INPUT_CONTRACTS[item].optional),
            "required": sorted(EXACT_SKILL_INPUT_CONTRACTS[item].required),
        }
        for item in registry_ids
    }
    binding_documents = {
        item: {
            "callable_name": getattr(EXACT_SKILL_HANDLERS[item], "__name__", None),
            "kernel": manifest_by_id.get(item, {}).get("kernel"),
            "objective_digest": digest_object(
                manifest_by_id.get(item, {}).get("objective"),
                domain="commercial-skill-objective",
            ),
            "skill_id": getattr(EXACT_SKILL_HANDLERS[item], "__elmos_exact_skill_id__", None),
        }
        for item in registry_ids
    }
    manifest_bindings_valid = all(
        isinstance(manifest_by_id[item].get("objective"), str)
        and bool(manifest_by_id[item]["objective"].strip())
        and manifest_by_id[item].get("kernel") in _KERNEL_NAMES
        and isinstance(manifest_by_id[item].get("path"), str)
        and Path(manifest_by_id[item]["path"]).parent.name == item
        for item in registry_ids
        if item in manifest_by_id
    )
    exact = (
        len(registry_ids) == 85
        and registry_ids == manifest_ids
        and set(EXACT_SKILL_INPUT_CONTRACTS) == set(registry_ids)
        and len(callable_ids) == len(registry_ids)
        and handler_source_sha256 == _EXPECTED_HANDLER_SOURCE_SHA256
        and algorithm_source_sha256 == _EXPECTED_LOCAL_ALGORITHM_SOURCE_SHA256
        and manifest_bindings_valid
        and all(
            callable(EXACT_SKILL_HANDLERS[item])
            and getattr(EXACT_SKILL_HANDLERS[item], "__elmos_exact_skill_id__", None) == item
            and isinstance(EXACT_SKILL_INPUT_CONTRACTS[item], SkillInputContract)
            for item in registry_ids
        )
    )
    manifest_digest = "sha256:" + _EXPECTED_MANIFEST_SHA256 if manifest_ids else None
    registry_digest = digest_object(
        {
            "handlers": registry_ids,
            "handler_bindings": binding_documents,
            "handler_source_sha256": handler_source_sha256,
            "local_algorithm_source_sha256": algorithm_source_sha256,
            "input_contracts": contract_documents,
            "manifest_digest": manifest_digest,
            "manifest_skills": manifest_ids,
        },
        domain="commercial-exact-registry",
    )
    return {
        "exact": exact,
        "registry_ids": registry_ids,
        "manifest_by_id": manifest_by_id,
        "input_contracts": contract_documents,
        "manifest_digest": manifest_digest,
        "handler_source_sha256": handler_source_sha256,
        "local_algorithm_source_sha256": algorithm_source_sha256,
        "registry_digest": registry_digest,
    }


def _archive_status(repository_root: Path) -> dict[str, Any]:
    candidates = (
        Path("skills/subskills/elmos-commercial-capability-expansion-skills-v2.0.0.zip"),
        Path("skills/subskills/sub/elmos-commercial-capability-expansion-skills-v2.0.0.zip"),
    )
    for relative in candidates:
        try:
            document = _read_stable_file(
                repository_root / relative,
                maximum=2 * 1024 * 1024,
                expected_size=_EXPECTED_ARCHIVE_BYTES,
            )
        except (ContractError, OSError):
            continue
        sha256 = hashlib.sha256(document).hexdigest()
        return {
            "present": True,
            "digest_matches": sha256 == _EXPECTED_ARCHIVE_SHA256,
            "sha256": sha256,
        }
    return {"present": False, "digest_matches": False, "sha256": None}


def _read_projection_file(
    root: Path,
    relative: Path,
    *,
    maximum: int = _MAX_PROJECTION_FILE_BYTES,
) -> bytes:
    path = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise ContractError("projection paths must not contain symlinks")
    return _read_stable_file(path, maximum=maximum)


def _projection_tree_digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(b"elmos-tree-sha256-v1\0")
    for relative in sorted(files):
        encoded = relative.encode("utf-8")
        content = files[relative]
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _projection_status(
    registry_ids: tuple[str, ...],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Verify the installed dual-root projection without trusting its receipt."""

    repository = _select_repository_root(root)
    try:
        catalog_bytes = _read_projection_file(repository, _CATALOG_RELATIVE)
        receipt_bytes = _read_projection_file(repository, _RECEIPT_RELATIVE)
        catalog = strict_json_loads(catalog_bytes)
        receipt = strict_json_loads(receipt_bytes)
        if not isinstance(catalog, Mapping) or not isinstance(receipt, Mapping):
            raise ContractError("projection catalog and receipt must be objects")
        catalog_skills = catalog.get("skills")
        if not isinstance(catalog_skills, (tuple, list)):
            raise ContractError("compiled catalog skills must be an array")
        catalog_names: list[str] = []
        for item in catalog_skills:
            if isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str):
                    catalog_names.append(name)
        catalog_ids = tuple(sorted(catalog_names))
        if catalog_ids != registry_ids or catalog.get("skill_count") != 85:
            raise ContractError("compiled catalog does not bind all exact Skills")
        package = catalog.get("package")
        if not isinstance(package, Mapping) or package.get("archive_sha256") != _EXPECTED_ARCHIVE_SHA256:
            raise ContractError("compiled catalog archive binding is invalid")
        compiled_catalog = receipt.get("compiled_catalog")
        wrappers_receipt = receipt.get("installed_wrappers")
        if not isinstance(compiled_catalog, Mapping) or not isinstance(wrappers_receipt, Mapping):
            raise ContractError("projection receipt is incomplete")
        catalog_sha256 = hashlib.sha256(catalog_bytes).hexdigest()
        if catalog_sha256 != _EXPECTED_COMPILED_CATALOG_SHA256:
            raise ContractError("compiled catalog differs from its repository-owned pin")
        if (
            compiled_catalog.get("path") != _CATALOG_RELATIVE.as_posix()
            or compiled_catalog.get("sha256") != catalog_sha256
            or compiled_catalog.get("tree_sha256")
            != _projection_tree_digest({_CATALOG_RELATIVE.name: catalog_bytes})
        ):
            raise ContractError("compiled catalog receipt binding is invalid")
        if (
            wrappers_receipt.get("master_count") != 1
            or wrappers_receipt.get("skill_count") != 85
            or wrappers_receipt.get("files_per_wrapper") != 3
            or wrappers_receipt.get("workspace_root") != _WORKSPACE_SKILLS_RELATIVE.as_posix()
            or wrappers_receipt.get("runtime_root") != _RUNTIME_SKILLS_RELATIVE.as_posix()
            or wrappers_receipt.get("dual_roots_byte_identical") is not True
        ):
            raise ContractError("installed wrapper receipt metadata is invalid")
        total_projection_bytes = len(catalog_bytes) + len(receipt_bytes)
        wrapper_payloads: dict[str, bytes] = {}
        for skill_id in (_MASTER_SKILL_ID, *registry_ids):
            contract_bytes: bytes | None = None
            for relative_name in _WRAPPER_FILES:
                relative = Path(skill_id) / relative_name
                workspace_bytes = _read_projection_file(
                    repository,
                    _WORKSPACE_SKILLS_RELATIVE / relative,
                    maximum=_MAX_WRAPPER_FILE_BYTES,
                )
                runtime_bytes = _read_projection_file(
                    repository,
                    _RUNTIME_SKILLS_RELATIVE / relative,
                    maximum=_MAX_WRAPPER_FILE_BYTES,
                )
                total_projection_bytes += len(workspace_bytes) + len(runtime_bytes)
                if total_projection_bytes > _MAX_PROJECTION_TOTAL_BYTES:
                    raise ContractError("installed projection exceeds its aggregate read bound")
                if workspace_bytes != runtime_bytes:
                    raise ContractError("dual-root wrapper bytes differ")
                wrapper_payloads[f"{skill_id}/{relative_name}"] = workspace_bytes
                if relative_name == "compiled-contract.json":
                    contract_bytes = workspace_bytes
            if contract_bytes is None:
                raise ContractError("compiled wrapper contract is missing")
            contract = strict_json_loads(contract_bytes)
            if (
                not isinstance(contract, Mapping)
                or not isinstance(contract.get("skill"), Mapping)
                or contract["skill"].get("name") != skill_id
            ):
                raise ContractError("compiled wrapper contract identity is invalid")
        wrapper_tree_sha256 = _projection_tree_digest(wrapper_payloads)
        if wrapper_tree_sha256 != _EXPECTED_WRAPPER_TREE_SHA256:
            raise ContractError("installed wrappers differ from their repository-owned pin")
        if wrappers_receipt.get("tree_sha256") != wrapper_tree_sha256:
            raise ContractError("installed wrapper receipt binding is invalid")
        if receipt.get("runtime_binding") != catalog.get("runtime_binding"):
            raise ContractError("projection runtime binding differs between catalog and receipt")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, Mapping) or evidence != {
            "local_runtime": "NOT_RUN",
            "external_runtime": "NOT_RUN",
            "provider_database_stream_lakehouse": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }:
            raise ContractError("projection receipt overstates certification")
    except (ContractError, KeyError, OSError, TypeError, ValueError):
        return {"status": "MISSING_OR_INVALID", "valid": False}
    return {
        "status": "PINNED_VERIFIED",
        "valid": True,
        "catalog_sha256": catalog_sha256,
        "wrapper_tree_sha256": wrapper_tree_sha256,
        "wrapper_count": 86,
    }


def _qualification_status(registry_digest: str, repository_root: Path) -> dict[str, Any]:
    """Do not promote from a caller-writable receipt without a controlled runner."""

    path = (
        repository_root
        / "engines/commercial-capability-expansion-engine/qualification/local-qualification.json"
    )
    try:
        receipt = strict_json_loads(_read_stable_file(path, maximum=1_048_576))
    except (ContractError, OSError):
        return {"status": "NOT_RUN", "valid": False, "receipt": None}
    observed = isinstance(receipt, Mapping) and receipt.get("registry_digest") == registry_digest
    return {
        "status": "UNTRUSTED_RECEIPT_PRESENT" if observed else "INVALID",
        "valid": False,
        "receipt": None,
    }


def get_commercial_status(repository_root: Path | None = None) -> dict[str, Any]:
    repository = _select_repository_root(repository_root)
    facts = _registry_facts(repository)
    archive = _archive_status(repository)
    projection = _projection_status(facts["registry_ids"], root=repository)
    qualification = _qualification_status(facts["registry_digest"], repository)
    ready_structure = bool(facts["exact"] and archive["digest_matches"] and projection["valid"])
    if not ready_structure:
        status = "NOT_READY"
    elif qualification["valid"]:
        status = "LOCAL_EXECUTED_SELF_ATTESTED"
    else:
        status = "LOCAL_BOUNDED_UNQUALIFIED"
    return {
        "engine": "elmos-commercial-capability-expansion-engine",
        "version": "2.0.0",
        "status": status,
        "kernels_count": len(_KERNEL_NAMES),
        "skills_count": len(facts["registry_ids"]),
        "exact_registry": facts["exact"],
        "registry_digest": facts["registry_digest"],
        "manifest_digest": facts["manifest_digest"],
        "handler_source_sha256": facts["handler_source_sha256"],
        "local_algorithm_source_sha256": facts["local_algorithm_source_sha256"],
        "archive": archive,
        "projection": projection,
        "qualification": qualification,
        "local_evidence_ceiling": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_provider_status": "NOT_RUN",
        "native_runtime_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "production_readiness_status": "NOT_READY",
        "operational_controls": {
            "authenticated_external_journal_anchor": "NOT_CONFIGURED",
            "durable_tenant_storage_quota": "NOT_CONFIGURED",
            "retention_and_garbage_collection": "NOT_CONFIGURED",
            "deployment_reconciliation": "NOT_RUN",
        },
    }


def list_capability_kernels(repository_root: Path | None = None) -> list[dict[str, Any]]:
    repository = _select_repository_root(repository_root)
    facts = _registry_facts(repository)
    projection = _projection_status(facts["registry_ids"], root=repository)
    manifest_by_id: Mapping[str, Mapping[str, Any]] = facts["manifest_by_id"]
    input_contracts: Mapping[str, Mapping[str, Any]] = facts["input_contracts"]
    handlers = set(facts["registry_ids"])
    result: list[dict[str, Any]] = []
    for kernel in _KERNEL_NAMES:
        manifest_ids = sorted(
            skill_id for skill_id, item in manifest_by_id.items() if item.get("kernel") == kernel
        )
        exact_ids = sorted(set(manifest_ids).intersection(handlers))
        result.append(
            {
                "kernel": kernel,
                "manifest_skill_count": len(manifest_ids),
                "exact_handler_count": len(exact_ids),
                "exact_registry_complete": exact_ids == manifest_ids,
                "skills": exact_ids,
                "input_contracts": {
                    skill_id: input_contracts[skill_id]
                    for skill_id in exact_ids
                },
                "status": (
                    "LOCAL_BOUNDED_UNQUALIFIED"
                    if exact_ids == manifest_ids and projection["valid"]
                    else "NOT_READY"
                ),
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            }
        )
    return result


class CommercialCapabilityExpansionService:
    """Thin facade; it never fabricates execution, evidence or provenance."""

    def __init__(self, runtime: CommercialCapabilityRuntime | None = None, *_args: object, **_kwargs: object) -> None:
        self.runtime = runtime

    def execute(
        self,
        invocation: Invocation,
        *,
        inputs: Mapping[str, Any],
        decision: PolicyDecision,
        lease: CapabilityLease,
        authority_proof: AuthorityProof | None,
    ) -> RuntimeReceipt:
        if self.runtime is None:
            raise AuthorizationError(
                "commercial runtime authority is not configured",
                code="RUNTIME_NOT_CONFIGURED",
            )
        return self.runtime.execute(
            invocation,
            inputs=inputs,
            decision=decision,
            lease=lease,
            authority_proof=authority_proof,
        )

    def run_commercial_workflow(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        """Legacy orchestration entrypoint retained as an explicit fail-closed result."""

        return {
            "status": "NOT_RUN",
            "outcome": "BLOCKED",
            "reason": "SIGNED_EXACT_INVOCATION_REQUIRED",
            "external_provider_status": "NOT_RUN",
            "native_runtime_status": "NOT_RUN",
            "independent_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
