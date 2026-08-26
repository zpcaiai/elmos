#!/usr/bin/env python3
"""Validate the installed Elmos pricing and billing Skill distribution.

The pinned archive is untrusted input.  Validation delegates archive parsing
and exact generated-tree comparison to the repository importer, then checks
the installed manifest's provenance, status ceiling, overlap authorities, and
Codex interfaces.  No source-package helper is imported or executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

import integrate_pricing_billing_skills as integration
import build_pricing_billing_runtime_binding as runtime_binding_builder


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_RELATIVE = Path("docs/pricing-billing-skills/installed-manifest.json")
INVENTORY_RELATIVE = Path("docs/pricing-billing-skills/source-inventory.json")
OVERLAP_RELATIVE = Path("docs/pricing-billing-skills/overlap-map.json")
RUNTIME_BINDING_RELATIVE = integration.RUNTIME_BINDING_RELATIVE
REQUIRED_OVERLAP_AUTHORITIES = (
    "product-b39-finance",
    "product-b44-finops-economics",
    "product-batch56-reviewed-guidance",
    "current-commercial-billing-runtime",
)


class ValidationError(RuntimeError):
    """An installed artifact or conservative evidence boundary is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {label}: {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _tree_payloads(root: Path) -> dict[str, tuple[bytes, int]]:
    _require(root.is_dir() and not root.is_symlink(), f"installed tree is invalid: {root}")
    result: dict[str, tuple[bytes, int]] = {}
    for path in root.rglob("*"):
        _require(not path.is_symlink(), f"symlink in installed tree: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
            )
        else:
            _require(path.is_dir(), f"special entry in installed tree: {path}")
    return result


def _validate_manifest(
    root: Path,
    snapshot: integration.PackageSnapshot,
    manifest: Mapping[str, Any],
) -> None:
    _require(
        manifest.get("schema_version")
        == "elmos.pricing-billing.installed-manifest.v1",
        "installed manifest Schema version is invalid",
    )
    _require(
        manifest.get("source_archive_sha256") == snapshot.archive_sha256,
        "installed manifest archive provenance differs",
    )
    _require(
        manifest.get("skill_count") == integration.EXPECTED_SKILL_COUNT
        and manifest.get("requirement_count") == integration.EXPECTED_REQUIREMENT_COUNT,
        "installed manifest top-level counts differ",
    )
    package = manifest.get("package")
    _require(isinstance(package, dict), "installed package record is invalid")
    _require(
        package.get("source_name") == integration.PACKAGE_ID
        and package.get("source_version") == integration.PACKAGE_VERSION
        and package.get("source_archive_sha256")
        == "sha256:" + snapshot.archive_sha256
        and package.get("archive_digest_scope") == integration.ARCHIVE_DIGEST_SCOPE
        and package.get("authorship_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and package.get("signature_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and package.get("sbom_attestation") == integration.SOURCE_ATTESTATION_STATE
        and package.get("provenance_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and package.get("archive_entry_count") == integration.EXPECTED_ENTRY_COUNT
        and package.get("archive_uncompressed_bytes")
        == integration.EXPECTED_UNCOMPRESSED_BYTES,
        "installed package identity, provenance, or counts differ",
    )
    namespace = manifest.get("namespace")
    _require(
        isinstance(namespace, dict)
        and namespace.get("name") == integration.PACKAGE_NAMESPACE
        and namespace.get("source_batch_range") == "B00-B53",
        "installed package namespace differs",
    )
    status = manifest.get("status")
    _require(
        status
        == {
            "guidance": integration.GUIDANCE_STATE,
            "installation": integration.INSTALL_STATE,
            "runtime_implementation": integration.RUNTIME_IMPLEMENTATION_STATE,
            "runtime_binding": integration.RUNTIME_BINDING_RELATIVE.as_posix(),
            "runtime_evidence": integration.RUNTIME_EVIDENCE_STATE,
            "external_evidence": integration.EXTERNAL_EVIDENCE_STATE,
            "certification": integration.CERTIFICATION_STATE,
            "production_ready": False,
            "maximum_local_claim": integration.MAXIMUM_LOCAL_CLAIM,
        },
        "installed evidence boundary or local claim ceiling differs",
    )
    _require(
        manifest.get("source_scripts_executed_by_importer") is False,
        "source-script execution must remain false",
    )

    rows = manifest.get("skills")
    _require(
        isinstance(rows, list)
        and [row.get("installed_name") for row in rows if isinstance(row, dict)]
        == list(integration.EXPECTED_SKILL_NAMES),
        "installed Skill inventory or order differs",
    )
    records = {record.name: record for record in snapshot.skills}
    for row in rows:
        _require(isinstance(row, dict), "installed Skill manifest row is invalid")
        name = row.get("installed_name")
        record = records.get(name)
        _require(record is not None, f"unknown installed Skill: {name}")
        expected_paths = [
            f"{install_root.as_posix()}/{name}"
            for install_root in integration.INSTALL_ROOTS
        ]
        _require(
            row.get("source_name") == name
            and row.get("installed_paths") == expected_paths
            and row.get("source_skill_sha256")
            == "sha256:" + record.source_skill_sha256
            and row.get("source_batches") == list(record.batches)
            and row.get("qualified_batches")
            == [f"{integration.PACKAGE_NAMESPACE}/{batch}" for batch in record.batches]
            and row.get("runtime_implementation")
            == integration.RUNTIME_IMPLEMENTATION_STATE
            and row.get("runtime_binding")
            == integration.RUNTIME_BINDING_RELATIVE.as_posix()
            and row.get("runtime_evidence") == integration.RUNTIME_EVIDENCE_STATE
            and row.get("external_evidence") == integration.EXTERNAL_EVIDENCE_STATE
            and row.get("certification") == integration.CERTIFICATION_STATE,
            f"installed Skill provenance or status differs: {name}",
        )

        left = root / integration.INSTALL_ROOTS[0] / name
        right = root / integration.INSTALL_ROOTS[1] / name
        _require(
            _tree_payloads(left) == _tree_payloads(right),
            f"dual-root byte/mode parity differs: {name}",
        )
        skill = left / "SKILL.md"
        interface = left / "agents/openai.yaml"
        _require(
            row.get("installed_skill_sha256") == _sha256(skill)
            and row.get("installed_interface_sha256") == _sha256(interface),
            f"installed Skill/interface digest differs: {name}",
        )
        interface_text = interface.read_text(encoding="utf-8")
        skill_text = skill.read_text(encoding="utf-8")
        _require(
            f"Use ${name} " in interface_text
            and 'short_description: "Apply imported Elmos billing guidance safely"'
            in interface_text
            and "allow_implicit_invocation: true" in interface_text,
            f"Codex interface metadata differs: {name}",
        )
        _require(
            integration.ARCHIVE_IDENTITY_NOTICE in skill_text,
            f"archive identity boundary is missing from installed Skill: {name}",
        )


def _validate_runtime_binding(
    snapshot: integration.PackageSnapshot,
    manifest_path: Path,
    binding: Mapping[str, Any],
) -> None:
    source = binding.get("sourceArchive")
    installed = binding.get("installedManifest")
    registry = binding.get("runtimeRegistry")
    traceability = binding.get("requirementTraceability")
    ceiling = binding.get("claimCeiling")
    _require(
        binding.get("schemaVersion") == 1
        and binding.get("packageNamespace") == integration.PACKAGE_NAMESPACE,
        "runtime binding Schema or namespace differs",
    )
    _require(
        isinstance(source, dict)
        and source.get("path") == integration.ARCHIVE_RELATIVE.as_posix()
        and source.get("sha256") == snapshot.archive_sha256
        and source.get("identityClaimOnly") is True,
        "runtime binding source identity differs",
    )
    _require(
        isinstance(installed, dict)
        and installed.get("path") == MANIFEST_RELATIVE.as_posix()
        and installed.get("sha256") == _sha256(manifest_path).removeprefix("sha256:"),
        "runtime binding installed-manifest identity differs",
    )
    _require(
        isinstance(registry, dict)
        and registry.get("skillCount") == integration.EXPECTED_SKILL_COUNT
        and registry.get("skills") == list(integration.EXPECTED_SKILL_NAMES)
        and registry.get("inspection") == "AST_LITERAL_SCAN_ONLY_NO_IMPORT_OR_EXECUTION",
        "runtime binding registry inventory or inspection boundary differs",
    )
    _require(isinstance(traceability, dict), "runtime binding traceability is invalid")
    rows = traceability.get("bindings")
    expected_ids = [
        f"EB-{skill:02d}-{requirement:03d}"
        for skill in range(1, 19)
        for requirement in range(1, 11)
    ]
    _require(
        traceability.get("requirementCount") == integration.EXPECTED_REQUIREMENT_COUNT
        and traceability.get("priorityCounts") == {"P0": 108, "P1": 72}
        and isinstance(rows, list)
        and [row.get("id") for row in rows if isinstance(row, dict)] == expected_ids
        and all(
            row.get("certification") == integration.CERTIFICATION_STATE
            and row.get("externalEvidence") == integration.EXTERNAL_EVIDENCE_STATE
            for row in rows
            if isinstance(row, dict)
        ),
        "runtime binding requirement inventory or evidence ceiling differs",
    )
    _require(
        ceiling
        == {
            "maximumLocalState": "LOCAL_EXECUTED",
            "externalProviderBankTaxAccountingEvidence": (
                "NOT_RUN_UNLESS_EXPLICITLY_BOUND_PER_REQUIREMENT"
            ),
            "certification": integration.CERTIFICATION_STATE,
        },
        "runtime binding claim ceiling differs",
    )


def validate(root: Path = ROOT) -> dict[str, Any]:
    try:
        root = integration._resolve_repository_root(root)
        archive = root / integration.ARCHIVE_RELATIVE
        snapshot = integration.validate_archive(archive)
        integration.check_outputs(root, snapshot)
    except integration.IntegrationError as exc:
        raise ValidationError(str(exc)) from exc

    manifest_path = root / MANIFEST_RELATIVE
    manifest = _load_json(manifest_path, "installed manifest")
    _validate_manifest(root, snapshot, manifest)
    runtime_binding_path = root / RUNTIME_BINDING_RELATIVE
    runtime_binding = _load_json(runtime_binding_path, "runtime binding")
    _validate_runtime_binding(snapshot, manifest_path, runtime_binding)
    try:
        expected_runtime_binding = runtime_binding_builder.build_document(root)
    except runtime_binding_builder.BindingError as exc:
        raise ValidationError(f"cannot rebuild runtime binding safely: {exc}") from exc
    _require(
        runtime_binding == expected_runtime_binding,
        "runtime binding is stale relative to its controlled runtime, tests, or mappings",
    )

    inventory = _load_json(root / INVENTORY_RELATIVE, "source inventory")
    _require(
        inventory.get("source_archive_sha256") == "sha256:" + snapshot.archive_sha256
        and inventory.get("archive_digest_scope") == integration.ARCHIVE_DIGEST_SCOPE
        and inventory.get("authorship_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and inventory.get("signature_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and inventory.get("sbom_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and inventory.get("provenance_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and inventory.get("archive_entry_count") == integration.EXPECTED_ENTRY_COUNT
        and inventory.get("internal_checksum_count")
        == integration.EXPECTED_INTERNAL_CHECKSUMS
        and inventory.get("controlled_file_count")
        == integration.EXPECTED_CONTROLLED_FILES
        and len(inventory.get("files", [])) == integration.EXPECTED_ENTRY_COUNT,
        "source inventory provenance or counts differ",
    )

    overlap = _load_json(root / OVERLAP_RELATIVE, "overlap map")
    relationships = overlap.get("relationships")
    _require(
        isinstance(relationships, list)
        and [row.get("authority_id") for row in relationships if isinstance(row, dict)]
        == list(REQUIRED_OVERLAP_AUTHORITIES)
        and overlap.get("source_namespace") == integration.PACKAGE_NAMESPACE
        and overlap.get("activation_default") == "guidance-only"
        and overlap.get("external_evidence_status") == integration.EXTERNAL_EVIDENCE_STATE
        and overlap.get("production_certification") == integration.CERTIFICATION_STATE,
        "overlap authority, namespace, or evidence boundary differs",
    )

    support_manifest = _load_json(
        root / integration.SUPPORT_RELATIVE / "install-manifest.json",
        "support install manifest",
    )
    _require(
        support_manifest.get("source_archive_sha256") == snapshot.archive_sha256
        and support_manifest.get("archive_digest_scope")
        == integration.ARCHIVE_DIGEST_SCOPE
        and support_manifest.get("authorship_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and support_manifest.get("signature_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and support_manifest.get("sbom_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and support_manifest.get("provenance_attestation")
        == integration.SOURCE_ATTESTATION_STATE
        and support_manifest.get("source_helpers_executed") is False
        and support_manifest.get("source_helpers_mode") == "0644_NON_EXECUTABLE"
        and support_manifest.get("runtime_implementation")
        == integration.RUNTIME_IMPLEMENTATION_STATE
        and support_manifest.get("runtime_binding")
        == integration.RUNTIME_BINDING_RELATIVE.as_posix(),
        "support-tree provenance or source-helper nonexecution boundary differs",
    )
    support_payloads = _tree_payloads(root / integration.SUPPORT_RELATIVE)
    _require(
        all(mode == 0o644 for _content, mode in support_payloads.values()),
        "support-tree files must all be non-executable mode 0644",
    )

    return {
        "decision": "INSTALLED_ARTIFACTS_VERIFIED",
        "package": integration.PACKAGE_ID,
        "version": integration.PACKAGE_VERSION,
        "archive_sha256": snapshot.archive_sha256,
        "installed_manifest_sha256": _sha256(manifest_path),
        "skills": len(snapshot.skills),
        "batches": len(snapshot.batches),
        "requirements": sum(snapshot.requirement_priority_counts.values()),
        "dual_root_parity": "BYTE_AND_MODE_IDENTICAL",
        "source_scripts_executed": False,
        "runtime_implementation": integration.RUNTIME_IMPLEMENTATION_STATE,
        "runtime_binding": integration.RUNTIME_BINDING_RELATIVE.as_posix(),
        "runtime_binding_sha256": _sha256(runtime_binding_path),
        "runtime_evidence": integration.RUNTIME_EVIDENCE_STATE,
        "external_evidence": integration.EXTERNAL_EVIDENCE_STATE,
        "certification": integration.CERTIFICATION_STATE,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        report = validate(args.root)
    except ValidationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
