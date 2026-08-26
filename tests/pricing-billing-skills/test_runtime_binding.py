from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tooling import build_pricing_billing_runtime_binding as binding


SOURCE_REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE_ARCHIVE = SOURCE_REPOSITORY.joinpath(*binding.ARCHIVE_RELATIVE.parts)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


ROOT_BATCHES = {1, 14, 15, 16, 17, 18}
COMMERCIAL_BATCHES = {2, 3, 6, 7, 8, 12}
FINANCIAL_BATCHES = {4, 5, 9, 13}
PAYMENT_BATCHES = {10, 11}


def _batch(requirement_id: str) -> int:
    return int(requirement_id[3:5])


def _requirements_for(batches: set[int]) -> list[str]:
    return [value for value in binding.EXACT_REQUIREMENTS if _batch(value) in batches]


def _non_hyphenated_namespaced(requirement_id: str) -> str:
    return "elmos.pricing-billing.v1/" + requirement_id.replace("EB-", "EB", 1)


def _create_repository(root: Path) -> Path:
    archive = root.joinpath(*binding.ARCHIVE_RELATIVE.parts)
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_ARCHIVE, archive)

    _write_json(
        root.joinpath(*binding.INSTALLED_MANIFEST_RELATIVE.parts),
        {"skills": [{"installed_name": name} for name in binding.EXACT_SKILLS]},
    )

    registry = root.joinpath(*binding.REGISTRY_RELATIVE.parts)
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        "SKILLS = (\n"
        + "".join(f"    {name!r},\n" for name in binding.EXACT_SKILLS)
        + ")\n",
        encoding="utf-8",
    )

    requirement_root = root.joinpath(*binding.REQUIREMENTS_RELATIVE.parts)
    _write_json(
        requirement_root / "root.json",
        {
            "namespace": "elmos.pricing-billing.v1",
            "implementationState": "LOCAL_IMPLEMENTED",
            "testExecution": "LOCAL_EXECUTED",
            "externalEvidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "requirements": [
                {
                    "id": requirement_id,
                    "symbol": f"root.symbol.{requirement_id}",
                    "test": f"test_root_{requirement_id.lower().replace('-', '_')}",
                }
                for requirement_id in _requirements_for(ROOT_BATCHES)
            ],
        },
    )
    _write_json(
        requirement_root / "commercial.json",
        {
            "namespace": "elmos.pricing-billing.v1",
            "implementation_state": "LOCAL_CODED_UNVERIFIED",
            "source_path": "engines/pricing-billing-engine/src/commercial.py",
            "test_path": "engines/pricing-billing-engine/tests/test_commercial.py",
            "test_execution": "LOCAL_EXECUTED",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "requirements": [
                {
                    "id": _non_hyphenated_namespaced(requirement_id),
                    "source_symbol": f"Commercial.{requirement_id}",
                    "test_symbol": f"test_commercial_{requirement_id.lower().replace('-', '_')}",
                }
                for requirement_id in _requirements_for(COMMERCIAL_BATCHES)
            ],
        },
    )
    _write_json(
        requirement_root / "financial.json",
        {
            "namespace": "elmos.pricing-billing.v1",
            "implementation_artifacts": ["modules/commercial/FinancialRuntime.java"],
            "test_artifacts": ["modules/commercial/FinancialRuntimeTest.java"],
            "evidence_state": {
                "implementation": "IMPLEMENTED_LOCAL_REFERENCE",
                "local_tests": "NOT_RUN",
                "postgresql_migration": "NOT_RUN",
                "provider_bank_tax_runtime": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            "requirements": [
                {
                    "id": _non_hyphenated_namespaced(requirement_id),
                    "implementation": f"Explicit financial control for {requirement_id}.",
                    "implementation_symbol": f"Financial.{requirement_id}",
                    "local_test_node_id": (
                        "tests/test_financial.py::"
                        f"test_{requirement_id.lower().replace('-', '_')}"
                    ),
                }
                for requirement_id in _requirements_for(FINANCIAL_BATCHES)
            ],
        },
    )
    _write_json(
        requirement_root / "payments.json",
        {
            "package_namespace": "elmos.pricing-billing.v1",
            "evidence_state": {
                "test_execution": "NOT_RUN",
                "provider_sandbox": "NOT_RUN",
                "bank_or_settlement_file": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            "requirements": [
                {
                    "id": requirement_id,
                    "canonical_id": f"elmos.pricing-billing.v1/{requirement_id}",
                    "priority": "P0" if int(requirement_id[-3:]) <= 6 else "P1",
                    "symbols": [f"Payment.{requirement_id}"],
                    "tests": [f"test_payment_{requirement_id.lower().replace('-', '_')}"],
                    "implementation_state": "LOCAL_CODE_ADDED_UNVERIFIED",
                }
                for requirement_id in _requirements_for(PAYMENT_BATCHES)
            ],
        },
    )

    runtime = root / "engines/pricing-billing-engine/src/elmos_pricing_billing/runtime.py"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("BOUNDARY = 'local-reference-only'\n", encoding="utf-8")
    tests = root / "engines/pricing-billing-engine/tests/test_runtime.py"
    tests.parent.mkdir(parents=True, exist_ok=True)
    tests.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    integration_test = root / "tests/pricing-billing-skills/fixture.txt"
    integration_test.parent.mkdir(parents=True, exist_ok=True)
    integration_test.write_text("fixture\n", encoding="utf-8")

    output_parent = root.joinpath(*binding.OUTPUT_RELATIVE.parent.parts)
    output_parent.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    return _create_repository(tmp_path / "repository")


def test_render_is_deterministic_and_write_check_are_byte_exact(repository: Path) -> None:
    root = binding.resolve_repo_root(repository)

    first = binding.render_binding(root)
    ignored_virtualenv = root / "engines/pricing-billing-engine/src/.venv/ignored.bin"
    ignored_virtualenv.parent.mkdir(parents=True)
    ignored_virtualenv.write_bytes(b"must not affect the binding")
    ignored_bytecode = root / "engines/pricing-billing-engine/tests/__pycache__/ignored.pyc"
    ignored_bytecode.parent.mkdir(parents=True)
    ignored_bytecode.write_bytes(b"must not affect the binding")
    second = binding.render_binding(root)

    assert first == second
    assert binding.main(["--repo-root", str(root), "--write"]) == 0
    output = root.joinpath(*binding.OUTPUT_RELATIVE.parts)
    assert output.read_bytes() == first
    assert binding.main(["--repo-root", str(root), "--check"]) == 0


def test_four_explicit_mapping_schemas_normalize_without_weakening(repository: Path) -> None:
    document = binding.build_document(repository)
    requirements = {
        item["id"]: item
        for item in document["requirementTraceability"]["bindings"]
    }

    root = requirements["EB-01-001"]
    assert root["canonicalId"] == "elmos.pricing-billing.v1/EB-01-001"
    assert root["implementation"] == "LOCAL_IMPLEMENTED"
    assert root["testExecution"] == "LOCAL_EXECUTED"
    assert root["priority"] == "P0"
    assert root["sourceBatch"] == "B00"
    assert root["sourceStatement"]

    commercial = requirements["EB-02-001"]
    assert commercial["implementation"] == "LOCAL_IMPLEMENTED"
    assert commercial["testExecution"] == "LOCAL_EXECUTED"
    assert commercial["symbols"] == [
        "Commercial.EB-02-001",
        "engines/pricing-billing-engine/src/commercial.py",
    ]
    assert "engines/pricing-billing-engine/tests/test_commercial.py" in commercial["tests"]

    financial = requirements["EB-04-001"]
    assert financial["implementation"] == "LOCAL_IMPLEMENTED"
    assert financial["testExecution"] == "NOT_RUN"
    assert financial["symbols"] == [
        "Explicit financial control for EB-04-001.",
        "Financial.EB-04-001",
        "modules/commercial/FinancialRuntime.java",
    ]
    assert financial["tests"] == [
        "modules/commercial/FinancialRuntimeTest.java",
        "tests/test_financial.py::test_eb_04_001",
    ]

    payments = requirements["EB-10-001"]
    assert payments["implementation"] == "LOCAL_IMPLEMENTED"
    assert payments["testExecution"] == "NOT_RUN"
    assert payments["externalEvidence"] == "NOT_RUN"
    assert payments["certification"] == "NOT_CERTIFIED"


def test_missing_and_duplicate_requirements_fail_closed(repository: Path) -> None:
    requirement_path = repository.joinpath(
        *binding.REQUIREMENTS_RELATIVE.parts, "payments.json"
    )
    document = json.loads(requirement_path.read_text(encoding="utf-8"))
    complete = list(document["requirements"])

    document["requirements"] = complete[:-1]
    _write_json(requirement_path, document)
    with pytest.raises(binding.BindingError, match="missing exact"):
        binding.build_document(repository)

    duplicate = dict(complete[0])
    duplicate["id"] = _non_hyphenated_namespaced(str(duplicate["id"]))
    document["requirements"] = complete + [duplicate]
    _write_json(requirement_path, document)
    with pytest.raises(binding.BindingError, match="duplicate requirement id"):
        binding.build_document(repository)

    document["requirements"] = complete
    document["requirements"][0]["priority"] = "P1"
    _write_json(requirement_path, document)
    with pytest.raises(binding.BindingError, match="priority differs from the pinned archive"):
        binding.build_document(repository)

    document["requirements"][0]["priority"] = "P0"
    document["requirements"][0]["source_statement"] = "tampered source statement"
    _write_json(requirement_path, document)
    with pytest.raises(binding.BindingError, match="statement differs from the pinned archive"):
        binding.build_document(repository)


def test_stale_archive_installed_manifest_and_registry_are_rejected(repository: Path) -> None:
    archive = repository.joinpath(*binding.ARCHIVE_RELATIVE.parts)
    archive.write_bytes(archive.read_bytes() + b"stale")
    with pytest.raises(binding.BindingError, match="source archive digest mismatch"):
        binding.build_document(repository)

    repository = _create_repository(repository.parent / "installed-drift")
    manifest_path = repository.joinpath(*binding.INSTALLED_MANIFEST_RELATIVE.parts)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["skills"].pop()
    _write_json(manifest_path, manifest)
    with pytest.raises(binding.BindingError, match="exact 18"):
        binding.build_document(repository)

    repository = _create_repository(repository.parent / "registry-drift")
    registry = repository.joinpath(*binding.REGISTRY_RELATIVE.parts)
    registry.write_text("SKILLS = ('elmos-billing-orchestrator',)\n", encoding="utf-8")
    with pytest.raises(binding.BindingError, match="registry skill drift"):
        binding.build_document(repository)


def test_repo_root_and_controlled_input_symlinks_are_rejected(repository: Path) -> None:
    root_link = repository.parent / "repository-link"
    root_link.symlink_to(repository, target_is_directory=True)
    with pytest.raises(binding.BindingError, match="repository root contains a symlink"):
        binding.resolve_repo_root(root_link)

    manifest_path = repository.joinpath(*binding.INSTALLED_MANIFEST_RELATIVE.parts)
    outside = repository.parent / "outside-manifest.json"
    outside.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(outside)
    with pytest.raises(binding.BindingError, match="controlled path contains a symlink"):
        binding.build_document(repository)


def test_bounded_reads_reject_oversized_controlled_input(repository: Path) -> None:
    manifest_path = repository.joinpath(*binding.INSTALLED_MANIFEST_RELATIVE.parts)
    manifest_path.write_bytes(b"{" + b" " * binding.MAX_JSON_BYTES + b"}")

    with pytest.raises(binding.BindingError, match="exceeds"):
        binding.build_document(repository)


def test_check_detects_drift_and_cli_actions_are_mutually_exclusive(repository: Path) -> None:
    assert binding.main(["--repo-root", str(repository), "--check"]) == 1
    assert binding.main(["--repo-root", str(repository), "--write"]) == 0

    output = repository.joinpath(*binding.OUTPUT_RELATIVE.parts)
    output.write_bytes(output.read_bytes() + b"drift")
    assert binding.main(["--repo-root", str(repository), "--check"]) == 1

    with pytest.raises(SystemExit):
        binding.main(["--repo-root", str(repository), "--write", "--check"])
