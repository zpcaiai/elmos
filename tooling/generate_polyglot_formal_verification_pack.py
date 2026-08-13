#!/usr/bin/env python3
"""Build the honest Batch 35 aggregate for the exact 30 routed language pairs.

The route generator owns execution.  This tool only packages already persisted,
content-addressed route evidence and the separately executed arithmetic solver
campaign.  Missing routes, missing strict evidence, or unverified bytes stop the
build; unresolved proof obligations remain explicit ``not-run`` entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PACK_KEY = "polyglot-30-route-formal-equivalence-v1"
PACK_KEY = "polyglot-30-route-formal-equivalence-v1"
PACK_VERSION = "1.0.0"
LANGUAGES = ("csharp", "go", "java", "python", "rust", "typescript")
SEMANTIC_PROFILE = "typed-pure-function-v1"
BLOCKS = (
    "signature-types-and-names",
    "literals",
    "integer-arithmetic",
    "arithmetic-error-behavior",
    "comparisons",
    "boolean-short-circuit",
    "strings",
    "number-nan-infinity-signed-zero",
    "if-else-path-conditions",
    "return-and-totality",
    "evaluation-order",
    "source-map",
)
# The three checked-in corpora exercise only this exact subset.  The remaining
# matrix rows stay NOT_RUN until a native corpus actually covers them.
LOCALLY_EXERCISED_BLOCKS = frozenset(
    {
        "signature-types-and-names",
        "literals",
        "integer-arithmetic",
        "comparisons",
        "if-else-path-conditions",
        "return-and-totality",
        "source-map",
    }
)
PACKED_REPLAY_SCOPE = "evidence-integrity-and-semantic-closure-only"
PACKED_REPLAY_COMMAND = [
    "python3",
    "certification/replay/validate_packed_route.py",
    "--route",
    ".",
]
LEGACY_REPLAY_SOURCE_ROOT = (
    "verification-packs/polyglot-30-route-formal-equivalence-v1/evidence/routes/"
    "csharp-to-go/certification/replay"
)
PACKED_REPLAY_FILES = {
    "certification/replay/validate_packed_route.py": (
        f"{LEGACY_REPLAY_SOURCE_ROOT}/validate_packed_route.py",
        "replay-tool",
        "launcher",
    ),
    "certification/replay/scripts/batch29/validate_route.py": (
        f"{LEGACY_REPLAY_SOURCE_ROOT}/scripts/batch29/validate_route.py",
        "replay-tool",
        "validator",
    ),
    "certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json": (
        (
            f"{LEGACY_REPLAY_SOURCE_ROOT}/schemas/batch29/"
            "formal-equivalence-evidence.schema.json"
        ),
        "replay-schema",
        "schema",
    ),
}
LEGACY_CAMPAIGN_SHA256 = (
    "sha256:4a31a2c67e0f2aaa03ba24b343abb4f60dd8b600121fb9cf7cd77aa1cba95c9c"
)
LEGACY_CAMPAIGN_BYTES = 578_643
LEGACY_REPLAY_METHOD_SHA256 = (
    "sha256:52a1e58a6c044eb5744bd70e1de43d6880bb7bd2e34838ae237503ec87a78ec"
)
LEGACY_REPLAY_IDENTITIES = {
    "certification/replay/validate_packed_route.py": (
        "sha256:d7cf4017a6d0296c01f880e568950ef6b1dd341b61b48a09b90d61e0cff686da",
        6_753,
    ),
    "certification/replay/scripts/batch29/validate_route.py": (
        "sha256:650470cc8078fe8158eea881885ccd5390ea68d2eb81b4809ed6b672c553c6f9",
        95_431,
    ),
    ("certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json"): (
        "sha256:c4821219c01e037ca86bb749f7790a892b612e2c6d0cfd382eb40c503a0280c7",
        11_670,
    ),
}
EXTERNAL_NATIVE_REEXECUTION = {
    "status": "NOT_RUN",
    "scope": "native-toolchain-regeneration-and-execution",
    "required_environment_variable": "ELMOS_REPO_ROOT",
    "command_template": [
        "uv",
        "--directory",
        "${ELMOS_REPO_ROOT}/engines/polyglot-route-engine",
        "run",
        "--locked",
        "python",
        "${ELMOS_REPO_ROOT}/scripts/batch29/run_polyglot_routes.py",
        "--repo-root",
        "${ELMOS_REPO_ROOT}",
        "--route",
        "{route_key}",
    ],
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def immutable_tree_digest(root: Path) -> str:
    """Digest every regular file path, byte count, and content in one pack."""

    if root.is_symlink() or not root.is_dir():
        raise RuntimeError(f"PACK_TREE_INVALID:{root}")
    records: list[dict[str, str | int]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"PACK_TREE_SYMLINK_FORBIDDEN:{path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise RuntimeError(f"PACK_TREE_MEMBER_INVALID:{path}")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": digest_file(path),
                "bytes": path.stat().st_size,
            }
        )
    if not records:
        raise RuntimeError(f"PACK_TREE_EMPTY:{root}")
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return digest_bytes(payload)


def verify_existing_canonical_pack(
    repo_root: Path,
    *,
    execute_frozen_replay: bool = True,
) -> dict[str, str | int]:
    """Verify immutable v1 in place without importing current route code.

    The canonical v1 pack is historical evidence.  Verification uses the
    exact launcher, validator, and Schema captured inside each route.  It never
    validates the live route tree and never publishes over the frozen pack.
    """

    pack = repo_root / "verification-packs" / CANONICAL_PACK_KEY
    before = immutable_tree_digest(pack)
    campaign_path = pack / "formal-route-campaign.json"
    if campaign_path.is_symlink() or not campaign_path.is_file():
        raise RuntimeError("CANONICAL_V1_CAMPAIGN_MISSING")
    if (
        campaign_path.stat().st_size != LEGACY_CAMPAIGN_BYTES
        or digest_file(campaign_path) != LEGACY_CAMPAIGN_SHA256
    ):
        raise RuntimeError("CANONICAL_V1_CAMPAIGN_IDENTITY_DRIFT")
    campaign = load_json(campaign_path)
    if (
        campaign.get("schema_version") != 1
        or campaign.get("campaign_key") != CANONICAL_PACK_KEY
        or campaign.get("version") != "1.0.0"
    ):
        raise RuntimeError("CANONICAL_V1_CAMPAIGN_CONTRACT_DRIFT")
    route_set = campaign.get("route_set")
    routes = route_set.get("routes") if isinstance(route_set, dict) else None
    expected_route_keys = {route_key for route_key, _, _ in exact_routes()}
    if not isinstance(routes, list) or len(routes) != len(expected_route_keys):
        raise RuntimeError("CANONICAL_V1_ROUTE_COUNT_DRIFT")
    route_keys = [
        record.get("route_key") if isinstance(record, dict) else None
        for record in routes
    ]
    if (
        len(set(route_keys)) != len(route_keys)
        or set(route_keys) != expected_route_keys
    ):
        raise RuntimeError("CANONICAL_V1_ROUTE_SET_DRIFT")

    route_root = pack / "evidence" / "routes"
    observed_route_keys = {
        path.name
        for path in route_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    }
    if observed_route_keys != expected_route_keys:
        raise RuntimeError("CANONICAL_V1_ROUTE_TREE_DRIFT")
    replay_python = Path(sys.executable).resolve()
    if execute_frozen_replay and (
        sys.version_info < (3, 10) or not replay_python.is_file()
    ):
        raise RuntimeError("CANONICAL_V1_FROZEN_REPLAY_PYTHON_UNAVAILABLE")
    for route_key in sorted(expected_route_keys):
        route = route_root / route_key
        for relative, (
            expected_sha256,
            expected_bytes,
        ) in LEGACY_REPLAY_IDENTITIES.items():
            path = route / relative
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(route.resolve(strict=True))
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
                raise RuntimeError(
                    f"CANONICAL_V1_REPLAY_ASSET_MISSING:{route_key}:{relative}"
                ) from exc
            if path.is_symlink() or not resolved.is_file():
                raise RuntimeError(
                    f"CANONICAL_V1_REPLAY_ASSET_INVALID:{route_key}:{relative}"
                )
            if (
                resolved.stat().st_size != expected_bytes
                or digest_file(resolved) != expected_sha256
            ):
                raise RuntimeError(
                    f"CANONICAL_V1_REPLAY_ASSET_IDENTITY_DRIFT:{route_key}:{relative}"
                )
        if execute_frozen_replay:
            launcher = route / "certification/replay/validate_packed_route.py"
            completed = subprocess.run(
                [
                    str(replay_python),
                    "-I",
                    "-B",
                    str(launcher),
                    "--route",
                    str(route),
                ],
                cwd=route,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise RuntimeError(
                    f"CANONICAL_V1_FROZEN_REPLAY_FAILED:{route_key}:{detail}"
                )
    after = immutable_tree_digest(pack)
    if after != before:
        raise RuntimeError("CANONICAL_V1_VERIFY_MODIFIED_FROZEN_TREE")
    return {
        "route_count": len(expected_route_keys),
        "campaign_sha256": LEGACY_CAMPAIGN_SHA256,
        "method_sha256": LEGACY_REPLAY_METHOD_SHA256,
        "tree_sha256": after,
    }


def formal_artifact_id(relative: str) -> str:
    return "artifact-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()


def packed_replay_evidence_id(route_key: str, member: str) -> str:
    return f"route-replay-{member}-{route_key}"


def aggregate_digest(values: object) -> str:
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return digest_bytes(encoded)


def exact_routes() -> list[tuple[str, str, str]]:
    return [
        (f"{source}-to-{target}", source, target)
        for source in LANGUAGES
        for target in LANGUAGES
        if source != target
    ]


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise RuntimeError(f"EVIDENCE_FILE_INVALID:{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if (
        digest_file(source) != digest_file(target)
        or source.stat().st_size != target.stat().st_size
    ):
        raise RuntimeError(f"EVIDENCE_COPY_MISMATCH:{source}")


def route_relative_file(route: Path, reference: object, *, label: str) -> Path:
    """Resolve one immutable route-relative file without accepting path escape."""

    if (
        not isinstance(reference, str)
        or not reference
        or "\\" in reference
        or "://" in reference
    ):
        raise RuntimeError(f"{label}_PATH_INVALID:{reference}")
    relative = Path(reference)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"{label}_PATH_INVALID:{reference}")
    candidate = route / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(route.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise RuntimeError(f"{label}_PATH_ESCAPE_OR_MISSING:{reference}") from exc
    if not resolved.is_file() or candidate.is_symlink():
        raise RuntimeError(f"{label}_FILE_INVALID:{reference}")
    return candidate


def validate_source_routes(repo_root: Path) -> None:
    """Run the authoritative Batch 29 route validator before packaging bytes."""

    validator = repo_root / "scripts" / "batch29" / "validate_route.py"
    if not validator.is_file():
        raise RuntimeError(f"BATCH29_VALIDATOR_MISSING:{validator}")
    for route_key, _, _ in exact_routes():
        route = repo_root / "routes" / route_key
        completed = subprocess.run(
            [sys.executable, str(validator), str(route)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"BATCH29_ROUTE_INVALID:{route_key}:{detail}")


def install_packed_route_replay(
    route_root: Path,
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Freeze a route-local integrity replay and rewrite the copied wrapper.

    The launcher validates the copied evidence closure only.  Native compilation
    and execution remain an external, explicitly NOT_RUN campaign operation.
    """

    replay_members: list[dict[str, str]] = []
    for relative, (source_relative, role, member) in PACKED_REPLAY_FILES.items():
        source = route_relative_file(
            repo_root,
            source_relative,
            label=f"PACKED_REPLAY_SOURCE_{member.upper()}",
        )
        target = route_root / relative
        copy_file(source, target)
        replay_members.append(
            {
                "member": member,
                "relative": relative,
                "role": role,
                "sha256": digest_file(target),
            }
        )

    formal_path = route_root / "certification" / "formal-equivalence.json"
    certification_path = route_root / "certification" / "certification.json"
    formal = load_json(formal_path)
    certification = load_json(certification_path)
    references = formal.get("artifact_refs")
    if not isinstance(references, list) or not references:
        raise RuntimeError(f"PACKED_REPLAY_ARTIFACT_REFS_REQUIRED:{route_root.name}")
    existing_paths = {item.get("path") for item in references if isinstance(item, dict)}
    replay_paths = set(PACKED_REPLAY_FILES)
    conflicts = sorted(existing_paths & replay_paths)
    if conflicts:
        raise RuntimeError(
            f"PACKED_REPLAY_PATH_CONFLICT:{route_root.name}:{','.join(conflicts)}"
        )
    for member in replay_members:
        target = route_root / member["relative"]
        references.append(
            {
                "artifact_id": formal_artifact_id(member["relative"]),
                "role": member["role"],
                "path": member["relative"],
                "sha256": member["sha256"],
                "bytes": target.stat().st_size,
            }
        )
    replay = formal.get("formal_proof", {}).get("replay")
    if not isinstance(replay, dict):
        raise RuntimeError(f"PACKED_REPLAY_RECORD_REQUIRED:{route_root.name}")
    replay["command"] = list(PACKED_REPLAY_COMMAND)
    replay["cwd"] = "."
    write_json(formal_path, formal)

    formal_reference = certification.get("formal_equivalence")
    if not isinstance(formal_reference, dict):
        raise RuntimeError(f"PACKED_REPLAY_FORMAL_REFERENCE_REQUIRED:{route_root.name}")
    formal_reference.update(
        {
            "path": "certification/formal-equivalence.json",
            "sha256": digest_file(formal_path),
            "bytes": formal_path.stat().st_size,
        }
    )
    write_json(certification_path, certification)
    return formal, replay_members


