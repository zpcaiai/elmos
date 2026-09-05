from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from elmos_project_synthesis.cli import main as cli_main
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES, SynthesisRequest, p0_scope_payload
from elmos_project_synthesis.supply_chain import (
    ARTIFACT_HASH_EVIDENCE_PATH,
    SupplyChainFailure,
    build_dependency_sbom,
    build_python_lock_sbom,
    build_release_manifest,
    build_workspace_sbom,
    canonical_json,
    collect_native_artifact_hash_evidence,
    observe_git_revision,
    sbom_is_complete,
    sbom_status,
    verify_release_signature,
)
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def _allow_crud(resource: str) -> list[dict[str, str]]:
    return [
        {"actor": "api_user", "action": action, "resource": resource, "effect": "allow"}
        for action in ("create", "read", "update", "delete")
    ]


def _p0_request(
    *,
    languages: tuple[str, ...] = SUPPORTED_LANGUAGES,
    auth_mode: str = "jwt",
) -> dict[str, object]:
    draft = create_draft(
        name="release-orders",
        description="P0 order API",
        entity="order",
        languages=languages,
        persistence="postgresql",
        auth_mode=auth_mode,
        permissions=_allow_crud("order"),
    )
    return approve_request(draft, actor="user:release-reviewer", approved_at="2026-09-04T00:00:00+00:00")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _materialize_native_locks(workspace: Path) -> None:
    if (workspace / "java").is_dir():
        java_tree = {
            "groupId": "com.example",
            "artifactId": "release-orders",
            "version": "1.0.0",
            "children": [
                {
                    "groupId": "org.springframework.boot",
                    "artifactId": "spring-boot-starter-web",
                    "version": "3.5.3",
                    "children": [
                        {
                            "groupId": "org.springframework",
                            "artifactId": "spring-web",
                            "version": "6.2.8",
                            "children": [],
                        }
                    ],
                }
            ],
        }
        _write_json(workspace / ".elmos" / "dependencies" / "java-dependency-tree.json", java_tree)
    if (workspace / "python").is_dir():
        digest = hashlib.sha256(b"fastapi-0.116.1").hexdigest()
        (workspace / "python" / "uv.lock").write_text(
            f'''version = 1

[[package]]
name = "release-orders"
version = "1.0.0"
source = {{ editable = "." }}

[[package]]
name = "fastapi"
version = "0.116.1"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ hash = "sha256:{digest}" }}
''',
            encoding="utf-8",
        )
    if (workspace / "dotnet").is_dir():
        content_hash = base64.b64encode(hashlib.sha512(b"Npgsql-9.0.3").digest()).decode("ascii")
        transitive_hash = base64.b64encode(hashlib.sha512(b"System.Memory-4.6.3").digest()).decode("ascii")
        _write_json(
            workspace / "dotnet" / "packages.lock.json",
            {
                "version": 1,
                "dependencies": {
                    "net10.0": {
                        "Npgsql": {
                            "type": "Direct",
                            "requested": "[9.0.3, )",
                            "resolved": "9.0.3",
                            "contentHash": content_hash,
                        },
                        "System.Memory": {
                            "type": "Transitive",
                            "resolved": "4.6.3",
                            "contentHash": transitive_hash,
                        },
                        "release-orders.api": {
                            "type": "Project"
                        },
                    }
                },
            },
        )
    if (workspace / "typescript").is_dir():
        pg_integrity = base64.b64encode(hashlib.sha512(b"pg-8.16.3").digest()).decode("ascii")
        types_integrity = base64.b64encode(hashlib.sha512(b"pg-types-2.2.0").digest()).decode("ascii")
        (workspace / "typescript" / "pnpm-lock.yaml").write_text(
            f'''lockfileVersion: '9.0'
packages:
  pg@8.16.3:
    resolution: {{integrity: sha512-{pg_integrity}}}
  pg-types@2.2.0:
    resolution: {{integrity: sha512-{types_integrity}}}
snapshots: {{}}
''',
            encoding="utf-8",
        )


