from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .dotnet_target import render_dotnet
from .java_target import render_java
from .models import SynthesisRequest, request_payload, sha256_json
from .python_target import render_python
from .rendering import clean, pretty_json


class WorkspaceConflictError(RuntimeError):
    """Raised when generation would overwrite unowned or modified content."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise WorkspaceConflictError(f"UNSAFE_GENERATED_PATH:{relative}")
    target = root.joinpath(*candidate.parts)
    resolved_parent = target.parent.resolve(strict=False)
    if root.resolve(strict=False) not in (resolved_parent, *resolved_parent.parents):
        raise WorkspaceConflictError(f"GENERATED_PATH_ESCAPE:{relative}")
    return target


def _target_directory(language: str) -> str:
    return {"java": "java", "python": "python", "csharp": "dotnet"}[language]


def _render_psir(request: SynthesisRequest) -> dict[str, Any]:
    payload = request_payload(request.raw)
    return {
        "schema_version": "1.0.0",
        "project": payload["project"],
        "requirements": payload["requirements"],
        "acceptance_criteria": payload["acceptance_criteria"],
        "actors": payload.get("actors", []),
        "constraints": payload.get("constraints", []),
        "assumptions": payload.get("assumptions", []),
        "quality_attributes": payload.get("quality_attributes", []),
        "open_questions": payload.get("open_questions", []),
    }


def _render_blueprint(request: SynthesisRequest) -> dict[str, Any]:
    approval_hash = str(request.raw["approval"]["approved_payload_sha256"])
    applications = [
        {
            "id": f"APP-{target.language.upper()}",
            "language": target.language,
            "profile": f"{target.framework}-{target.runtime}",
            "port": target.port,
            "storage": "in-memory",
        }
        for target in request.targets
    ]
    return {
        "schema_version": "1.0.0",
        "project": {
            "id": request.raw["project"]["id"],
            "name": request.project_name,
            "requirements_baseline_ref": f"sha256:{approval_hash}",
            "architecture_baseline_ref": f"sha256:{sha256_json(applications)}",
        },
        "applications": applications,
        "repository": {
            "mode": "polyglot-monorepo",
            "generated_areas": [_target_directory(target.language) for target in request.targets],
        },
        "runtime": {target.language: target.runtime for target in request.targets},
        "dependencies": [
            {"target": "java", "catalog": "spring-boot-3.5.3"},
            {"target": "python", "catalog": "fastapi-0.116.1"},
            {"target": "csharp", "catalog": "aspnet-core-10.0.9"},
        ],
        "build": {"reproducible_intent": True, "external_dependency_resolution_evidence": "NOT_RUN"},
        "configuration": [
            {"key": "APP_NAME", "secret": False},
            {"key": "APP_ENV", "secret": False},
            {"key": "PORT", "secret": False},
            {"key": "LOG_LEVEL", "secret": False},
        ],
        "quality": {"unit_tests": True, "lint": True, "type_check": True, "startup_probe": True},
        "generation_units": [
            {
                "id": f"GEN-{target.language.upper()}",
                "kind": "project",
                "target_path": _target_directory(target.language),
                "ownership": "managed",
                "source_refs": ["REQ-CRUD-001", "REQ-HEALTH-001", "REQ-DELIVERY-001"],
            }
            for target in request.targets
        ],
    }


def _compose(request: SynthesisRequest) -> str:
    blocks: list[str] = ["services:"]
    for target in request.targets:
        directory = _target_directory(target.language)
        blocks.extend(
            [
                f"  {target.language}:",
                f"    build: ./{directory}",
                "    environment:",
                f"      APP_NAME: {request.project_name}-{target.language}",
                "      APP_ENV: development",
                f"      PORT: \"{target.port}\"",
                f"    ports: [\"{target.port}:{target.port}\"]",
                "    read_only: true",
                "    tmpfs: [/tmp]",
                "    security_opt: [no-new-privileges:true]",
            ]
        )
    return "\n".join(blocks) + "\n"


def _root_readme(request: SynthesisRequest) -> str:
    target_rows = "\n".join(
        (
            f"| {target.language} | {target.framework} {target.runtime} | "
            f"`{_target_directory(target.language)}/` | {target.port} |"
        )
        for target in request.targets
    )
    build_commands = []
    if any(target.language == "java" for target in request.targets):
        build_commands.append("(cd java && mvn -B test)")
    if any(target.language == "python" for target in request.targets):
        build_commands.append(
            "(cd python && uv sync --python 3.12 && uv run pytest "
            "&& uv run ruff check src tests && uv run mypy src)"
        )
    if any(target.language == "csharp" for target in request.targets):
        build_commands.append("(cd dotnet && dotnet restore --use-lock-file && dotnet test)")
    commands = "\n".join(build_commands)
    return clean(
        f"""
        # {request.project_name}

        {request.description}

        This workspace was generated from an approved, hash-bound ELMOS Project Synthesis
        requirement baseline. Generators did not consume raw conversation text directly.

        | Target | Profile | Directory | Port |
        |---|---|---|---:|
        {target_rows}

        ## Verify

        ```bash
        {commands}
        ```

        Or run `elmos-project-synthesis verify --workspace .` from the engine environment.
        Use `docker compose up --build` only after resolving and approving container image
        digests in your delivery policy.

        ## Generated contracts

        - `requirements/approved-request.json`: immutable approved input.
        - `requirements/psir.json`: normalized Project Synthesis IR.
        - `requirements/project-blueprint.json`: selected language/runtime/build profiles.
        - `.elmos/generation-manifest.json`: ownership, hashes, trace links, and claim boundary.

        ## Current boundary

        The generated starter uses in-memory persistence and intentionally omits authentication
        until a durable data profile, identity provider, tenant model, and authorization policy
        are explicitly selected. Local generation is `GENERATED`; production delivery and all
        external certification remain `NOT_RUN`.
        """
    )


def render_workspace(request: SynthesisRequest) -> dict[str, str]:
    files: dict[str, str] = {
        "README.md": _root_readme(request),
        "docker-compose.yml": _compose(request),
        "requirements/approved-request.json": pretty_json(request.raw),
        "requirements/psir.json": pretty_json(_render_psir(request)),
        "requirements/project-blueprint.json": pretty_json(_render_blueprint(request)),
        "docs/traceability.md": clean(
            """
            # Requirement traceability

            | Requirement | Generated verification |
            |---|---|
            | REQ-CRUD-001 | Target API tests create and list the primary entity. |
            | REQ-HEALTH-001 | Target API tests and startup probes call `GET /health`. |
            | REQ-DELIVERY-001 | Build, test, configuration, CI, container, Kubernetes, OpenAPI, and evidence assets. |

            Missing production identity, persistence, image-digest, deployment, SLO, restore,
            and external gate evidence remains explicit and cannot be inferred from this table.
            """
        ),
    }
    for target in request.targets:
        rendered = {
            "java": render_java,
            "python": render_python,
            "csharp": render_dotnet,
        }[target.language](request, target.port)
        prefix = _target_directory(target.language)
        for relative, content in rendered.items():
            path = f"{prefix}/{relative}"
            if path in files:
                raise WorkspaceConflictError(f"DUPLICATE_GENERATED_PATH:{path}")
            files[path] = content
    manifest_entries = [
        {
            "path": path,
            "sha256": _sha256_text(content),
            "ownership": "managed",
            "source_refs": ["approved-request", "PG001-PG170"],
        }
        for path, content in sorted(files.items())
    ]
    manifest = {
        "schema_version": "1.0.0",
        "engine": "elmos.project-synthesis",
        "engine_version": "1.0.0",
        "request_sha256": request.request_hash,
        "approved_payload_sha256": request.raw["approval"]["approved_payload_sha256"],
        "status": "GENERATED",
        "production_delivery_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "external_evidence_status": "NOT_RUN",
        "files": manifest_entries,
    }
    files[".elmos/generation-manifest.json"] = pretty_json(manifest)
    return files


def _load_existing_manifest(root: Path) -> dict[str, Any] | None:
    path = root / ".elmos" / "generation-manifest.json"
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceConflictError("EXISTING_MANIFEST_INVALID") from error
    if not isinstance(loaded, dict):
        raise WorkspaceConflictError("EXISTING_MANIFEST_INVALID")
    return loaded


def _assert_existing_files_unmodified(root: Path, manifest: dict[str, Any]) -> None:
    if (
        manifest.get("engine") != "elmos.project-synthesis"
        or manifest.get("engine_version") != "1.0.0"
        or manifest.get("status") != "GENERATED"
    ):
        raise WorkspaceConflictError("EXISTING_MANIFEST_IDENTITY_INVALID")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise WorkspaceConflictError("EXISTING_MANIFEST_FILES_INVALID")
    seen_paths: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or entry["path"] in seen_paths
            or not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise WorkspaceConflictError("EXISTING_MANIFEST_ENTRY_INVALID")
        seen_paths.add(entry["path"])
        target = _safe_path(root, entry["path"])
        if not target.is_file():
            raise WorkspaceConflictError(f"MANAGED_FILE_MISSING:{entry['path']}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry.get("sha256"):
            raise WorkspaceConflictError(f"MANAGED_FILE_MODIFIED:{entry['path']}")


def _write_text_atomic(target: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.elmos-",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def generate_workspace(request_mapping: dict[str, Any], output: Path) -> dict[str, Any]:
    request = SynthesisRequest.from_mapping(request_mapping, require_approval=True)
    root = output.expanduser().resolve(strict=False)
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise WorkspaceConflictError("BROAD_OUTPUT_TARGET_REJECTED")
    existing_manifest = _load_existing_manifest(root) if root.exists() else None
    if root.exists() and any(root.iterdir()) and existing_manifest is None:
        raise WorkspaceConflictError("NONEMPTY_UNMANAGED_OUTPUT_REJECTED")
    if existing_manifest is not None:
        _assert_existing_files_unmodified(root, existing_manifest)
        if existing_manifest.get("request_sha256") != request.request_hash:
            raise WorkspaceConflictError("REQUEST_BASELINE_CHANGED_REQUIRES_NEW_OUTPUT")
    rendered = render_workspace(request)
    for relative, content in sorted(rendered.items()):
        target = _safe_path(root, relative)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise WorkspaceConflictError(f"GENERATED_TARGET_NOT_REGULAR_FILE:{relative}")
            if target.read_text(encoding="utf-8") == content:
                continue
            if existing_manifest is None:
                raise WorkspaceConflictError(f"EXISTING_FILE_CONFLICT:{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(target, content)
    manifest = cast(dict[str, Any], json.loads(rendered[".elmos/generation-manifest.json"]))
    manifest["workspace"] = str(root)
    manifest["file_count"] = len(manifest["files"])
    return manifest