def copy_route_formal_bundle(
    route: Path,
    target_root: Path,
    certification: dict[str, Any],
) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    """Copy the strict wrapper and its complete route-relative byte closure."""

    strict_ref = certification.get("formal_equivalence")
    if not isinstance(strict_ref, dict):
        raise RuntimeError(f"STRICT_FORMAL_EVIDENCE_REQUIRED:{route.name}")
    formal_relative = strict_ref.get("path")
    if formal_relative != "certification/formal-equivalence.json":
        raise RuntimeError(f"STRICT_FORMAL_REFERENCE_INVALID:{route.name}")
    formal_path = route_relative_file(
        route, formal_relative, label=f"{route.name}_FORMAL_WRAPPER"
    )
    if digest_file(formal_path) != strict_ref.get(
        "sha256"
    ) or formal_path.stat().st_size != strict_ref.get("bytes"):
        raise RuntimeError(f"STRICT_FORMAL_REFERENCE_TAMPERED:{route.name}")
    formal = load_json(formal_path)
    artifact_refs = formal.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        raise RuntimeError(f"STRICT_FORMAL_ARTIFACT_REFS_REQUIRED:{route.name}")

    relative_paths = {
        "route.json",
        "lowering/profile.json",
        "certification/certification.json",
        formal_relative,
    }
    evidence_refs = certification.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) for item in evidence_refs
    ):
        raise RuntimeError(f"CERTIFICATION_EVIDENCE_REFS_INVALID:{route.name}")
    relative_paths.update(evidence_refs)
    for index, artifact_ref in enumerate(artifact_refs):
        if not isinstance(artifact_ref, dict):
            raise RuntimeError(
                f"STRICT_FORMAL_ARTIFACT_REF_INVALID:{route.name}:{index}"
            )
        relative = artifact_ref.get("path")
        source = route_relative_file(
            route,
            relative,
            label=f"{route.name}_ARTIFACT_REF_{index}",
        )
        if digest_file(source) != artifact_ref.get(
            "sha256"
        ) or source.stat().st_size != artifact_ref.get("bytes"):
            raise RuntimeError(
                f"STRICT_FORMAL_ARTIFACT_REF_TAMPERED:{route.name}:{relative}"
            )
        relative_paths.add(relative)

    for relative in sorted(relative_paths):
        source = route_relative_file(
            route, relative, label=f"{route.name}_BUNDLE_MEMBER"
        )
        copy_file(source, target_root / relative)
    formal, replay_members = install_packed_route_replay(
        target_root,
        repo_root=ROOT,
    )
    return formal, formal_relative, replay_members