def _materialize_maven_artifact_evidence(workspace: Path, cache_root: Path) -> dict[str, object]:
    preliminary = build_workspace_sbom(workspace)
    references = sorted(
        str(item["bom-ref"])
        for item in preliminary["components"]
        if str(item.get("bom-ref", "")).startswith("pkg:maven/")
    )
    maven = cache_root / "maven"
    gradle = cache_root / "gradle"
    maven.mkdir(parents=True)
    gradle.mkdir(parents=True)
    for reference in references:
        coordinate = reference.removeprefix("pkg:maven/")
        name, version = coordinate.rsplit("@", 1)
        group, artifact = name.rsplit("/", 1)
        artifact_path = maven.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}.jar")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"PK\x03\x04" + reference.encode("utf-8"))
    evidence = collect_native_artifact_hash_evidence(
        workspace,
        maven_repository=maven,
        gradle_cache=gradle,
    )
    _write_json(workspace / ARTIFACT_HASH_EVIDENCE_PATH, evidence)
    return evidence


def _complete_workspace(
    tmp_path: Path,
    *,
    languages: tuple[str, ...] = SUPPORTED_LANGUAGES,
    auth_mode: str = "jwt",
) -> tuple[Path, dict[str, object]]:
    request = _p0_request(languages=languages, auth_mode=auth_mode)
    workspace = tmp_path / "workspace"
    generate_workspace(request, workspace)
    _materialize_native_locks(workspace)
    if (workspace / "java").is_dir() or (workspace / "kotlin").is_dir():
        _materialize_maven_artifact_evidence(workspace, tmp_path / "native-caches")
    return workspace, request


_TOOLCHAIN_LABELS = {
    "php": ("PHP 8.4.12",),
    "postgresql": ("PostgreSQL 17.5",),
}


def _php_verification_fixture(workspace: Path) -> dict[str, object]:
    generation_path = workspace / ".elmos" / "generation-manifest.json"
    generation_bytes = generation_path.read_bytes()
    generation = json.loads(generation_bytes)
    sbom = build_workspace_sbom(workspace)
    results: list[dict[str, object]] = []
    for language, labels in _TOOLCHAIN_LABELS.items():
        for label in labels:
            results.append(
                {
                    "language": language,
                    "kind": "toolchain",
                    "command": [language, "--version"],
                    "status": "PASSED",
                    "exit_code": 0,
                    "output": f"EXPECTED:{label}\nOBSERVED:/verified/{language}:{label}",
                }
            )
    for command in (("php", "-l", "public/index.php"), ("php", "tests/run.php")):
        results.append(
            {
                "language": "php",
                "kind": "build-analysis",
                "command": list(command),
                "status": "PASSED",
                "exit_code": 0,
                "output": "TEST_FIXTURE_STRUCTURALLY_VALID_RESULT",
            }
        )
    results.append(
        {
            "language": "php",
            "kind": "startup-probe",
            "command": ["php", "-S", "127.0.0.1:8087", "public/index.php"],
            "status": "PASSED",
            "exit_code": 0,
            "output": "TEST_FIXTURE_STRUCTURALLY_VALID_RESULT",
            "port": 8087,
            "response": '{"status":"ok","service":"release-orders"}',
            "integration_status": "PASSED",
        }
    )
    return {
        "schema_version": "1.2.0",
        "status": "PASSED",
        "workspace": str(workspace.resolve()),
        "request_sha256": generation["request_sha256"],
        "approved_payload_sha256": generation["approved_payload_sha256"],
        "generation_manifest_sha256": hashlib.sha256(generation_bytes).hexdigest(),
        "supply_chain": {
            "sbom_format": "CycloneDX",
            "sbom_spec_version": "1.6",
            "sbom_sha256": hashlib.sha256(canonical_json(sbom)).hexdigest(),
            "transitive_inventory_status": "COMPLETE",
            "artifact_integrity_status": "COMPLETE",
            "dependency_graph_status": "INCOMPLETE_FLATTENED",
            "release_signature_status": "NOT_RUN",
            "trusted_root_status": "NOT_RUN",
        },
        "environment": {
            "platform": "test-fixture",
            "python": "3.12.12",
            "tools": {},
            "exact_toolchain_match": {"php": True},
        },
        "production_delivery_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "results": results,
        "insights": {},
    }


def _init_git_repository(path: Path, *, include_provider_observation: bool = False) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[3]
    (path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    for relative in (
        "AGENTS.md",
        "Makefile",
        "engines/project-synthesis-engine/pyproject.toml",
        "docs/project-synthesis/p0-launch-scope-v1.json",
    ):
        destination = path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, destination)
    if include_provider_observation:
        source = source_root / "docs/project-synthesis/provider-observation-2026-09-04.json"
        destination = path / "docs/project-synthesis/provider-observation-2026-09-04.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "ELMOS Test"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "https://github.com/zpcaiai/elmos.git"],
        check=True,
    )
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
    return path.resolve()