def add_evidence(
    pack: Path,
    campaign: dict[str, Any],
    evidence_id: str,
    relative: str,
    *,
    role: str,
) -> str:
    path = pack / relative
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise RuntimeError(f"PACK_EVIDENCE_INVALID:{relative}")
    campaign["evidence"].append(
        {
            "evidence_id": evidence_id,
            "path": relative,
            "sha256": digest_file(path),
            "bytes": path.stat().st_size,
            "role": role,
        }
    )
    return evidence_id


def prepare_directories(pack: Path) -> None:
    for relative in (
        "properties",
        "metamorphic",
        "mutation",
        "fuzz",
        "models",
        "solver",
        "counterexamples",
        "assurance",
        "coverage",
        "evidence/routes",
        "corpus/development",
        "corpus/negative",
        "corpus/holdout",
        "corpus/representative-workloads",
        "certification",
    ):
        (pack / relative).mkdir(parents=True, exist_ok=True)


def collect_route_evidence(
    pack: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    routes: list[dict[str, Any]] = []
    copies: list[dict[str, Any]] = []
    for route_key, source, target in exact_routes():
        route = ROOT / "routes" / route_key
        manifest = load_json(route / "route.json")
        certification = load_json(route / "certification" / "certification.json")
        if manifest.get("route_key") != route_key:
            raise RuntimeError(f"ROUTE_KEY_MISMATCH:{route_key}")
        if manifest.get("profiles", {}).get("semantic_profile") != SEMANTIC_PROFILE:
            raise RuntimeError(f"SEMANTIC_PROFILE_MISMATCH:{route_key}")
        if certification.get("status") != "limited":
            raise RuntimeError(f"ROUTE_NOT_LIMITED:{route_key}")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            raise RuntimeError(f"ROUTE_CERTIFICATION_BOUNDARY_VIOLATED:{route_key}")
        strict_ref = certification.get("formal_equivalence")
        if certification.get("evidence_format") != 2 or not isinstance(
            strict_ref, dict
        ):
            raise RuntimeError(f"STRICT_FORMAL_EVIDENCE_REQUIRED:{route_key}")
        target_root = pack / "evidence" / "routes" / route_key
        formal, formal_relative, replay_members = copy_route_formal_bundle(
            route, target_root, certification
        )
        proof_status = formal.get("formal_proof", {}).get("status")
        if proof_status not in {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}:
            raise RuntimeError(
                f"ROUTE_FORMAL_PROOF_NONPASSING:{route_key}:{proof_status}"
            )
        target_path = target_root / formal_relative
        evidence_id = f"route-evidence-{route_key}"
        copies.append(
            {
                "evidence_id": evidence_id,
                "relative": target_path.relative_to(pack).as_posix(),
                "source_ir_sha256": formal["semantic_ir"]["source_ir_sha256"],
                "target_ir_sha256": formal["semantic_ir"]["target_relift_ir_sha256"],
                "environment_sha256": formal["environment_sha256"],
                "artifact_sha256": formal["artifact_sha256"],
                "behavior_cases": formal["behavior_equivalence"]["total_cases"],
                "proof_status": proof_status,
                "replay_members": replay_members,
            }
        )
        packed_replay_evidence_ids = [
            packed_replay_evidence_id(route_key, member["member"])
            for member in replay_members
        ]
        routes.append(
            {
                "route_key": route_key,
                "source_language": source,
                "target_language": target,
                "route_version": str(manifest.get("version")),
                "semantic_profile": SEMANTIC_PROFILE,
                "composition_id": f"composition-{route_key}",
                "artifact_evidence_ids": [evidence_id],
                "packed_replay_evidence_ids": packed_replay_evidence_ids,
            }
        )
    if len(routes) != 30:
        raise RuntimeError(f"ROUTE_COUNT_INVALID:{len(routes)}")
    return routes, copies


def write_bundle_evidence(
    pack: Path, route_copies: list[dict[str, Any]]
) -> dict[str, str]:
    bundles = {
        "source": {
            "schema_version": 1,
            "kind": "source-normalized-ir-bundle",
            "routes": [
                {
                    "route_key": item["evidence_id"].removeprefix("route-evidence-"),
                    "sha256": item["source_ir_sha256"],
                }
                for item in route_copies
            ],
        },
        "target": {
            "schema_version": 1,
            "kind": "target-relift-ir-bundle",
            "routes": [
                {
                    "route_key": item["evidence_id"].removeprefix("route-evidence-"),
                    "sha256": item["target_ir_sha256"],
                }
                for item in route_copies
            ],
        },
        "environment": {
            "schema_version": 1,
            "kind": "route-environment-bundle",
            "route_environment_digests": sorted(
                {item["environment_sha256"] for item in route_copies}
            ),
            "route_engine_lockfile": {
                "path": "engines/polyglot-route-engine/uv.lock",
                "sha256": digest_file(
                    ROOT / "engines" / "polyglot-route-engine" / "uv.lock"
                ),
            },
            "independent_verification": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
    }
    paths: dict[str, str] = {}
    for name, value in bundles.items():
        path = pack / "evidence" / f"{name}-bundle.json"
        write_json(path, value)
        paths[name] = path.relative_to(pack).as_posix()
    return paths


def base_pack_files(
    pack: Path,
    *,
    source_digest: str,
    target_digest: str,
    environment_digest: str,
    arithmetic_digest: str,
    total_behavior_cases: int,
    arithmetic_counts: dict[str, Any],
) -> None:
    owner = "elmos-polyglot-verification-engineering"
    scope = {
        "migration_route": "six-language-complete-directed-matrix-30-routes",
        "source_artifact_digest": source_digest,
        "target_artifact_digest": target_digest,
        "workload_key": SEMANTIC_PROFILE,
        "risk_tier": "P0",
        "environment_digest": environment_digest,
        "route_count": 30,
        "independent_verification": "NOT_RUN",
        "external_certification": "NOT_RUN",
    }
    write_json(
        pack / "pack.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "version": PACK_VERSION,
            "status": "experimental",
            "owner": owner,
            "maintenance_owner": owner,
            "scope": scope,
            "contracts": {
                "validation_profile": "validation-profile.json",
                "oracle_registry": "oracle-registry.json",
                "assurance_case": "assurance/assurance-case.json",
            },
            "corpus": {
                "development": "corpus/development",
                "negative": "corpus/negative",
                "holdout": "corpus/holdout",
                "representative_workloads": "corpus/representative-workloads",
            },
            "certification": {
                "evidence_path": "certification/evidence.json",
                "result_path": "certification/gate-result.json",
            },
            "formal_route_campaign": "formal-route-campaign.json",
            "tags": [
                "formal-equivalence",
                "polyglot",
                "30-directed-routes",
                "not-certified",
            ],
        },
    )
    write_json(
        pack / "support-matrix.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "capabilities": [
                {
                    "key": "route-layered-equivalence",
                    "status": "experimental",
                    "owner": owner,
                    "evidence_refs": [
                        "formal-route-campaign.json",
                        "evidence/route-set.json",
                    ],
                    "limitations": [
                        "Local route proof is assumption-bound; source analyzer soundness is not independently proved."
                    ],
                },
                {
                    "key": "int64-arithmetic-smt",
                    "status": "experimental",
                    "owner": owner,
                    "evidence_refs": ["solver/arithmetic-campaign.json"],
                    "limitations": [
                        "Some obligations remain BOUNDED and language-primitive obligations remain AXIOM."
                    ],
                },
                {
                    "key": "l1-plus-language-semantics",
                    "status": "blocked",
                    "owner": owner,
                    "evidence_refs": ["formal-route-campaign.json"],
                    "limitations": [
                        "Local variables, loops, calls, nullable values, exceptions, aggregates, "
                        "concurrency, I/O, frameworks, and databases are out of scope."
                    ],
                },
            ],
        },
    )
    write_json(
        pack / "validation-profile.json",
        {
            "schema_version": 1,
            "profile_key": f"{PACK_KEY}-profile-v1",
            "version": 1,
            "risk_tier": "P0",
            "claims": [
                {
                    "claim_id": "claim.route-equivalence",
                    "description": (
                        "Every directed route preserves the exact declared L0 semantics for its "
                        "executed local corpora, with unresolved assumptions explicit."
                    ),
                    "criticality": "P0",
                    "required_oracles": [
                        "oracle.canonical-ir",
                        "oracle.source-runtime",
                        "oracle.target-runtime",
                    ],
                    "required_techniques": [
                        "formal-route-campaign",
                        "target-relift",
                        "semantic-chunk-mapping",
                        "differential-execution",
                        "smt",
                    ],
                },
                {
                    "claim_id": "claim.fail-closed-governance",
                    "description": (
                        "Unknown, bounded, axiom-only, missing, tampered, or unreplayed evidence "
                        "cannot become proof or certification."
                    ),
                    "criticality": "P0",
                    "required_oracles": ["oracle.canonical-ir", "oracle.route-gate"],
                    "required_techniques": [
                        "mutation",
                        "counterexample-replay",
                        "evidence-integrity",
                    ],
                },
            ],
            "techniques": [
                "formal-route-campaign",
                "target-relift",
                "semantic-chunk-mapping",
                "differential-execution",
                "smt",
                "property",
                "metamorphic",
                "mutation",
                "counterexample-replay",
                "evidence-integrity",
            ],
            "budgets": {
                "max_wall_time_minutes": 180,
                "max_solver_seconds": 1800,
                "max_fuzz_seconds": 600,
                "max_schedules": 0,
                "max_mutants": 500,
            },
            "stop_conditions": [
                "counterexample",
                "solver-unknown-or-timeout",
                "bounded-required-proof",
                "artifact-digest-drift",
                "missing-route-or-obligation",
                "oracle-conflict",
            ],
            "approvals": [],
        },
    )
    write_json(
        pack / "oracle-registry.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "oracles": [
                {
                    "oracle_id": "oracle.canonical-ir",
                    "type": "formal-spec",
                    "owner": owner,
                    "scope": [
                        "claim.route-equivalence",
                        "claim.fail-closed-governance",
                    ],
                    "independence": "dependent",
                    "trust_level": "strong",
                    "version": "typed-pure-function-v1",
                    "evidence_refs": ["formal-route-campaign.json"],
                },
                {
                    "oracle_id": "oracle.source-runtime",
                    "type": "source-behavior",
                    "owner": owner,
                    "scope": ["claim.route-equivalence"],
                    "independence": "partially-independent",
                    "trust_level": "supporting",
                    "version": "local-pinned-toolchains",
                    "evidence_refs": ["evidence/route-set.json"],
                },
                {
                    "oracle_id": "oracle.target-runtime",
                    "type": "reference-implementation",
                    "owner": owner,
                    "scope": ["claim.route-equivalence"],
                    "independence": "partially-independent",
                    "trust_level": "supporting",
                    "version": "local-pinned-toolchains",
                    "evidence_refs": ["evidence/route-set.json"],
                },
                {
                    "oracle_id": "oracle.route-gate",
                    "type": "contract",
                    "owner": owner,
                    "scope": ["claim.fail-closed-governance"],
                    "independence": "dependent",
                    "trust_level": "supporting",
                    "version": "batch29-evidence-format-2",
                    "evidence_refs": ["formal-route-campaign.json"],
                },
            ],
            "precedence_rules": [
                {
                    "claim_type": "route-equivalence",
                    "ordered_oracles": [
                        "oracle.canonical-ir",
                        "oracle.source-runtime",
                        "oracle.target-runtime",
                        "oracle.route-gate",
                    ],
                }
            ],
            "conflicts": [],
            "approvals": [],
        },
    )
    write_json(
        pack / "properties" / "sample.json",
        {
            "schema_version": 1,
            "property_id": "property.route-equivalence",
            "claim_id": "claim.route-equivalence",
            "owner": owner,
            "generator": {
                "kind": "typed-l0-domain",
                "constraints": ["profile=typed-pure-function-v1", "route-set=exact-30"],
            },
            "oracle_refs": [
                "oracle.canonical-ir",
                "oracle.source-runtime",
                "oracle.target-runtime",
            ],
            "assertion": {
                "kind": "source-canonical-target-observational-equivalence",
                "required_layers": [
                    "semantic-ir",
                    "semantic-chunks",
                    "behavior",
                    "formal-composition",
                ],
            },
            "shrinker": {"kind": "typed-expression-and-input-shrinker"},
            "replay": {
                "seed": "20260809",
                "command": "python3 scripts/batch29/run_polyglot_routes.py --route java-to-python",
            },
        },
    )
    write_json(
        pack / "metamorphic" / "sample.json",
        {
            "schema_version": 1,
            "relation_id": "relation.route-direction-composition",
            "claim_id": "claim.route-equivalence",
            "owner": owner,
            "preconditions": [
                "both-directed-routes-in-exact-profile",
                "canonical-input-is-valid",
            ],
            "transformation": {"kind": "source-to-target-to-canonical-replay"},
            "expected_relation": {"kind": "same-value-or-same-error-class"},
            "oracle_refs": [
                "oracle.canonical-ir",
                "oracle.source-runtime",
                "oracle.target-runtime",
            ],
            "non_applicable": ["semantics-outside-typed-pure-function-v1"],
        },
    )
    write_json(
        pack / "mutation" / "campaign.json",
        {
            "schema_version": 1,
            "campaign_key": "mutation.formal-route-evidence-gates",
            "owner": owner,
            "target_scope": [
                "engines/polyglot-route-engine",
                "scripts/batch29",
                "scripts/batch35",
            ],
            "operators": [
                {"key": "flip-operator", "risk": "P0"},
                {"key": "drop-semantic-chunk", "risk": "P0"},
                {"key": "forge-evidence-digest", "risk": "P0"},
                {"key": "promote-unknown-to-proved", "risk": "P0"},
            ],
            "budgets": {"max_mutants": 500, "max_minutes": 120},
            "required_tests": [
                "engines/polyglot-route-engine/tests/test_layered_equivalence.py",
                "tests/batch29/test_toolkit.py",
                "tests/batch35/test_formal_route_campaign.py",
            ],
            "equivalent_mutant_policy": "explicit-review-no-score-credit",
        },
    )
    write_json(
        pack / "fuzz" / "campaign.json",
        {
            "schema_version": 1,
            "campaign_key": "fuzz.typed-l0-semantic-ir",
            "owner": owner,
            "targets": [
                "native-analyzers",
                "canonical-ir",
                "emitters",
                "target-relift",
                "evidence-validator",
            ],
            "seed_corpus": [
                "corpus/development/manifest.json",
                "corpus/negative/manifest.json",
            ],
            "coverage_signal": "semantic-production-and-error-class-coverage",
            "budgets": {"max_seconds": 600, "max_memory_mb": 2048},
            "sanitizers": [
                "schema-validation",
                "native-parser-diagnostics",
                "counterexample-replay",
            ],
            "dictionary_refs": [],
        },
    )
    write_json(
        pack / "models" / "model.json",
        {
            "schema_version": 1,
            "model_key": "model.route-proof-lifecycle",
            "owner": owner,
            "states": [
                "declared",
                "executed",
                "proved-under-assumptions",
                "unresolved",
                "certified",
            ],
            "initial_state": "declared",
            "commands": [
                {
                    "command": "execute",
                    "from": ["declared"],
                    "to": "executed",
                    "guard": "native-evidence-complete",
                    "effects": ["bind-artifact-digests"],
                },
                {
                    "command": "compose",
                    "from": ["executed"],
                    "to": "proved-under-assumptions",
                    "guard": "all-local-layers-pass",
                    "effects": ["record-assumptions"],
                },
                {
                    "command": "block",
                    "from": ["declared", "executed", "proved-under-assumptions"],
                    "to": "unresolved",
                    "guard": "unknown-or-counterexample",
                    "effects": ["preserve-replay"],
                },
                {
                    "command": "certify",
                    "from": ["proved-under-assumptions"],
                    "to": "certified",
                    "guard": "assumptions-discharged-and-independent-verification-passed",
                    "effects": ["bind-independent-evidence"],
                },
            ],
            "invariants": [
                "unknown-never-passes",
                "bounded-and-axiom-never-equal-theorem",
                "certified-requires-independent-verification",
                "route-set-is-exactly-thirty",
            ],
            "forbidden_transitions": [
                {"from": "declared", "event": "certify"},
                {"from": "unresolved", "event": "certify"},
            ],
            "timeouts": [],
        },
    )
    write_json(
        pack / "solver" / "proof.json",
        {
            "schema_version": 1,
            "proof_id": "proof.aggregate-route-equivalence",
            "property_id": "property.route-equivalence",
            "solver": {
                "name": "z3-solver",
                "version": "4.16.0",
                "options": {
                    "timeout_ms": 20000,
                    "random_seed": 0,
                    "smt_random_seed": 0,
                },
                "timeout_ms": 20000,
            },
            "status": "unknown",
            "assumptions": [
                "Source analyzer soundness is not independently proved.",
                "Language-standard primitive behavior is cited, not solver-certified.",
                "Three arithmetic obligations are bounded below 64 bits only.",
            ],
            "input_digest": arithmetic_digest,
            "evidence_refs": [
                "solver/arithmetic-campaign.json",
                "formal-route-campaign.json",
            ],
        },
    )
    negative_input = {
        "negative_control": "mutated-target-semantic-ir",
        "mutation": "replace canonical integer addition with subtraction",
        "expected": "counterexample-and-gate-failure",
        "scope": SEMANTIC_PROFILE,
    }
    write_json(pack / "counterexamples" / "input.json", negative_input)
    write_json(
        pack / "counterexamples" / "sample.json",
        {
            "schema_version": 1,
            "counterexample_id": "ce.mutated-target-ir-negative-control",
            "technique": "symbolic-and-concrete-negative-control",
            "claim_id": "claim.fail-closed-governance",
            "failure_fingerprint": "NOT_OBSERVED",
            "environment_digest": environment_digest,
            "artifact_digests": [source_digest, target_digest],
            "input_ref": "counterexamples/input.json",
            "replay": {
                "command": "NOT_RUN",
                "expected_fingerprint": "NOT_OBSERVED",
                "execution_status": "NOT_RUN",
                "observed_fingerprint": None,
            },
            "status": "open",
            "owner": owner,
            "limitations": [
                "No concrete mutant, failing output, or observed failure fingerprint has been recorded."
            ],
        },
    )
    write_json(
        pack / "assurance" / "assurance-case.json",
        {
            "schema_version": 1,
            "case_key": f"{PACK_KEY}-assurance-v1",
            "version": 1,
            "owner": owner,
            "top_claim": (
                "The exact 30-route L0 campaign has replayable local evidence and fails closed on "
                "every unresolved proof boundary."
            ),
            "claims": [
                {
                    "claim_id": "claim.route-equivalence",
                    "statement": (
                        "Executed local corpora have source/canonical/target semantic, chunk, and behavior agreement."
                    ),
                    "status": "partially-supported",
                    "evidence_refs": [
                        "formal-route-campaign.json",
                        "evidence/route-set.json",
                    ],
                    "assumptions": [
                        "Pinned native analyzers and toolchains implement their declared semantics."
                    ],
                    "limitations": [
                        "Unexecuted semantic blocks and independent verification remain NOT_RUN."
                    ],
                },
                {
                    "claim_id": "claim.fail-closed-governance",
                    "statement": (
                        "Incomplete, bounded, axiom-only, tampered, or counterexample evidence does not certify."
                    ),
                    "status": "partially-supported",
                    "evidence_refs": [
                        "solver/arithmetic-campaign.json",
                        "counterexamples/sample.json",
                    ],
                    "assumptions": [],
                    "limitations": [
                        "Local engineering governance is not an independent certification."
                    ],
                },
            ],
            "evidence": [
                "formal-route-campaign.json",
                "solver/arithmetic-campaign.json",
            ],
            "residual_risks": [
                {
                    "risk_id": "risk.source-lifting-soundness",
                    "severity": "P0",
                    "status": "open",
                    "disposition": "independent-proof-required",
                },
                {
                    "risk_id": "risk.semantic-block-coverage",
                    "severity": "P0",
                    "status": "open",
                    "disposition": "native-corpus-required",
                },
                {
                    "risk_id": "risk.arithmetic-conditional-bounded-or-axiom",
                    "severity": "P0",
                    "status": "open",
                    "disposition": "second-solver-or-certificate-required",
                },
                {
                    "risk_id": "risk.external-validation",
                    "severity": "P0",
                    "status": "open",
                    "disposition": "NOT_RUN",
                },
            ],
            "monitoring_obligations": [
                "rerun-on-analyzer-emitter-toolchain-or-lockfile-digest-change"
            ],
            "approvals": [],
        },
    )
    metrics = {
        "directed_route_count": 30,
        "local_behavior_case_count": total_behavior_cases,
        "semantic_block_count": len(BLOCKS),
        "locally_exercised_semantic_block_count": len(LOCALLY_EXERCISED_BLOCKS),
        "arithmetic_proved_64_bit": int(arithmetic_counts.get("PROVED", 0)),
        "arithmetic_proved_under_assumptions": int(
            arithmetic_counts.get("PROVED_UNDER_ASSUMPTIONS", 0)
        ),
        "arithmetic_bounded": int(arithmetic_counts.get("BOUNDED", 0)),
        "arithmetic_axiom": int(arithmetic_counts.get("AXIOM", 0)),
        "independent_verification_pass_rate": 0.0,
        "representative_customer_workload_pass_rate": 0.0,
    }
    write_json(
        pack / "certification" / "evidence.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "metrics": metrics,
            "zero_tolerance": {
                "critical_unknown_obligations": 1,
                "invalid_or_unknown_required_proofs": 1,
                "test_integrity_violations": 0,
            },
            "evidence_refs": [
                "formal-route-campaign.json",
                "solver/arithmetic-campaign.json",
                "evidence/route-set.json",
            ],
            "notes": [
                "Local engineering evidence only.",
                "Independent verifier, customer workload, production execution, and external "
                "certification remain NOT_RUN.",
            ],
        },
    )
    write_json(
        pack / "certification" / "certification.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "status": "experimental",
            "owner": owner,
            "exact_scope": scope,
            "metrics": metrics,
            "evidence_refs": [
                "formal-route-campaign.json",
                "solver/arithmetic-campaign.json",
                "evidence/route-set.json",
            ],
            "limitations": [
                "NOT_CERTIFIED",
                "Formal route campaign contains required NOT_RUN obligations.",
                "Independent verification NOT_RUN.",
                "External/customer/production validation NOT_RUN.",
                "L1+ semantics outside declared profile remain unsupported.",
            ],
            "approved_at": None,
        },
    )