def test_frozen_p0_scope_and_generation_manifest_are_digest_bound() -> None:
    request = SynthesisRequest.from_mapping(_p0_request())
    rendered = render_workspace(request)
    manifest = json.loads(rendered[".elmos/generation-manifest.json"])
    sbom = json.loads(rendered["requirements/dependency-sbom.cdx.json"])
    scope = p0_scope_payload()

    assert scope["project_kind"] == "api"
    assert [item["language"] for item in scope["languages"]] == list(SUPPORTED_LANGUAGES)
    java = scope["languages"][0]
    python = scope["languages"][1]
    assert java["request_runtime_selector"] == "21"
    assert java["exact_qualification_toolchain"][0]["version"] == "21.0.11"
    assert python["request_runtime_selector"] == "3.12"
    assert python["exact_qualification_toolchain"][0]["version"] == "3.12.12"
    assert scope["persistence"]["exact_local_runtime_version"] == "17.5"
    assert "managed_provider_observation" not in scope
    assert scope["managed_provider_contract"]["algorithm_mismatch_policy"] == "BLOCKED"
    assert manifest["schema_version"] == "1.2.0"
    assert manifest["p0_launch_scope"]["request_status"] == "IN_SCOPE"
    assert manifest["supply_chain"]["sbom"]["dependency_graph_status"] == "INCOMPLETE_FLATTENED"
    assert not sbom_is_complete(sbom)
    assert manifest["certification_status"] == "NOT_CERTIFIED"


def test_generation_sbom_keeps_missing_inventory_and_integrity_explicit() -> None:
    request = SynthesisRequest.from_mapping(_p0_request(languages=("java", "python", "rust")))
    sbom = build_dependency_sbom(request, render_workspace(request))

    assert sbom_status(sbom, "elmos:transitive-inventory-status") == "INCOMPLETE"
    assert sbom_status(sbom, "elmos:artifact-integrity-status") == "INCOMPLETE"
    assert sbom_status(sbom, "elmos:dependency-graph-status") == "INCOMPLETE_FLATTENED"
    properties = {item["name"]: item["value"] for item in sbom["metadata"]["properties"]}
    assert properties["elmos:target:java:missing-evidence"] == '[".elmos/dependencies/java-dependency-tree.json"]'
    assert properties["elmos:target:python:missing-evidence"] == '["python/uv.lock"]'
    assert properties["elmos:target:rust:inventory-status"] == "COMPLETE"


def test_native_cache_collector_makes_java_integrity_reachable_and_missing_fails(tmp_path: Path) -> None:
    request = _p0_request(languages=("java",))
    workspace = tmp_path / "workspace"
    generate_workspace(request, workspace)
    _materialize_native_locks(workspace)
    maven = tmp_path / "maven"
    gradle = tmp_path / "gradle"
    maven.mkdir()
    gradle.mkdir()

    with pytest.raises(SupplyChainFailure, match="NATIVE_ARTIFACT_NOT_FOUND"):
        collect_native_artifact_hash_evidence(workspace, maven_repository=maven, gradle_cache=gradle)

    evidence = _materialize_maven_artifact_evidence(workspace, tmp_path / "caches")
    sbom = build_workspace_sbom(workspace)
    assert evidence["artifacts"]
    assert sbom_is_complete(sbom)
    assert all(record["byte_count"] > 0 for record in evidence["artifacts"])


def test_native_cache_collector_prefers_jar_and_does_not_compare_it_to_pom(tmp_path: Path) -> None:
    workspace = tmp_path / "project" / "workspace"
    generate_workspace(_p0_request(languages=("java",)), workspace)
    _materialize_native_locks(workspace)
    maven = tmp_path / "cache" / "maven"
    gradle = tmp_path / "cache" / "gradle"
    gradle.mkdir(parents=True)
    preliminary = build_workspace_sbom(workspace)
    references = [
        str(item["bom-ref"])
        for item in preliminary["components"]
        if str(item.get("bom-ref", "")).startswith("pkg:maven/")
    ]
    for reference in references:
        coordinate = reference.removeprefix("pkg:maven/")
        name, version = coordinate.rsplit("@", 1)
        group, artifact = name.rsplit("/", 1)
        directory = maven.joinpath(*group.split("."), artifact, version)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{artifact}-{version}.jar").write_bytes(b"PK\x03\x04" + reference.encode())
        (directory / f"{artifact}-{version}.pom").write_text("<project/>\n", encoding="utf-8")
    evidence = collect_native_artifact_hash_evidence(
        workspace,
        maven_repository=maven,
        gradle_cache=gradle,
    )
    assert len(evidence["artifacts"]) == len(references)
    assert all(record["cache_relative_path"].endswith(".jar") for record in evidence["artifacts"])


def test_workspace_sbom_collects_transitive_inventory_without_graph_overclaim(tmp_path: Path) -> None:
    workspace, _ = _complete_workspace(tmp_path)
    sbom = build_workspace_sbom(workspace)
    components = {(item["name"], item["version"]) for item in sbom["components"]}

    assert sbom_is_complete(sbom)
    assert sbom["compositions"][0]["aggregate"] == "incomplete"
    assert sbom_status(sbom, "elmos:dependency-graph-status") == "INCOMPLETE_FLATTENED"
    assert ("org.springframework/spring-web", "6.2.8") in components
    assert ("fastapi", "0.116.1") in components
    assert ("System.Memory", "4.6.3") in components
    assert ("pg-types", "2.2.0") in components
    assert any(item[0] == "axum" for item in components)


def test_placeholder_or_missing_registry_integrity_never_unlocks_release(tmp_path: Path) -> None:
    request = SynthesisRequest.from_mapping(_p0_request(languages=("python", "typescript")))
    rendered = render_workspace(request)
    rendered["python/uv.lock"] = '''version = 1
[[package]]
name = "fastapi"
version = "0.116.1"
source = { registry = "https://pypi.org/simple" }
'''
    rendered["typescript/pnpm-lock.yaml"] = """lockfileVersion: '9.0'
packages:
  pg@8.16.3:
    resolution: {integrity: sha512-example}
"""
    sbom = build_dependency_sbom(request, rendered)
    assert sbom_status(sbom, "elmos:transitive-inventory-status") == "COMPLETE"
    assert sbom_status(sbom, "elmos:artifact-integrity-status") == "INCOMPLETE"
    assert not sbom_is_complete(sbom)


def test_release_manifest_rebuilds_sbom_validates_receipt_and_observes_real_git(tmp_path: Path) -> None:
    workspace, request = _complete_workspace(tmp_path, languages=("php",))
    sbom = build_workspace_sbom(workspace)
    verification_path = tmp_path / "verification.json"
    _write_json(verification_path, _php_verification_fixture(workspace))
    repository = _init_git_repository(tmp_path / "source")

    manifest = build_release_manifest(
        workspace,
        sbom=sbom,
        verification=verification_path,
        source_repository=repository,
    )
    observed = observe_git_revision(repository)
    assert request["project"]["kind"] == "api"
    assert manifest["source_revision"] == observed
    assert manifest["decision"] == "AWAITING_TRUSTED_SIGNATURE"
    assert manifest["blockers"] == ["RELEASE_SIGNATURE_NOT_VERIFIED"]
    assert manifest["transitive_dependency_sbom"]["release_input_status"] == (
        "INVENTORY_AND_INTEGRITY_COMPLETE"
    )

    forged_sbom = deepcopy(sbom)
    forged_sbom["components"].append({"type": "library", "bom-ref": "pkg:test/forged@1", "name": "forged"})
    with pytest.raises(SupplyChainFailure, match="RELEASE_SBOM_WORKSPACE_BINDING_MISMATCH"):
        build_release_manifest(
            workspace,
            sbom=forged_sbom,
            verification=verification_path,
            source_repository=repository,
        )

    forged_receipt = _php_verification_fixture(workspace)
    forged_receipt["results"] = []
    _write_json(verification_path, forged_receipt)
    with pytest.raises(SupplyChainFailure, match="RESULTS_EMPTY"):
        build_release_manifest(
            workspace,
            sbom=sbom,
            verification=verification_path,
            source_repository=repository,
        )