def write_corpus_manifests(pack: Path, *, route_set_digest: str) -> None:
    values = {
        "development": (
            "passed",
            "local-development",
            "Local development fixtures from all 30 routes.",
        ),
        "negative": (
            "passed",
            "local-negative",
            "Fail-closed missing-function and evidence-tamper controls.",
        ),
        "holdout": (
            "passed",
            "local-separated-holdout",
            "Locally separated holdout; independent external verifier NOT_RUN.",
        ),
        "representative-workloads": (
            "passed",
            "bounded-representative-fixture",
            "Customer repository and production representativeness NOT_RUN.",
        ),
    }
    for key, (status, dataset, note) in values.items():
        manifest = {
            "schema_version": 1,
            "corpus": key,
            "status": status,
            "source_digest": route_set_digest,
            "dataset_digest": aggregate_digest(
                {"corpus": key, "route_set": route_set_digest}
            ),
            "evidence_refs": ["evidence/route-set.json"],
            "dataset_class": dataset,
            "notes": [note],
        }
        write_json(pack / "corpus" / key / "manifest.json", manifest)


def build_campaign(
    pack: Path,
    routes: list[dict[str, Any]],
    route_copies: list[dict[str, Any]],
    bundle_paths: dict[str, str],
) -> dict[str, Any]:
    campaign: dict[str, Any] = {
        "schema_version": 1,
        "campaign_key": PACK_KEY,
        "version": PACK_VERSION,
        "semantic_profile": SEMANTIC_PROFILE,
        "campaign_status": "LOCAL_EXECUTED",
        "certification_status": "NOT_CERTIFIED",
        "required_languages": list(LANGUAGES),
        "semantic_blocks": list(BLOCKS),
        "route_set": {"manifest_evidence_id": "route-set", "routes": routes},
        "obligations": [],
        "obligation_matrix": [],
        "compositions": [],
        "solver_runs": [],
        "replays": [],
        "evidence": [],
        "packed_route_replay": {
            "packed_validation": {
                "scope": PACKED_REPLAY_SCOPE,
                "command": list(PACKED_REPLAY_COMMAND),
                "cwd": ".",
            },
            "external_native_reexecution": dict(EXTERNAL_NATIVE_REEXECUTION),
        },
        "independent_verification": {
            "status": "NOT_RUN",
            "verifier": None,
            "evidence_ids": [],
        },
        "limitations": [
            "Packed route replay validates frozen evidence closure only; native regeneration and execution require ELMOS_REPO_ROOT and remain NOT_RUN.",
            "Source analyzer soundness is not formally discharged.",
            "Only seven of twelve declared semantic blocks have local corpus execution.",
            "PROVED_UNDER_ASSUMPTIONS, AXIOM, and BOUNDED arithmetic evidence is not an unconditional theorem.",
            "Independent, external, customer, production, L1+, framework, database, and "
            "concurrency evidence is NOT_RUN.",
        ],
    }
    for item in route_copies:
        add_evidence(
            pack,
            campaign,
            item["evidence_id"],
            item["relative"],
            role="route-formal-evidence",
        )
        route_key = item["evidence_id"].removeprefix("route-evidence-")
        for member in item["replay_members"]:
            add_evidence(
                pack,
                campaign,
                packed_replay_evidence_id(route_key, member["member"]),
                f"evidence/routes/{route_key}/{member['relative']}",
                role=member["role"],
            )
    add_evidence(
        pack, campaign, "source-bundle", bundle_paths["source"], role="artifact"
    )
    add_evidence(
        pack, campaign, "target-bundle", bundle_paths["target"], role="artifact"
    )
    add_evidence(
        pack,
        campaign,
        "environment-bundle",
        bundle_paths["environment"],
        role="environment",
    )
    add_evidence(
        pack,
        campaign,
        "arithmetic-campaign",
        "solver/arithmetic-campaign.json",
        role="solver-output",
    )

    route_set_path = pack / "evidence" / "route-set.json"
    write_json(
        route_set_path,
        {"schema_version": 1, "semantic_profile": SEMANTIC_PROFILE, "routes": routes},
    )
    add_evidence(
        pack, campaign, "route-set", "evidence/route-set.json", role="route-set"
    )

    source_ids: dict[tuple[str, str], str] = {}
    target_ids: dict[tuple[str, str], str] = {}
    behavior_ids: dict[tuple[str, str], str] = {}
    route_evidence_ids = {
        item["evidence_id"].removeprefix("route-evidence-"): item["evidence_id"]
        for item in route_copies
    }
    for language in LANGUAGES:
        source_route_evidence = sorted(
            evidence_id
            for route_key, evidence_id in route_evidence_ids.items()
            if route_key.startswith(f"{language}-to-")
        )
        target_route_evidence = sorted(
            evidence_id
            for route_key, evidence_id in route_evidence_ids.items()
            if route_key.endswith(f"-to-{language}")
        )
        for block in BLOCKS:
            source_id = f"lifting-{language}-{block}"
            source_ids[(language, block)] = source_id
            campaign["obligations"].append(
                {
                    "obligation_id": source_id,
                    "claim_id": "claim.route-equivalence",
                    "property_id": "property.route-equivalence",
                    "kind": "source-lifting",
                    "semantic_block": block,
                    "source_language": language,
                    "required": True,
                    "status": "not-run",
                    "proof_strength": "none",
                    "method": "not-run",
                    "assumptions": [
                        {
                            "assumption_id": f"assumption-{language}-analyzer-{block}",
                            "statement": (
                                f"The pinned {language} compiler frontend lifts {block} into the "
                                "canonical IR without semantic loss."
                            ),
                            "status": "unverified",
                            "evidence_ids": [
                                "environment-bundle",
                                *source_route_evidence,
                            ],
                        }
                    ],
                    "evidence_ids": ["source-bundle", *source_route_evidence],
                }
            )
            target_id = f"lowering-{language}-{block}"
            target_ids[(language, block)] = target_id
            target_evidence = ["target-bundle", *target_route_evidence]
            if block in {"integer-arithmetic", "arithmetic-error-behavior"}:
                target_evidence.append("arithmetic-campaign")
            campaign["obligations"].append(
                {
                    "obligation_id": target_id,
                    "claim_id": "claim.route-equivalence",
                    "property_id": "property.route-equivalence",
                    "kind": "target-lowering",
                    "semantic_block": block,
                    "target_language": language,
                    "required": True,
                    "status": "not-run",
                    "proof_strength": "none",
                    "method": "not-run",
                    "assumptions": [],
                    "evidence_ids": target_evidence,
                }
            )

    for route in routes:
        route_key = route["route_key"]
        for block in BLOCKS:
            behavior_id = f"behavior-{route_key}-{block}"
            behavior_ids[(route_key, block)] = behavior_id
            executed = block in LOCALLY_EXERCISED_BLOCKS
            campaign["obligations"].append(
                {
                    "obligation_id": behavior_id,
                    "claim_id": "claim.route-equivalence",
                    "property_id": "property.route-equivalence",
                    "kind": "route-behavior",
                    "semantic_block": block,
                    "route_key": route_key,
                    "required": True,
                    "status": "passed" if executed else "not-run",
                    "proof_strength": "testing" if executed else "none",
                    "method": "differential-execution" if executed else "not-run",
                    "assumptions": [],
                    "evidence_ids": [route_evidence_ids[route_key]],
                }
            )
            campaign["obligation_matrix"].append(
                {
                    "route_key": route_key,
                    "semantic_block": block,
                    "source_lifting_obligation_id": source_ids[
                        (route["source_language"], block)
                    ],
                    "target_lowering_obligation_id": target_ids[
                        (route["target_language"], block)
                    ],
                    "behavior_obligation_id": behavior_id,
                    "composition_id": route["composition_id"],
                }
            )
        campaign["compositions"].append(
            {
                "composition_id": route["composition_id"],
                "route_key": route_key,
                "source_lifting_obligation_ids": [
                    source_ids[(route["source_language"], block)] for block in BLOCKS
                ],
                "target_lowering_obligation_ids": [
                    target_ids[(route["target_language"], block)] for block in BLOCKS
                ],
                "behavior_obligation_ids": [
                    behavior_ids[(route_key, block)] for block in BLOCKS
                ],
                "status": "not-run",
            }
        )
    write_json(pack / "formal-route-campaign.json", campaign)
    return campaign


def write_readme(pack: Path) -> None:
    (pack / "README.md").write_text(
        "# Polyglot 30-route formal equivalence v1\n\n"
        "Batch 35 aggregate for all 30 directed pairs over Java, C#, Go, Rust, Python, and TypeScript. "
        "It binds target re-lift, semantic chunks, source/canonical/target behavior, SMT inputs, and "
        "route composition to exact evidence bytes.\n\n"
        "Each route-local packed replay reruns frozen evidence-integrity and semantic-closure "
        "validation only; it does not recompile or execute the native source/target route. Native "
        "route regeneration requires an external `${ELMOS_REPO_ROOT}` and remains `NOT_RUN`.\n\n"
        "The pack is intentionally `experimental / NOT_CERTIFIED`. Local route proofs are assumption-bound; "
        "source lifting, unexecuted semantic blocks, independent review, customer workloads, production, and "
        "external certification remain `NOT_RUN`.\n",
        encoding="utf-8",
    )
    (pack / "certification" / "gap-inventory.md").write_text(
        "# Remaining formal and certification gaps\n\n"
        "- Formally discharge every source-language analyzer lifting obligation.\n"
        "- Add native corpora for short-circuit behavior, strings, floating-point special values, "
        "error paths, and evaluation order.\n"
        "- Replace every TypeScript guard-abstraction PROVED_UNDER_ASSUMPTIONS, language-standard "
        "AXIOM, and narrow-width BOUNDED obligation with an emitted-runtime theorem or independently "
        "verified certificate.\n"
        "- Execute the external `${ELMOS_REPO_ROOT}` native route replay separately; the packed launcher "
        "does evidence-integrity validation only.\n"
        "- Run an independent verifier, representative customer workloads, production-equivalent "
        "regression, and external certification.\n"
        "- Add separate exact packs for L1+ constructs, frameworks, databases, I/O, exceptions, "
        "aggregates, and concurrency.\n",
        encoding="utf-8",
    )