def test_dirty_source_and_oidc_algorithm_mismatch_fail_closed(tmp_path: Path) -> None:
    jwt_workspace, _ = _complete_workspace(tmp_path / "jwt", languages=("php",))
    jwt_sbom = build_workspace_sbom(jwt_workspace)
    jwt_verification = tmp_path / "jwt-verification.json"
    _write_json(jwt_verification, _php_verification_fixture(jwt_workspace))
    dirty_repository = _init_git_repository(tmp_path / "dirty-source")
    (dirty_repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    dirty = build_release_manifest(
        jwt_workspace,
        sbom=jwt_sbom,
        verification=jwt_verification,
        source_repository=dirty_repository,
    )
    assert dirty["decision"] == "BLOCKED"
    assert "SOURCE_WORKTREE_NOT_CLEAN" in dirty["blockers"]

    oidc_workspace, _ = _complete_workspace(
        tmp_path / "oidc",
        languages=("php",),
        auth_mode="oidc",
    )
    oidc_verification = tmp_path / "oidc-verification.json"
    _write_json(oidc_verification, _php_verification_fixture(oidc_workspace))
    provider_repository = _init_git_repository(
        tmp_path / "provider-source",
        include_provider_observation=True,
    )
    oidc = build_release_manifest(
        oidc_workspace,
        sbom=build_workspace_sbom(oidc_workspace),
        verification=oidc_verification,
        source_repository=provider_repository,
    )
    assert oidc["managed_provider_compatibility"]["status"] == "ALGORITHM_MISMATCH"
    assert "MANAGED_OIDC_ALGORITHM_MISMATCH:required=RS256:observed=EdDSA" in oidc["blockers"]
    assert oidc["decision"] == "BLOCKED"


def test_supply_chain_cli_returns_nonzero_for_blocked_manifest(tmp_path: Path) -> None:
    workspace, _ = _complete_workspace(tmp_path, languages=("php",))
    repository = _init_git_repository(tmp_path / "source")
    exit_code = cli_main(
        [
            "supply-chain",
            "--workspace",
            str(workspace),
            "--source-repository",
            str(repository),
            "--sbom",
            str(tmp_path / "sbom.json"),
            "--release-manifest",
            str(tmp_path / "release.json"),
        ]
    )
    assert exit_code == 2
    assert json.loads((tmp_path / "release.json").read_text(encoding="utf-8"))["decision"] == "BLOCKED"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is required for Ed25519 verification")
def test_release_signature_requires_active_exact_trust_root(tmp_path: Path) -> None:
    openssl = shutil.which("openssl")
    assert openssl is not None
    workspace, _ = _complete_workspace(tmp_path, languages=("php",))
    verification = tmp_path / "verification.json"
    _write_json(verification, _php_verification_fixture(workspace))
    repository = _init_git_repository(tmp_path / "source")
    manifest = build_release_manifest(
        workspace,
        sbom=build_workspace_sbom(workspace),
        verification=verification,
        source_repository=repository,
    )
    manifest_path = tmp_path / "release-manifest.json"
    _write_json(manifest_path, manifest)
    sbom_path = tmp_path / "sbom.json"
    _write_json(sbom_path, build_workspace_sbom(workspace))

    private_key = tmp_path / "release-private.pem"
    public_key = tmp_path / "release-public.pem"
    signature_binary = tmp_path / "release.sig"
    canonical_path = tmp_path / "release.canonical.json"
    canonical_path.write_bytes(canonical_json(manifest))
    subprocess.run([openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_key)], check=True)
    subprocess.run(
        [openssl, "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
    )
    subprocess.run(
        [
            openssl,
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_key),
            "-rawin",
            "-in",
            str(canonical_path),
            "-out",
            str(signature_binary),
        ],
        check=True,
    )
    signature_path = tmp_path / "release-signature.json"
    _write_json(
        signature_path,
        {
            "schema_version": "1.0.0",
            "kind": "elmos.project-synthesis.release-signature",
            "algorithm": "ed25519",
            "key_id": "release-2026",
            "payload_format": "canonical-json",
            "payload_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
            "signature_base64": base64.b64encode(signature_binary.read_bytes()).decode("ascii"),
            "signed_at": "2026-09-04T01:00:00Z",
        },
    )
    trust_root_path = tmp_path / "release-trust-root.json"
    _write_json(
        trust_root_path,
        {
            "schema_version": "1.0.0",
            "kind": "elmos.project-synthesis.release-trust-root",
            "trust_root_id": "project-synthesis-release-root",
            "status": "ACTIVE",
            "keys": [
                {
                    "key_id": "release-2026",
                    "algorithm": "ed25519",
                    "status": "ACTIVE",
                    "public_key_path": public_key.name,
                    "public_key_sha256": hashlib.sha256(public_key.read_bytes()).hexdigest(),
                    "valid_from": "2026-09-04T00:00:00Z",
                    "valid_until": "2027-09-04T00:00:00Z",
                }
            ],
        },
    )

    verified = verify_release_signature(
        manifest_path,
        signature_path,
        trust_root_path,
        workspace=workspace,
        sbom_path=sbom_path,
        verification_path=verification,
        source_repository=repository,
        verified_at=datetime(2026, 9, 4, 2, tzinfo=UTC),
    )
    assert verified["decision"] == "READY_FOR_EXTERNAL_GATE"
    assert verified["production_ready"] is False
    assert verified["certified"] is False

    revoked = json.loads(trust_root_path.read_text(encoding="utf-8"))
    revoked["keys"][0]["status"] = "REVOKED"
    _write_json(trust_root_path, revoked)
    with pytest.raises(SupplyChainFailure, match="RELEASE_SIGNING_KEY_NOT_ACTIVE"):
        verify_release_signature(
            manifest_path,
            signature_path,
            trust_root_path,
            workspace=workspace,
            sbom_path=sbom_path,
            verification_path=verification,
            source_repository=repository,
            verified_at=datetime(2026, 9, 4, 2, tzinfo=UTC),
        )