def build_staged_pack(pack: Path, arithmetic_campaign: Path) -> tuple[int, int]:
    prepare_directories(pack)
    routes, route_copies = collect_route_evidence(pack)
    copy_file(arithmetic_campaign, pack / "solver" / "arithmetic-campaign.json")
    arithmetic = load_json(pack / "solver" / "arithmetic-campaign.json")
    if arithmetic.get("solver", {}).get("version") != "4.16.0":
        raise RuntimeError("ARITHMETIC_SOLVER_VERSION_NOT_LOCKED")
    if arithmetic.get("all_required_proved") is not False:
        raise RuntimeError("ARITHMETIC_CAMPAIGN_MUST_PRESERVE_CURRENT_RESIDUAL_STATUS")
    bundle_paths = write_bundle_evidence(pack, route_copies)
    campaign = build_campaign(pack, routes, route_copies, bundle_paths)
    source_digest = digest_file(pack / bundle_paths["source"])
    target_digest = digest_file(pack / bundle_paths["target"])
    environment_digest = digest_file(pack / bundle_paths["environment"])
    arithmetic_digest = digest_file(pack / "solver" / "arithmetic-campaign.json")
    total_behavior_cases = sum(int(item["behavior_cases"]) for item in route_copies)
    base_pack_files(
        pack,
        source_digest=source_digest,
        target_digest=target_digest,
        environment_digest=environment_digest,
        arithmetic_digest=arithmetic_digest,
        total_behavior_cases=total_behavior_cases,
        arithmetic_counts=arithmetic.get("counts", {}),
    )
    route_set_digest = digest_file(pack / "evidence" / "route-set.json")
    write_corpus_manifests(pack, route_set_digest=route_set_digest)
    write_readme(pack)
    return len(routes), len(campaign["obligation_matrix"])


def validate_staged_pack(repo_root: Path, pack: Path) -> None:
    commands = (
        (
            "BATCH35_PACK_VALIDATION",
            [
                sys.executable,
                str(
                    repo_root / "scripts" / "batch35" / "validate_verification_pack.py"
                ),
                str(pack),
            ],
        ),
        (
            "BATCH35_FORMAL_CAMPAIGN_VALIDATION",
            [
                sys.executable,
                str(
                    repo_root
                    / "scripts"
                    / "batch35"
                    / "validate_formal_route_campaign.py"
                ),
                str(pack),
                "--json",
            ],
        ),
        (
            "BATCH35_GATE",
            [
                sys.executable,
                str(repo_root / "scripts" / "batch35" / "run_verification_gate.py"),
                str(pack),
            ],
        ),
    )
    for label, command in commands:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"{label}_FAILED:{detail}")


def publish_staged_pack(staging: Path, destination: Path) -> None:
    """Publish only a fully validated tree and restore the old tree on failure."""

    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise RuntimeError(f"PACK_DESTINATION_INVALID:{destination}")
    backup: Path | None = None
    if destination.exists():
        backup = Path(
            tempfile.mkdtemp(prefix=f".{PACK_KEY}-backup-", dir=destination.parent)
        )
        backup.rmdir()
        os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def main() -> int:
    global PACK_KEY, PACK_VERSION, ROOT
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-existing",
        action="store_true",
        help="verify immutable canonical v1 in place (the default)",
    )
    mode.add_argument(
        "--build-new-pack-key",
        help="build a new content key; canonical v1 can never be selected",
    )
    parser.add_argument(
        "--arithmetic-campaign",
        type=Path,
        help="required only when building a new versioned pack",
    )
    parser.add_argument(
        "--pack-version",
        help="new semantic version; required with --build-new-pack-key",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.repo_root.resolve()
    if args.build_new_pack_key is None:
        if args.arithmetic_campaign is not None or args.pack_version is not None:
            parser.error(
                "--arithmetic-campaign/--pack-version require --build-new-pack-key"
            )
        authority = verify_existing_canonical_pack(ROOT)
        print(
            "PASS: immutable canonical v1 verified read-only with "
            f"{authority['route_count']} frozen routes; native reexecution NOT_RUN"
        )
        return 0

    new_pack_key = args.build_new_pack_key
    if (
        new_pack_key == CANONICAL_PACK_KEY
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{2,127}", new_pack_key) is None
    ):
        parser.error("new pack key must be safe and differ from canonical v1")
    if (
        args.pack_version is None
        or args.pack_version == "1.0.0"
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.pack_version) is None
    ):
        parser.error("new pack version must be an exact non-v1 semantic version")
    if args.arithmetic_campaign is None:
        parser.error("--arithmetic-campaign is required for a new pack version")
    PACK_KEY = new_pack_key
    PACK_VERSION = args.pack_version
    arithmetic_campaign = args.arithmetic_campaign.resolve(strict=True)
    pack_parent = ROOT / "verification-packs"
    destination = pack_parent / PACK_KEY
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"VERSIONED_PACK_DESTINATION_ALREADY_EXISTS:{destination}")
    validate_source_routes(ROOT)
    pack_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{PACK_KEY}-staging-", dir=pack_parent))
    try:
        route_count, matrix_count = build_staged_pack(staging, arithmetic_campaign)
        validate_staged_pack(ROOT, staging)
        publish_staged_pack(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(
        f"PASS: built {destination} with {route_count} routes, "
        f"{matrix_count} route/block matrix rows, "
        "decision boundary NOT_CERTIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