def _load_current_sha_collector() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts/operations/generate_project_synthesis_p0_evidence.py"
    spec = importlib.util.spec_from_file_location("project_synthesis_p0_evidence_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collector_repository(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[3]
    repository = tmp_path / "collector-source"
    engine = repository / "engines/project-synthesis-engine"
    engine.parent.mkdir(parents=True)
    shutil.copytree(source_root / "engines/project-synthesis-engine/src", engine / "src")
    shutil.copy2(source_root / "engines/project-synthesis-engine/pyproject.toml", engine / "pyproject.toml")
    shutil.copy2(source_root / "engines/project-synthesis-engine/uv.lock", engine / "uv.lock")
    docs = repository / "docs/project-synthesis"
    docs.mkdir(parents=True)
    for name in ("p0-launch-scope-v1.json", "provider-observation-2026-09-04.json"):
        shutil.copy2(source_root / "docs/project-synthesis" / name, docs / name)
    return _init_git_repository(repository)


def test_current_sha_collector_uses_exact_cwds_and_exercises_happy_skip_dirty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = _load_current_sha_collector()
    repository = _collector_repository(tmp_path)
    plan = collector._check_plan(repository)
    assert plan
    by_id = {identifier: cwd for identifier, _command, cwd, _timeout in plan}
    engine = repository / "engines/project-synthesis-engine"
    assert by_id["ruff"] == engine
    assert by_id["mypy"] == engine

    monkeypatch.setattr(
        collector,
        "_check_plan",
        lambda _repository: [
            ("sentinel", [sys.executable, "-c", "print('collector-ok')"], repository, 60)
        ],
    )
    happy_output = tmp_path / "happy-evidence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collector",
            "--repository",
            str(repository),
            "--output",
            str(happy_output),
            "--auth-profile",
            "jwt",
        ],
    )
    assert collector.main() == 0
    happy = json.loads((happy_output / "current-sha-evidence.json").read_text(encoding="utf-8"))
    assert happy["local_checks"]["status"] == "PASSED"
    assert happy["decision"] == "READY_FOR_TRUSTED_SIGNING"

    skip_output = tmp_path / "skip-evidence"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collector",
            "--repository",
            str(repository),
            "--output",
            str(skip_output),
            "--auth-profile",
            "jwt",
            "--skip-local-checks",
        ],
    )
    assert collector.main() == 2
    skipped = json.loads((skip_output / "current-sha-evidence.json").read_text(encoding="utf-8"))
    assert skipped["local_checks"]["status"] == "NOT_RUN"
    assert "LOCAL_CHECKS_NOT_RUN" in skipped["blockers"]

    (repository / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collector",
            "--repository",
            str(repository),
            "--output",
            str(tmp_path / "dirty-evidence"),
            "--auth-profile",
            "jwt",
        ],
    )
    with pytest.raises(collector.EvidenceFailure, match="SOURCE_WORKTREE_NOT_CLEAN"):
        collector.main()


def test_engine_uv_lock_produces_integrity_complete_flattened_inventory() -> None:
    engine = Path(__file__).resolve().parents[1]
    sbom = build_python_lock_sbom(engine)

    assert sbom_is_complete(sbom)
    assert sbom["compositions"][0]["aggregate"] == "incomplete"
    assert len(sbom["components"]) >= 10
    assert any(item["name"] == "pytest" and item["version"] == "9.0.3" for item in sbom["components"])
    assert any(item["name"] == "mypy" and item["version"] == "1.17.0" for item in sbom["components"])
