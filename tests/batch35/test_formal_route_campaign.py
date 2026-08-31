from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch35"
sys.path.insert(0, str(ROOT / "engines" / "polyglot-route-engine" / "src"))
EXACT_DARWIN_ARM64_REPLAY_ENABLED = (
    os.environ.get("ELMOS_BATCH35_PORTABLE_ONLY") != "true"
    and sys.platform == "darwin"
    and platform.machine() == "arm64"
)
LANGUAGES = ("csharp", "go", "java", "python", "rust", "typescript")
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
    "launcher": (
        "replay-tool",
        "certification/replay/validate_packed_route.py",
        f"{LEGACY_REPLAY_SOURCE_ROOT}/validate_packed_route.py",
    ),
    "validator": (
        "replay-tool",
        "certification/replay/scripts/batch29/validate_route.py",
        f"{LEGACY_REPLAY_SOURCE_ROOT}/scripts/batch29/validate_route.py",
    ),
    "schema": (
        "replay-schema",
        (
            "certification/replay/schemas/batch29/"
            "formal-equivalence-evidence.schema.json"
        ),
        (
            f"{LEGACY_REPLAY_SOURCE_ROOT}/schemas/batch29/"
            "formal-equivalence-evidence.schema.json"
        ),
    ),
}


def packed_replay_evidence_id(route_key: str, member: str) -> str:
    return f"route-replay-{member}-{route_key}"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def complete_scaffold(pack: Path) -> None:
    manifest = load(pack / "pack.json")
    manifest["owner"] = "formal-verification-team"
    manifest["maintenance_owner"] = "route-verification-team"
    manifest["scope"].update(
        {
            "source_artifact_digest": "sha256:" + "1" * 64,
            "target_artifact_digest": "sha256:" + "2" * 64,
            "environment_digest": "sha256:" + "3" * 64,
        }
    )
    write(pack / "pack.json", manifest)
    certification = load(pack / "certification" / "certification.json")
    certification["owner"] = "formal-verification-team"
    certification["exact_scope"] = manifest["scope"]
    write(pack / "certification" / "certification.json", certification)


def scaffold(repo: Path, *, key: str = "formal-route-test") -> Path:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "scaffold_verification_pack.py"),
            "--pack-key",
            key,
            "--migration-route",
            "all-directed-pairs-six-languages",
            "--workload-key",
            "typed-pure-function-v1",
            "--repo-root",
            str(repo),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    pack = repo / "verification-packs" / key
    complete_scaffold(pack)
    profile = load(pack / "validation-profile.json")
    profile["claims"][0]["required_techniques"] = [
        "formal-route-campaign",
        "differential-execution",
    ]
    write(pack / "validation-profile.json", profile)
    return pack


def add_evidence(
    pack: Path,
    campaign: dict[str, Any],
    evidence_id: str,
    relative: str,
    content: bytes,
    role: str,
) -> str:
    path = pack / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    campaign["evidence"].append(
        {
            "evidence_id": evidence_id,
            "path": relative,
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "role": role,
        }
    )
    return evidence_id


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def canonical_json_digest(value: object) -> str:
    content = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()
    return digest(content)


def load_pack_generator() -> Any:
    path = ROOT / "tooling" / "generate_polyglot_formal_verification_pack.py"
    spec = importlib.util.spec_from_file_location("formal_pack_generator_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_specialized_pack_generator() -> Any:
    path = (
        ROOT / "tooling" / "generate_specialized_polyglot_formal_verification_pack.py"
    )
    tooling = str(path.parent)
    inserted = tooling not in sys.path
    if inserted:
        sys.path.insert(0, tooling)
    try:
        spec = importlib.util.spec_from_file_location(
            "specialized_formal_pack_generator_test", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load specialized generator: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(tooling)


def load_formal_campaign_validator() -> Any:
    path = SCRIPTS / "validate_formal_route_campaign.py"
    spec = importlib.util.spec_from_file_location(
        "formal_route_campaign_validator_test", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load formal campaign validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_packed_route_launcher() -> Any:
    path = SCRIPTS / "validate_packed_route.py"
    spec = importlib.util.spec_from_file_location("packed_route_launcher_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load packed route launcher: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_route_formal_bundle(
    pack: Path,
    campaign: dict[str, Any],
    route: dict[str, Any],
) -> str:
    route_key = route["route_key"]
    profile = route["semantic_profile"]
    route_root = pack / "evidence" / "routes" / route_key
    route_manifest = {
        "route_key": route_key,
        "version": route["route_version"],
        "status": "limited",
        "profiles": {"semantic_profile": profile},
        "source": {"language": route["source_language"]},
        "target": {"language": route["target_language"]},
    }
    write(route_root / "route.json", route_manifest)
    write(route_root / "lowering" / "profile.json", {"profile": profile})

    def json_content(value: object) -> bytes:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()

    formal_function = {
        "name": "fixture_value",
        "parameters": [],
        "return": {"kind": "literal", "value": 1},
    }
    source_ir = {
        "analyzer": "fixture-source-analyzer",
        "analyzer_version": "1.0.0",
        "source_language": route["source_language"],
        "functions": [formal_function],
    }
    target_ir = {
        "analyzer": "fixture-target-relift-analyzer",
        "analyzer_version": "1.0.0",
        "source_language": route["target_language"],
        "functions": [formal_function],
    }
    source_ir_content = json_content(source_ir)
    target_ir_content = json_content(target_ir)
    source_artifact_content = b"fixture source analyzer input\n"
    target_artifact_content = b"generated target analyzer input\n"
    semantic_path = "/functions/0"
    semantic_hash = canonical_json_digest(formal_function)
    source_artifact_digest = digest(source_artifact_content)
    target_artifact_digest = digest(target_artifact_content)
    source_artifact_pointer = f"{source_artifact_digest}#{semantic_path}"
    target_artifact_pointer = f"{target_artifact_digest}#{semantic_path}"
    source_chunk_id = digest(
        f"{source_artifact_digest}\0{semantic_path}\0{semantic_hash}".encode()
    )
    target_chunk_id = digest(
        f"{target_artifact_digest}\0{semantic_path}\0{semantic_hash}".encode()
    )

    artifacts: dict[str, tuple[str, str, bytes]] = {
        "source-ir-fixture": (
            "source-ir",
            "certification/artifacts/source-ir.json",
            source_ir_content,
        ),
        "target-ir-fixture": (
            "target-ir",
            "certification/artifacts/target-ir.json",
            target_ir_content,
        ),
        "source-artifact-fixture": (
            "corpus-artifact",
            "certification/artifacts/source-input.txt",
            source_artifact_content,
        ),
        "target-artifact-fixture": (
            "target-artifact",
            "certification/artifacts/target.txt",
            target_artifact_content,
        ),
        "chunk-map-fixture": (
            "chunk-map",
            "certification/artifacts/chunk-map.json",
            (
                json.dumps(
                    {
                        "status": "PASSED",
                        "path_scheme": "rfc6901-json-pointer-v1",
                        "required_source_chunk_count": 1,
                        "mapped_source_chunk_count": 1,
                        "coverage": 1.0,
                        "mappings": [
                            {
                                "status": "EXACT",
                                "semantic_path": semantic_path,
                                "semantic_hash": semantic_hash,
                                "source_chunk_id": source_chunk_id,
                                "target_chunk_id": target_chunk_id,
                                "source_artifact_pointer": source_artifact_pointer,
                                "target_artifact_pointer": target_artifact_pointer,
                            }
                        ],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            ),
        ),
        "source-runtime-result-fixture": (
            "behavior-result",
            "certification/artifacts/source-behavior.json",
            (
                b'{"case_count":1,"oracle_conflict_count":0,"pass_count":1,'
                b'"source_runtime_passed":true,"target_runtime_passed":true}\n'
            ),
        ),
        "target-runtime-result-fixture": (
            "behavior-result",
            "certification/artifacts/target-behavior.json",
            (
                b'{"case_count":1,"oracle_conflict_count":0,"pass_count":1,'
                b'"source_runtime_passed":true,"target_runtime_passed":true}\n'
            ),
        ),
    }

    engine_sources = {
        "engine-source-engine-fixture": (
            "certification/artifacts/engine-sources/engines/"
            "polyglot-route-engine/src/elmos_polyglot_route/engine.py",
            b"# fixture engine\n",
            "engines/polyglot-route-engine/src/elmos_polyglot_route/engine.py",
        ),
        "engine-source-equivalence-fixture": (
            "certification/artifacts/engine-sources/engines/"
            "polyglot-route-engine/src/elmos_polyglot_route/equivalence.py",
            b"# fixture equivalence encoder\n",
            "engines/polyglot-route-engine/src/elmos_polyglot_route/equivalence.py",
        ),
        "engine-source-emitter-fixture": (
            "certification/artifacts/engine-sources/engines/"
            "polyglot-route-engine/src/elmos_polyglot_route/emitter.py",
            b"# fixture emitter\n",
            "engines/polyglot-route-engine/src/elmos_polyglot_route/emitter.py",
        ),
        "engine-source-lock-fixture": (
            "certification/artifacts/engine-sources/engines/"
            "polyglot-route-engine/uv.lock",
            b"fixture-lock\n",
            "engines/polyglot-route-engine/uv.lock",
        ),
    }
    engine_manifest_files = []
    for artifact_id, (relative, content, repository_path) in engine_sources.items():
        artifacts[artifact_id] = ("engine-source", relative, content)
        engine_manifest_files.append(
            {
                "repository_path": repository_path,
                "captured_path": relative,
                "sha256": digest(content),
                "bytes": len(content),
            }
        )
    engine_manifest = json_content(
        {
            "schema_version": 1,
            "kind": "polyglot-route-engine-source-bundle",
            "file_count": len(engine_manifest_files),
            "files": engine_manifest_files,
        }
    )
    artifacts["engine-source-manifest-fixture"] = (
        "engine-source-manifest",
        "certification/artifacts/engine-source-manifest.json",
        engine_manifest,
    )
    environment = json_content(
        {
            "schema_version": 1,
            "route_key": route_key,
            "authority": "local-test-fixture",
            "platform": "test-only",
            "python": sys.version,
            "source_toolchain": "fixture-pinned",
            "target_toolchain": "fixture-pinned",
            "solver": {"name": "fixture-solver", "version": "1.0.0"},
            "route_engine_lock": {
                "path": "engines/polyglot-route-engine/uv.lock",
                "sha256": digest(engine_sources["engine-source-lock-fixture"][1]),
            },
            "engine_source_manifest": {
                "path": "certification/artifacts/engine-source-manifest.json",
                "sha256": digest(engine_manifest),
                "bytes": len(engine_manifest),
            },
            "independent_verification": "NOT_RUN",
            "external_certification": "NOT_RUN",
        }
    )
    artifacts["environment-fixture"] = (
        "environment",
        "certification/artifacts/environment.json",
        environment,
    )

    proof_assumptions = [
        "fixture analyzers and runtime contracts are trusted test assumptions"
    ]
    implementation_identity = {}
    for identity, artifact_id, implementation_path in (
        (
            "engine",
            "engine-source-engine-fixture",
            "src/elmos_polyglot_route/engine.py",
        ),
        (
            "equivalence_encoder",
            "engine-source-equivalence-fixture",
            "src/elmos_polyglot_route/equivalence.py",
        ),
        (
            "emitter",
            "engine-source-emitter-fixture",
            "src/elmos_polyglot_route/emitter.py",
        ),
    ):
        source_content = engine_sources[artifact_id][1]
        implementation_identity[identity] = {
            "path": implementation_path,
            "sha256": digest(source_content),
            "byte_count": len(source_content),
        }
    formal_input = json_content(
        {
            "schema_version": "1.0.0",
            "kind": "elmos.formal-equivalence-input",
            "route": {
                "source_language": route["source_language"],
                "target_language": route["target_language"],
                "profile": profile,
            },
            "claim_scope": {
                "relation": "canonical-normalized-source-ir-to-target-relift-ir",
                "source_term": "source_normalized_ir.formal_function",
                "target_term": "target_relift_normalized_ir.formal_function",
                "original_source_bytes_theorem": False,
                "source_compiler_runtime_soundness": "NOT_RUN",
                "target_compiler_runtime_soundness": "NOT_RUN",
            },
            "source_artifact": {
                "role": "original-source-analyzer-input",
                "path": "source-input.txt",
                "sha256": source_artifact_digest,
                "byte_count": len(source_artifact_content),
                "content_base64": base64.b64encode(source_artifact_content).decode(),
                "content_reference": {
                    "path": "source-input.txt",
                    "sha256": source_artifact_digest,
                },
            },
            "target_artifact": {
                "role": "emitted-target-analyzer-input",
                "path": "target.txt",
                "sha256": target_artifact_digest,
                "byte_count": len(target_artifact_content),
                "content_base64": base64.b64encode(target_artifact_content).decode(),
                "content_reference": {
                    "path": "target.txt",
                    "sha256": target_artifact_digest,
                },
            },
            "source_normalized_ir": {
                "role": "canonical-source-normalized-ir",
                "artifact": {
                    "path": "source-ir.json",
                    "sha256": digest(source_ir_content),
                },
                "semantic_ir": source_ir,
                "semantic_ir_sha256": canonical_json_digest(source_ir),
                "formal_function": formal_function,
                "formal_function_sha256": semantic_hash,
            },
            "target_relift_normalized_ir": {
                "role": "emitted-target-relift-normalized-ir",
                "artifact": {
                    "path": "target-ir.json",
                    "sha256": digest(target_ir_content),
                },
                "semantic_ir": target_ir,
                "semantic_ir_sha256": canonical_json_digest(target_ir),
                "formal_function": formal_function,
                "formal_function_sha256": semantic_hash,
            },
            "implementation_identity": implementation_identity,
            "analyzer_identity": {
                "source": {
                    "name": source_ir["analyzer"],
                    "version": source_ir["analyzer_version"],
                    "language": route["source_language"],
                },
                "target_relift": {
                    "name": target_ir["analyzer"],
                    "version": target_ir["analyzer_version"],
                    "language": route["target_language"],
                    "mode": "emitted-target",
                },
            },
            "emitter_identity": {
                "target_language": route["target_language"],
                "normalization_rules": [],
                "helper_digests": [],
            },
            "solver": {
                "name": "fixture-solver",
                "version": "1.0.0",
                "timeout_ms": 20000,
                "random_seed": 0,
            },
            "environment": {"authority": "local-test-fixture"},
            "environment_assumptions": proof_assumptions,
            "unsupported_semantics": ["out-of-profile constructs are excluded"],
        }
    )
    artifacts["formal-input-fixture"] = (
        "formal-input",
        "certification/artifacts/formal-input.json",
        formal_input,
    )
    formal_input_digest = digest(formal_input)
    solver_input = (
        f"; formal_input_digest {formal_input_digest}\n(check-sat)\n".encode()
    )
    solver_input_digest = digest(solver_input)
    solver_result = json_content(
        {
            "status": "PROVED_UNDER_ASSUMPTIONS",
            "input_digest": formal_input_digest,
            "formal_input_digest": formal_input_digest,
            "formal_input": {
                "path": "formal-input.json",
                "sha256": formal_input_digest,
            },
            "solver_input_digest": solver_input_digest,
        }
    )
    artifacts["solver-input-fixture"] = (
        "solver-input",
        "certification/artifacts/proof.smt2",
        solver_input,
    )
    artifacts["solver-result-fixture"] = (
        "solver-result",
        "certification/artifacts/solver-result.json",
        solver_result,
    )
    composition = json_content(
        {
            "status": "PROVED_UNDER_ASSUMPTIONS",
            "formal_input_digest": formal_input_digest,
            "solver_input_digest": solver_input_digest,
        }
    )
    artifacts["formal-composition-fixture"] = (
        "formal-composition",
        "certification/artifacts/proof-composition.json",
        composition,
    )

    def proof_ref(artifact_id: str) -> dict[str, Any]:
        _role, relative, content = artifacts[artifact_id]
        return {
            "path": relative,
            "sha256": digest(content),
            "bytes": len(content),
        }

    proof_bundle = json_content(
        {
            "schema_version": 1,
            "route_key": route_key,
            "property_id": "fixture-denotational-equivalence",
            "same_input_required": True,
            "runs": [
                {
                    "corpus": "fixture",
                    "formal_input": proof_ref("formal-input-fixture"),
                    "smt2": proof_ref("solver-input-fixture"),
                    "result": proof_ref("solver-result-fixture"),
                    "composition": proof_ref("formal-composition-fixture"),
                }
            ],
        }
    )
    artifacts["proof-input-bundle-fixture"] = (
        "proof-input-bundle",
        "certification/artifacts/proof-input-bundle.json",
        proof_bundle,
    )
    for member, (role, relative, source_relative) in PACKED_REPLAY_FILES.items():
        artifacts[f"packed-replay-{member}-fixture"] = (
            role,
            relative,
            (ROOT / source_relative).read_bytes(),
        )

    artifact_refs = []
    for artifact_id, (role, relative, content) in artifacts.items():
        path = route_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        artifact_refs.append(
            {
                "artifact_id": artifact_id,
                "role": role,
                "path": relative,
                "sha256": digest(content),
                "bytes": len(content),
            }
        )

    solver_result_digest = digest(solver_result)
    formal = {
        "schema_version": 2,
        "route_key": route_key,
        "route_manifest_sha256": digest((route_root / "route.json").read_bytes()),
        "semantic_profile": profile,
        "semantic_profile_sha256": digest(
            (route_root / "lowering" / "profile.json").read_bytes()
        ),
        "artifact_id": "target-artifact-fixture",
        "artifact_sha256": digest(artifacts["target-artifact-fixture"][2]),
        "environment_artifact_id": "environment-fixture",
        "environment_sha256": digest(artifacts["environment-fixture"][2]),
        "artifact_refs": artifact_refs,
        "semantic_ir": {
            "status": "PASSED",
            "source_ir_artifact_id": "source-ir-fixture",
            "source_ir_sha256": digest(source_ir_content),
            "target_ir_artifact_id": "target-ir-fixture",
            "target_relift_ir_sha256": digest(target_ir_content),
            "unknown_or_dropped_nodes": 0,
            "differences": [],
        },
        "semantic_chunks": {
            "status": "PASSED",
            "total": 1,
            "matched": 1,
            "unmatched": 0,
            "ambiguous": 0,
            "coverage": 1.0,
            "evidence_artifact_ids": ["chunk-map-fixture"],
            "chunks": [
                {
                    "chunk_id": f"artifacts:{source_chunk_id}",
                    "source_ref": f"source-ir-fixture#{semantic_path}",
                    "target_ref": f"target-ir-fixture#{semantic_path}",
                    "semantic_hash": semantic_hash,
                    "status": "MATCHED",
                }
            ],
        },
        "behavior_equivalence": {
            "status": "PASSED",
            "total_cases": 2,
            "passed_cases": 2,
            "counterexamples": [],
            "evidence_artifact_ids": [
                "source-runtime-result-fixture",
                "target-runtime-result-fixture",
            ],
            "source_runtime_artifact_ids": ["source-runtime-result-fixture"],
            "target_runtime_artifact_ids": ["target-runtime-result-fixture"],
            "canonical_oracle_passed": True,
            "source_runtime_passed": True,
            "target_runtime_passed": True,
        },
        "formal_proof": {
            "status": "PROVED_UNDER_ASSUMPTIONS",
            "solver": "fixture-solver",
            "solver_version": "1.0.0",
            "solver_options": {
                "timeout_ms": 20000,
                "random_seed": 0,
                "proof": True,
            },
            "input_artifact_id": "proof-input-bundle-fixture",
            "input_digest": digest(proof_bundle),
            "result_artifact_ids": ["solver-result-fixture"],
            "assumptions": proof_assumptions,
            "obligations": [
                {
                    "obligation_id": "fixture-equivalence",
                    "status": "PROVED_UNDER_ASSUMPTIONS",
                    "scope": profile,
                    "formal_input_artifact_id": "formal-input-fixture",
                    "solver_input_artifact_id": "solver-input-fixture",
                    "input_digest": solver_input_digest,
                    "solver_result_artifact_id": "solver-result-fixture",
                    "assumptions": proof_assumptions,
                }
            ],
            "replay": {
                "command": list(PACKED_REPLAY_COMMAND),
                "cwd": ".",
                "expected_result_artifact_id": "solver-result-fixture",
                "expected_result_sha256": solver_result_digest,
                "expected_exit_code": 0,
            },
        },
    }
    wrapper_path = route_root / "certification" / "formal-equivalence.json"
    write(wrapper_path, formal)
    wrapper_content = wrapper_path.read_bytes()
    write(
        route_root / "certification" / "certification.json",
        {
            "schema_version": 1,
            "route_key": route_key,
            "route_version": route["route_version"],
            "status": "limited",
            "declared_scope": profile,
            "evidence_format": 2,
            "formal_equivalence": {
                "path": "certification/formal-equivalence.json",
                "sha256": digest(wrapper_content),
                "bytes": len(wrapper_content),
            },
        },
    )
    evidence_id = f"route-evidence-{route_key}"
    add_evidence(
        pack,
        campaign,
        evidence_id,
        f"evidence/routes/{route_key}/certification/formal-equivalence.json",
        wrapper_content,
        "route-formal-evidence",
    )
    for member, (role, relative, source_relative) in PACKED_REPLAY_FILES.items():
        add_evidence(
            pack,
            campaign,
            packed_replay_evidence_id(route_key, member),
            f"evidence/routes/{route_key}/{relative}",
            (ROOT / source_relative).read_bytes(),
            role,
        )
    return evidence_id


def refresh_route_wrapper_binding(pack: Path, route_key: str) -> None:
    route_root = pack / "evidence" / "routes" / route_key
    wrapper_path = route_root / "certification" / "formal-equivalence.json"
    wrapper_content = wrapper_path.read_bytes()
    certification_path = route_root / "certification" / "certification.json"
    certification = load(certification_path)
    certification["formal_equivalence"].update(
        {
            "sha256": digest(wrapper_content),
            "bytes": len(wrapper_content),
        }
    )
    write(certification_path, certification)
    campaign_path = pack / "formal-route-campaign.json"
    campaign = load(campaign_path)
    evidence = next(
        item
        for item in campaign["evidence"]
        if item["evidence_id"] == f"route-evidence-{route_key}"
    )
    evidence.update(
        {
            "sha256": digest(wrapper_content),
            "bytes": len(wrapper_content),
        }
    )
    write(campaign_path, campaign)


def build_campaign(pack: Path) -> dict[str, Any]:
    block = "integer-arithmetic"
    profile = "typed-pure-function-v1"
    routes = [
        {
            "route_key": f"{source}-to-{target}",
            "source_language": source,
            "target_language": target,
            "route_version": "1.0.0",
            "semantic_profile": profile,
            "composition_id": f"composition-{source}-to-{target}",
            "artifact_evidence_ids": [f"route-evidence-{source}-to-{target}"],
            "packed_replay_evidence_ids": [
                packed_replay_evidence_id(f"{source}-to-{target}", member)
                for member in PACKED_REPLAY_FILES
            ],
        }
        for source in LANGUAGES
        for target in LANGUAGES
        if source != target
    ]
    campaign: dict[str, Any] = {
        "schema_version": 1,
        "campaign_key": "six-language-formal-route-campaign",
        "version": "1.0.0",
        "semantic_profile": profile,
        "campaign_status": "LOCAL_EXECUTED",
        "certification_status": "NOT_CERTIFIED",
        "required_languages": list(LANGUAGES),
        "semantic_blocks": [block],
        "route_set": {"manifest_evidence_id": "route-set", "routes": routes},
        "obligations": [],
        "obligation_matrix": [],
        "compositions": [],
        "solver_runs": [],
        "replays": [],
        "evidence": [],
        "packed_route_replay": {
            "packed_validation": {
                "scope": "evidence-integrity-and-semantic-closure-only",
                "command": list(PACKED_REPLAY_COMMAND),
                "cwd": ".",
            },
            "external_native_reexecution": {
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
            },
        },
        "independent_verification": {
            "status": "NOT_RUN",
            "verifier": None,
            "evidence_ids": [],
        },
        "limitations": [
            "Local engineering proof and behavior evidence only; independent verification is NOT_RUN."
        ],
    }
    for route in routes:
        self_contained_evidence = add_route_formal_bundle(pack, campaign, route)
        if route["artifact_evidence_ids"] != [self_contained_evidence]:
            raise AssertionError("route formal evidence binding drift")
    route_manifest = (
        json.dumps(
            {"schema_version": 1, "semantic_profile": profile, "routes": routes},
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    add_evidence(
        pack,
        campaign,
        "route-set",
        "formal-evidence/route-set.json",
        route_manifest,
        "route-set",
    )
    solver_binary = add_evidence(
        pack,
        campaign,
        "solver-binary",
        "formal-evidence/z3.bin",
        b"z3 4.16.0 test fixture\n",
        "artifact",
    )
    solver_digest = next(
        item["sha256"]
        for item in campaign["evidence"]
        if item["evidence_id"] == solver_binary
    )

    def add_proved_obligation(kind: str, language: str) -> str:
        prefix = "lift" if kind == "source-lifting" else "lower"
        obligation_id = f"{prefix}-{language}-{block}"
        input_id = add_evidence(
            pack,
            campaign,
            f"input-{obligation_id}",
            f"formal-evidence/solver/{obligation_id}.smt2",
            f"; obligation {obligation_id}\n(check-sat)\n".encode(),
            "solver-input",
        )
        output_id = add_evidence(
            pack,
            campaign,
            f"output-{obligation_id}",
            f"formal-evidence/solver/{obligation_id}.out",
            b"unsat\n",
            "solver-output",
        )
        run_id = f"run-{obligation_id}"
        obligation: dict[str, Any] = {
            "obligation_id": obligation_id,
            "claim_id": "claim.behavior",
            "property_id": "property.sample",
            "kind": kind,
            "semantic_block": block,
            "required": True,
            "status": "proved",
            "proof_strength": "theorem",
            "method": "smt",
            "assumptions": [],
            "evidence_ids": [input_id, output_id],
            "solver_run_id": run_id,
        }
        if kind == "source-lifting":
            obligation["source_language"] = language
            obligation["assumptions"] = [
                {
                    "assumption_id": f"assumption-{language}-frontend",
                    "statement": f"The pinned {language} frontend semantics are the declared source semantics.",
                    "status": "accepted",
                    "evidence_ids": ["route-set"],
                }
            ]
        else:
            obligation["target_language"] = language
        campaign["obligations"].append(obligation)
        campaign["solver_runs"].append(
            {
                "run_id": run_id,
                "obligation_ids": [obligation_id],
                "solver": {
                    "name": "z3",
                    "version": "4.16.0",
                    "binary_digest": solver_digest,
                    "binary_evidence_id": solver_binary,
                    "options": {"random_seed": 0, "proof": True},
                    "timeout_ms": 20000,
                },
                "result": "unsat",
                "input_evidence_id": input_id,
                "output_evidence_id": output_id,
            }
        )
        return obligation_id

    source_ids = {
        language: add_proved_obligation("source-lifting", language)
        for language in LANGUAGES
    }
    target_ids = {
        language: add_proved_obligation("target-lowering", language)
        for language in LANGUAGES
    }
    behavior_evidence = add_evidence(
        pack,
        campaign,
        "behavior-evidence",
        "formal-evidence/behavior.json",
        b'{"status":"passed","scope":"local-fixture"}\n',
        "behavior-run",
    )
    replay_content = b"same-fingerprint\n"
    fingerprint = "sha256:" + hashlib.sha256(replay_content).hexdigest()
    replay_manifest = add_evidence(
        pack,
        campaign,
        "replay-manifest",
        "formal-evidence/replay.json",
        (
            json.dumps(
                {
                    "command": ["python", "replay.py"],
                    "seed": 1,
                    "expected_fingerprint": fingerprint,
                },
                sort_keys=True,
            ).encode()
            + b"\n"
        ),
        "replay-manifest",
    )
    replay_output = add_evidence(
        pack,
        campaign,
        "replay-output",
        "formal-evidence/replay.out",
        replay_content,
        "replay-output",
    )

    first_behavior_id: str | None = None
    for route in routes:
        route_key = route["route_key"]
        behavior_id = f"behavior-{route_key}-{block}"
        behavior: dict[str, Any] = {
            "obligation_id": behavior_id,
            "claim_id": "claim.behavior",
            "property_id": "property.sample",
            "kind": "route-behavior",
            "semantic_block": block,
            "route_key": route_key,
            "required": True,
            "status": "passed",
            "proof_strength": "testing",
            "method": "differential-execution",
            "assumptions": [],
            "evidence_ids": [behavior_evidence],
        }
        if first_behavior_id is None:
            first_behavior_id = behavior_id
            behavior["replay_id"] = "replay-first-behavior"
            campaign["replays"].append(
                {
                    "replay_id": "replay-first-behavior",
                    "obligation_id": behavior_id,
                    "status": "passed",
                    "manifest_evidence_id": replay_manifest,
                    "expected_fingerprint": fingerprint,
                    "observed_fingerprint": fingerprint,
                    "evidence_ids": [replay_output],
                }
            )
        campaign["obligations"].append(behavior)
        composition_id = route["composition_id"]
        campaign["obligation_matrix"].append(
            {
                "route_key": route_key,
                "semantic_block": block,
                "source_lifting_obligation_id": source_ids[route["source_language"]],
                "target_lowering_obligation_id": target_ids[route["target_language"]],
                "behavior_obligation_id": behavior_id,
                "composition_id": composition_id,
            }
        )
        campaign["compositions"].append(
            {
                "composition_id": composition_id,
                "route_key": route_key,
                "source_lifting_obligation_ids": [source_ids[route["source_language"]]],
                "target_lowering_obligation_ids": [
                    target_ids[route["target_language"]]
                ],
                "behavior_obligation_ids": [behavior_id],
                "status": "proved",
            }
        )

    write(pack / "formal-route-campaign.json", campaign)
    manifest = load(pack / "pack.json")
    manifest["formal_route_campaign"] = "formal-route-campaign.json"
    write(pack / "pack.json", manifest)
    return campaign


class FormalRouteCampaignTests(unittest.TestCase):
    def make_pack(self, directory: str) -> Path:
        pack = scaffold(Path(directory))
        build_campaign(pack)
        return pack

    @staticmethod
    def specialized_arithmetic_binding_campaign(generator: Any) -> dict[str, Any]:
        obligations: list[dict[str, Any]] = []
        for language in generator.LANGUAGES:
            for block in (
                *sorted(generator.ARITHMETIC_EVIDENCE_BLOCKS),
                "finite-number-arithmetic",
            ):
                obligations.append(
                    {
                        "obligation_id": f"lowering-{language}-{block}",
                        "kind": "target-lowering",
                        "semantic_block": block,
                        "evidence_ids": ["target-bundle"],
                    }
                )
            for kind, prefix in (
                ("source-lifting", "lifting"),
                ("route-behavior", "behavior"),
            ):
                obligations.append(
                    {
                        "obligation_id": (
                            f"{prefix}-{language}-integer-arithmetic-safe-domain"
                        ),
                        "kind": kind,
                        "semantic_block": "integer-arithmetic-safe-domain",
                        "evidence_ids": ["route-evidence"],
                    }
                )
        return {
            "evidence": [
                {"evidence_id": generator.ARITHMETIC_EVIDENCE_ID},
            ],
            "obligations": obligations,
        }

    def run_validator(
        self, pack: Path
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_formal_route_campaign.py"),
                str(pack),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = completed.stdout.strip()
        if not payload:
            signal = (
                f" signal={-completed.returncode}" if completed.returncode < 0 else ""
            )
            self.fail(
                "formal route campaign validator emitted no JSON: "
                f"returncode={completed.returncode}{signal}; "
                f"stderr={completed.stderr.strip()!r}"
            )
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as exc:
            self.fail(
                "formal route campaign validator emitted invalid JSON: "
                f"returncode={completed.returncode}; stdout={payload!r}; "
                f"stderr={completed.stderr.strip()!r}; error={exc}"
            )
        if not isinstance(result, dict):
            self.fail(
                "formal route campaign validator JSON must be an object: "
                f"returncode={completed.returncode}; stdout={payload!r}"
            )
        return completed, result

    def mutate(self, pack: Path, callback: Any) -> dict[str, Any]:
        path = pack / "formal-route-campaign.json"
        campaign = load(path)
        callback(campaign)
        write(path, campaign)
        return campaign

    def assert_invalid(self, pack: Path, expected: str) -> None:
        completed, result = self.run_validator(pack)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(
            any(expected in error for error in result["errors"]), result["errors"]
        )

    def test_valid_complete_campaign_is_formal_ready_but_not_certification_ready(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed, result = self.run_validator(self.make_pack(directory))
            self.assertEqual(completed.returncode, 0, result)
            self.assertTrue(result["formal_ready"])
            self.assertFalse(result["certification_ready"])
            self.assertEqual(result["route_count"], 30)
            self.assertEqual(result["required_obligation_count"], 42)

    def test_legacy_v1_never_loads_hostile_live_batch29_validator(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            with (
                mock.patch.object(
                    validator,
                    "load_batch29_formal_validator",
                    side_effect=AssertionError("hostile live formal validator loaded"),
                ),
                mock.patch.object(
                    validator,
                    "load_batch29_packed_module_validator",
                    side_effect=AssertionError("hostile live module validator loaded"),
                ),
            ):
                result = validator.validate(pack)
        self.assertEqual(result["status"], "valid", result)
        self.assertTrue(result["formal_ready"])

    def test_legacy_replay_assets_are_byte_identical_across_exact_30(self) -> None:
        expected = {
            "certification/replay/validate_packed_route.py": (
                "sha256:d7cf4017a6d0296c01f880e568950ef6b1dd341b61b48a09b90d61e0cff686da",
                6753,
            ),
            "certification/replay/scripts/batch29/validate_route.py": (
                "sha256:650470cc8078fe8158eea881885ccd5390ea68d2eb81b4809ed6b672c553c6f9",
                95431,
            ),
            (
                "certification/replay/schemas/batch29/"
                "formal-equivalence-evidence.schema.json"
            ): (
                "sha256:c4821219c01e037ca86bb749f7790a892b612e2c6d0cfd382eb40c503a0280c7",
                11670,
            ),
        }
        routes = (
            ROOT / "verification-packs/polyglot-30-route-formal-equivalence-v1/"
            "evidence/routes"
        )
        route_roots = sorted(path for path in routes.iterdir() if path.is_dir())
        self.assertEqual(len(route_roots), 30)
        for route_root in route_roots:
            for relative, (expected_digest, expected_bytes) in expected.items():
                path = route_root / relative
                self.assertEqual(digest(path.read_bytes()), expected_digest)
                self.assertEqual(path.stat().st_size, expected_bytes)

    def test_missing_route_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            self.mutate(pack, lambda campaign: campaign["route_set"]["routes"].pop())
            self.assert_invalid(pack, "schema route_set.routes")

    def test_missing_obligation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            self.mutate(pack, lambda campaign: campaign["obligations"].pop(0))
            self.assert_invalid(pack, "missing source lifting obligation")

    def test_digest_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            (pack / "formal-evidence" / "behavior.json").write_bytes(b"tampered\n")
            self.assert_invalid(pack, "sha256 mismatch")

    def test_unreferenced_evidence_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            orphan_path = pack / "formal-evidence" / "orphan.json"
            orphan_content = b'{"status":"NOT_RUN"}\n'
            orphan_path.write_bytes(orphan_content)
            campaign_path = pack / "formal-route-campaign.json"
            campaign = load(campaign_path)
            campaign["evidence"].append(
                {
                    "evidence_id": "orphan-evidence",
                    "path": orphan_path.relative_to(pack).as_posix(),
                    "sha256": digest(orphan_content),
                    "bytes": len(orphan_content),
                    "role": "other",
                }
            )
            write(campaign_path, campaign)
            self.assert_invalid(pack, "unreferenced evidence entry: orphan-evidence")

    def test_route_wrapper_internal_ref_missing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_root = pack / "evidence" / "routes" / "java-to-python"
            (route_root / "certification" / "artifacts" / "source-ir.json").unlink()
            self.assert_invalid(pack, "artifact is missing")

    def test_route_wrapper_internal_ref_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            target = (
                pack
                / "evidence"
                / "routes"
                / "java-to-python"
                / "certification"
                / "artifacts"
                / "target.txt"
            )
            target.write_bytes(b"tampered target\n")
            self.assert_invalid(pack, "artifact_refs")

    def test_route_packed_replay_launcher_missing_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            launcher = (
                pack
                / "evidence"
                / "routes"
                / "java-to-python"
                / "certification"
                / "replay"
                / "validate_packed_route.py"
            )
            launcher.unlink()
            self.assert_invalid(pack, "packed replay launcher")

    def test_route_packed_replay_tool_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            launcher = (
                pack
                / "evidence"
                / "routes"
                / "java-to-python"
                / "certification"
                / "replay"
                / "validate_packed_route.py"
            )
            launcher.write_bytes(launcher.read_bytes() + b"# tampered\n")
            self.assert_invalid(pack, "sha256 mismatch")

    def test_route_packed_replay_ref_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_key = "java-to-python"
            wrapper_path = (
                pack
                / "evidence"
                / "routes"
                / route_key
                / "certification"
                / "formal-equivalence.json"
            )
            wrapper = load(wrapper_path)
            replay_ref = next(
                item
                for item in wrapper["artifact_refs"]
                if item["path"] == "certification/replay/validate_packed_route.py"
            )
            replay_ref["path"] = "../../../../../outside.py"
            write(wrapper_path, wrapper)
            refresh_route_wrapper_binding(pack, route_key)
            self.assert_invalid(pack, "packed replay launcher is not wrapper-bound")

    def test_route_packed_replay_dangling_argv_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_key = "java-to-python"
            wrapper_path = (
                pack
                / "evidence"
                / "routes"
                / route_key
                / "certification"
                / "formal-equivalence.json"
            )
            wrapper = load(wrapper_path)
            wrapper["formal_proof"]["replay"]["command"][1] = (
                "certification/replay/missing.py"
            )
            write(wrapper_path, wrapper)
            refresh_route_wrapper_binding(pack, route_key)
            self.assert_invalid(pack, "packed replay argv is not canonical")

    def test_route_packed_replay_nonzero_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_key = "java-to-python"
            wrapper_path = (
                pack
                / "evidence"
                / "routes"
                / route_key
                / "certification"
                / "formal-equivalence.json"
            )
            wrapper = load(wrapper_path)
            wrapper["formal_proof"]["replay"]["expected_result_sha256"] = (
                "sha256:" + "f" * 64
            )
            write(wrapper_path, wrapper)
            refresh_route_wrapper_binding(pack, route_key)
            route_root = wrapper_path.parents[1]
            replay = subprocess.run(
                [
                    sys.executable,
                    "certification/replay/validate_packed_route.py",
                    "--route",
                    ".",
                ],
                cwd=route_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assert_invalid(pack, "packed replay exited nonzero")

    def test_route_packed_replay_cli_is_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_root = pack / "evidence" / "routes" / "java-to-python"
            completed = subprocess.run(
                PACKED_REPLAY_COMMAND,
                cwd=route_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            result = json.loads(completed.stdout)
            self.assertEqual(
                result["scope"], "evidence-integrity-and-semantic-closure-only"
            )
            self.assertEqual(result["native_route_reexecution"], "NOT_RUN")

    def test_external_native_reexecution_cannot_masquerade_as_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def masquerade(campaign: dict[str, Any]) -> None:
                campaign["packed_route_replay"]["external_native_reexecution"][
                    "status"
                ] = "PASSED"

            self.mutate(pack, masquerade)
            self.assert_invalid(pack, "external_native_reexecution.status")

    def test_route_wrapper_internal_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            route_key = "java-to-python"
            route_root = pack / "evidence" / "routes" / route_key
            wrapper_path = route_root / "certification" / "formal-equivalence.json"
            wrapper = load(wrapper_path)
            wrapper["artifact_refs"][0]["path"] = "../../../../../outside.json"
            write(wrapper_path, wrapper)
            wrapper_content = wrapper_path.read_bytes()
            certification_path = route_root / "certification" / "certification.json"
            certification = load(certification_path)
            certification["formal_equivalence"].update(
                {
                    "sha256": digest(wrapper_content),
                    "bytes": len(wrapper_content),
                }
            )
            write(certification_path, certification)
            campaign_path = pack / "formal-route-campaign.json"
            campaign = load(campaign_path)
            evidence = next(
                item
                for item in campaign["evidence"]
                if item["evidence_id"] == f"route-evidence-{route_key}"
            )
            evidence.update(
                {
                    "sha256": digest(wrapper_content),
                    "bytes": len(wrapper_content),
                }
            )
            write(campaign_path, campaign)
            self.assert_invalid(pack, "escapes the route directory")

    def test_wrong_route_formal_evidence_binding_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def bind_wrong_route(campaign: dict[str, Any]) -> None:
                routes = campaign["route_set"]["routes"]
                routes[0]["artifact_evidence_ids"] = routes[1][
                    "artifact_evidence_ids"
                ].copy()

            self.mutate(pack, bind_wrong_route)
            self.assert_invalid(pack, "does not preserve route-relative hierarchy")

    def test_evidence_path_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def escape(campaign: dict[str, Any]) -> None:
                campaign["evidence"][0]["path"] = "../outside.json"

            self.mutate(pack, escape)
            self.assert_invalid(pack, "escapes or is not relative")

    def test_unknown_cannot_masquerade_as_proved_composition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def unknown(campaign: dict[str, Any]) -> None:
                obligation = next(
                    item
                    for item in campaign["obligations"]
                    if item["kind"] == "source-lifting"
                )
                obligation["status"] = "unknown"
                run = next(
                    item
                    for item in campaign["solver_runs"]
                    if item["run_id"] == obligation["solver_run_id"]
                )
                run["result"] = "unknown"

            self.mutate(pack, unknown)
            self.assert_invalid(pack, "claims proved but derives unknown")

    def test_honest_unknown_is_valid_but_not_formal_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def unknown(campaign: dict[str, Any]) -> None:
                obligation = next(
                    item
                    for item in campaign["obligations"]
                    if item["kind"] == "source-lifting"
                )
                obligation["status"] = "unknown"
                run = next(
                    item
                    for item in campaign["solver_runs"]
                    if item["run_id"] == obligation["solver_run_id"]
                )
                run["result"] = "unknown"
                for composition in campaign["compositions"]:
                    if (
                        obligation["obligation_id"]
                        in composition["source_lifting_obligation_ids"]
                    ):
                        composition["status"] = "unknown"

            self.mutate(pack, unknown)
            completed, result = self.run_validator(pack)
            self.assertEqual(completed.returncode, 0, result)
            self.assertEqual(result["status"], "valid")
            self.assertFalse(result["formal_ready"])
            self.assertIn(
                next(
                    item["obligation_id"]
                    for item in load(pack / "formal-route-campaign.json")["obligations"]
                    if item["status"] == "unknown"
                ),
                result["unresolved_required_obligation_ids"],
            )

    def test_axiom_cannot_masquerade_as_proved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def axiom(campaign: dict[str, Any]) -> None:
                obligation = next(
                    item
                    for item in campaign["obligations"]
                    if item["kind"] == "target-lowering"
                )
                obligation["method"] = "language-standard-axiom"
                obligation["proof_strength"] = "axiom"
                obligation.pop("solver_run_id")

            self.mutate(pack, axiom)
            self.assert_invalid(pack, "cannot masquerade as proved")

    def test_replay_fingerprint_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def drift(campaign: dict[str, Any]) -> None:
                campaign["replays"][0]["observed_fingerprint"] = "sha256:" + "f" * 64

            self.mutate(pack, drift)
            self.assert_invalid(pack, "fingerprint drift")

    def test_not_run_independent_verification_cannot_masquerade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def masquerade(campaign: dict[str, Any]) -> None:
                campaign["independent_verification"]["verifier"] = "same-team-reviewer"
                campaign["certification_status"] = "CERTIFIED"

            self.mutate(pack, masquerade)
            self.assert_invalid(pack, "NOT_RUN cannot name a verifier")

    def test_same_team_cannot_masquerade_as_independent_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)

            def masquerade(campaign: dict[str, Any]) -> None:
                campaign["independent_verification"] = {
                    "status": "PASSED",
                    "verifier": "formal-verification-team",
                    "evidence_ids": ["route-set"],
                }

            self.mutate(pack, masquerade)
            self.assert_invalid(pack, "must differ from pack owner")

    def test_gate_invokes_strict_formal_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            self.mutate(pack, lambda campaign: campaign["obligations"].pop(0))
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification" / "gate-result.json")
            self.assertTrue(
                any(
                    "formal route campaign invalid" in failure
                    for failure in result["failures"]
                )
            )

    def test_gate_consumes_valid_local_campaign_without_certifying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = self.make_pack(directory)
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode, 0, completed.stdout + completed.stderr
            )
            result = load(pack / "certification" / "gate-result.json")
            self.assertEqual(result["certification_decision"], "NOT_CERTIFIED")
            self.assertTrue(result["formal_route_campaign"]["formal_ready"])
            self.assertFalse(result["formal_route_campaign"]["certification_ready"])

    def test_gate_resolves_p0_proof_through_property_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = scaffold(Path(directory), key="p0-property-link-test")
            manifest = load(pack / "pack.json")
            manifest["status"] = "certified"
            write(pack / "pack.json", manifest)
            certification = load(pack / "certification" / "certification.json")
            certification["status"] = "certified"
            write(pack / "certification" / "certification.json", certification)
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_verification_gate.py"), str(pack)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            result = load(pack / "certification" / "gate-result.json")
            self.assertIn("required P0 proof is not resolved", result["failures"])

    def test_generator_keeps_unexecuted_counterexample_open(self) -> None:
        generator = load_pack_generator()
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory) / "pack"
            generator.prepare_directories(pack)
            generator.base_pack_files(
                pack,
                source_digest="sha256:" + "1" * 64,
                target_digest="sha256:" + "2" * 64,
                environment_digest="sha256:" + "3" * 64,
                arithmetic_digest="sha256:" + "4" * 64,
                total_behavior_cases=1,
                arithmetic_counts={},
            )
            counterexample = load(pack / "counterexamples" / "sample.json")
            self.assertEqual(counterexample["status"], "open")
            self.assertEqual(counterexample["failure_fingerprint"], "NOT_OBSERVED")
            self.assertEqual(counterexample["replay"]["execution_status"], "NOT_RUN")
            self.assertIsNone(counterexample["replay"]["observed_fingerprint"])

    def test_specialized_generator_uses_explicit_eight_and_private_replay(self) -> None:
        generator = load_specialized_pack_generator()
        self.assertEqual(
            tuple(item[0] for item in generator.exact_routes()),
            generator.EXACT_ROUTE_KEYS,
        )
        self.assertEqual(len(generator.EXACT_ROUTE_KEYS), 8)
        self.assertEqual(
            set(generator.EXACT_ROUTE_KEYS),
            {
                "cpp-to-objc",
                "objc-to-cpp",
                "cpp-to-swift",
                "swift-to-cpp",
                "objc-to-swift",
                "swift-to-objc",
                "cpp-to-java",
                "java-to-cpp",
            },
        )
        self.assertEqual(generator.PACKED_REPLAY_COMMAND[:3], ["python", "-I", "-B"])
        self.assertEqual(generator.PACKED_REPLAY_COMMAND[-2:], ["--route", "."])
        self.assertNotEqual(
            generator.PACK_KEY,
            "polyglot-30-route-formal-equivalence-v1",
        )

    def test_specialized_generator_binds_arithmetic_evidence_exactly_once(self) -> None:
        generator = load_specialized_pack_generator()
        campaign = self.specialized_arithmetic_binding_campaign(generator)

        generator._bind_specialized_arithmetic_evidence(campaign)
        generator._bind_specialized_arithmetic_evidence(campaign)

        expected = {
            f"lowering-{language}-{block}"
            for language in generator.LANGUAGES
            for block in generator.ARITHMETIC_EVIDENCE_BLOCKS
        }
        bound = {
            obligation["obligation_id"]
            for obligation in campaign["obligations"]
            if generator.ARITHMETIC_EVIDENCE_ID in obligation["evidence_ids"]
        }
        self.assertEqual(bound, expected)
        self.assertEqual(len(bound), 8)
        for obligation in campaign["obligations"]:
            self.assertLessEqual(
                obligation["evidence_ids"].count(generator.ARITHMETIC_EVIDENCE_ID),
                1,
            )
            if obligation["semantic_block"] == "finite-number-arithmetic":
                self.assertNotIn(
                    generator.ARITHMETIC_EVIDENCE_ID,
                    obligation["evidence_ids"],
                )

    def test_specialized_generator_fails_on_incomplete_arithmetic_binding_set(
        self,
    ) -> None:
        generator = load_specialized_pack_generator()
        campaign = self.specialized_arithmetic_binding_campaign(generator)
        campaign["obligations"] = [
            obligation
            for obligation in campaign["obligations"]
            if obligation["obligation_id"]
            != "lowering-java-out-of-domain-arithmetic-errors"
        ]
        with self.assertRaisesRegex(
            RuntimeError, "^ARITHMETIC_EVIDENCE_BINDING_INVALID$"
        ):
            generator._bind_specialized_arithmetic_evidence(campaign)

    def test_specialized_packed_replay_rejects_path_shadow_uv(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            trusted = Path(directory) / "trusted" / "uv"
            trusted.parent.mkdir()
            trusted.write_bytes(b"trusted uv fixture\n")
            trusted.chmod(0o555)
            shadow = Path(directory) / "shadow" / "uv"
            shadow.parent.mkdir()
            shadow.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'forged packed replay'\n",
                encoding="utf-8",
            )
            shadow.chmod(0o755)
            errors: list[str] = []
            with (
                mock.patch.object(validator, "PINNED_UV_PATH", trusted),
                mock.patch.dict(
                    os.environ,
                    {"PATH": str(shadow.parent) + os.pathsep + os.defpath},
                    clear=False,
                ),
            ):
                observed = validator.pinned_uv_runtime("shadow test", errors)
            self.assertIsNone(observed)
            self.assertTrue(
                any("pinned uv origin mismatch" in error for error in errors),
                errors,
            )
            self.assertTrue(any(str(shadow) in error for error in errors), errors)

    def test_specialized_packed_replay_uses_private_sanitized_environment(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            private_root = Path(directory).resolve()
            private_venv = private_root / validator.PACKED_REPLAY_VENV_NAME
            hostile_environment = {
                "UV": "hostile",
                "UV_PROJECT_ENVIRONMENT": str(Path(directory) / "hostile-venv"),
                "UV_PYTHON": str(Path(directory) / "hostile-python"),
                "UV_NO_SYNC": "1",
                "UV_ENV_FILE": str(Path(directory) / "hostile.env"),
                "DYLD_INSERT_LIBRARIES": str(Path(directory) / "hostile.dylib"),
                "PYTHONPATH": str(Path(directory) / "shadow-package"),
                "VIRTUAL_ENV": str(Path(directory) / "hostile-venv"),
                "HTTPS_PROXY": "http://hostile.invalid",
                "NO_PROXY": "*",
            }
            with mock.patch.dict(os.environ, hostile_environment, clear=False):
                environment = validator.packed_replay_environment(
                    private_root, private_venv
                )
            project_environment = Path(environment["UV_PROJECT_ENVIRONMENT"])
            self.assertEqual(project_environment, private_venv)
            self.assertFalse(project_environment.exists())
            self.assertEqual(environment["UV_NO_CONFIG"], "1")
            self.assertEqual(
                {key for key in environment if key == "UV" or key.startswith("UV_")},
                {"UV_CACHE_DIR", "UV_NO_CONFIG", "UV_PROJECT_ENVIRONMENT"},
            )
            for variable in (
                "DYLD_INSERT_LIBRARIES",
                "HTTPS_PROXY",
                "NO_PROXY",
                "PYTHONPATH",
                "VIRTUAL_ENV",
            ):
                self.assertNotIn(variable, environment)
            for variable in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "UV_CACHE_DIR"):
                Path(environment[variable]).resolve(strict=False).relative_to(
                    private_root
                )

    def test_specialized_runtime_closure_is_exact_seven_from_live_lock(self) -> None:
        generator = load_specialized_pack_generator()
        validator = load_formal_campaign_validator()
        lock = ROOT / "engines" / "polyglot-route-engine" / "uv.lock"
        generated = generator.production_wheels_from_lock(lock)
        independently_validated = validator.production_wheels_from_lock(lock)
        self.assertEqual(generated, independently_validated)
        self.assertEqual(
            {item["name"] for item in generated},
            generator.PRODUCTION_PACKAGE_NAMES,
        )
        self.assertEqual(len(generated), 7)

    def test_specialized_runtime_archive_rejects_hardlink_and_symlink_escape(
        self,
    ) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            for name, member in (
                (
                    "hardlink.tar.gz",
                    tarfile.TarInfo("python/bin/forged"),
                ),
                (
                    "symlink.tar.gz",
                    tarfile.TarInfo("python/bin/forged"),
                ),
            ):
                archive = Path(directory) / name
                with tarfile.open(archive, "w:gz") as bundle:
                    if name.startswith("hardlink"):
                        member.type = tarfile.LNKTYPE
                        member.linkname = "python/bin/python3.12"
                    else:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "../../outside"
                    bundle.addfile(member)
                with self.assertRaises(ValueError):
                    validator.python_archive_inventory(archive)

    def test_specialized_runtime_archive_rejects_path_escape(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "escape.tar.gz"
            content = b"forged"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("python/../outside")
                member.size = len(content)
                bundle.addfile(member, io.BytesIO(content))
            with self.assertRaises(ValueError):
                validator.python_archive_inventory(archive)

    def test_specialized_runtime_diagnostic_is_bounded_and_sanitized(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            diagnostic = validator.bounded_replay_diagnostic(
                (str(private) + " secret\n") * 1_000,
                "",
                sensitive_roots=(private,),
            )
            self.assertNotIn(str(private), diagnostic)
            self.assertLessEqual(
                len(diagnostic.encode()), validator.MAX_REPLAY_DIAGNOSTIC_BYTES
            )

    def test_specialized_runtime_manifest_rejects_extra_missing_and_tamper(
        self,
    ) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            runtime_root = pack / "runtime"
            wheelhouse_root = runtime_root / "wheelhouse"
            wheelhouse_root.mkdir(parents=True)
            archive = runtime_root / validator.PYTHON_ARCHIVE_NAME
            archive_content = b"python"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("python/bin/python3.12")
                member.mode = 0o755
                member.size = len(archive_content)
                bundle.addfile(member, io.BytesIO(archive_content))
            inventory = validator.python_archive_inventory(archive)
            lock = runtime_root / "uv.lock"
            lock.write_bytes(b"version = 1\n")
            packages: list[dict[str, Any]] = []
            for index in range(7):
                content = f"wheel-{index}".encode()
                filename = f"package_{index}-1.0-py3-none-any.whl"
                path = wheelhouse_root / filename
                path.write_bytes(content)
                packages.append(
                    {
                        "name": f"package-{index}",
                        "version": "1.0",
                        "dependencies": [],
                        "filename": filename,
                        "path": f"runtime/wheelhouse/{filename}",
                        "url": f"https://example.invalid/{filename}",
                        "sha256": digest(content),
                        "bytes": len(content),
                    }
                )
            archive_digest = digest(archive.read_bytes())
            lock_digest = digest(lock.read_bytes())
            manifest = {
                "schema_version": 1,
                "runtime_key": "macos-aarch64-cpython-3.12.12-z3-4.16.0",
                "scope": "offline-evidence-integrity-and-semantic-closure-only",
                "replay_command": list(validator.PACKED_REPLAY_COMMAND_V2),
                "python_archive": {
                    "path": validator.PYTHON_ARCHIVE_PATH,
                    "url": validator.PYTHON_ARCHIVE_URL,
                    "sha256": archive_digest,
                    "bytes": archive.stat().st_size,
                    "implementation": "cpython",
                    "version": "3.12.12",
                    "build": "20260211",
                    "platform": "macos-aarch64-none",
                    "tree": inventory,
                },
                "production_lock": {
                    "path": validator.PACKED_RUNTIME_LOCK,
                    "sha256": lock_digest,
                    "bytes": lock.stat().st_size,
                    "resolution": "independent-transitive-production-closure",
                },
                "wheelhouse": {
                    "package_count": 7,
                    "install_policy": {
                        "offline": True,
                        "no_index": True,
                        "require_hashes": True,
                        "no_dependencies": True,
                        "link_mode": "copy",
                    },
                    "packages": packages,
                },
                "uv": {
                    "path": str(validator.PINNED_UV_PATH),
                    "sha256": validator.PINNED_UV_SHA256,
                    "bytes": validator.PINNED_UV_BYTES,
                    "version": validator.PINNED_UV_VERSION,
                },
                "sandbox": {
                    "path": str(validator.PINNED_SANDBOX_PATH),
                    "sha256": validator.PINNED_SANDBOX_SHA256,
                    "bytes": validator.PINNED_SANDBOX_BYTES,
                    "mode": "100755",
                    "uid": 0,
                    "gid": 0,
                    "profile": validator.PINNED_SANDBOX_PROFILE,
                    "profile_sha256": validator.PINNED_SANDBOX_PROFILE_SHA256,
                    "socket_denial_probe": "SOCKET_DENIED:1",
                },
                "environment": {
                    "policy": "explicit-private-allowlist",
                    "private_home": True,
                    "private_tmp": True,
                    "private_cache": True,
                    "proxy_variables": [],
                },
                "native_route_reexecution": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "external_certification": "NOT_CERTIFIED",
            }
            manifest_path = runtime_root / "packed-replay-runtime.json"
            write(manifest_path, manifest)
            patches = {
                "PYTHON_ARCHIVE_SHA256": archive_digest,
                "PYTHON_ARCHIVE_BYTES": archive.stat().st_size,
                "PYTHON_TREE_SHA256": inventory["inventory_sha256"],
                "PYTHON_TREE_FILE_COUNT": inventory["regular_file_count"],
                "PYTHON_TREE_BYTES": inventory["regular_file_bytes"],
                "PYTHON_TREE_SYMLINKS": inventory["symlinks"],
                "PRODUCTION_LOCK_SHA256": lock_digest,
                "PRODUCTION_LOCK_BYTES": lock.stat().st_size,
            }
            with (
                mock.patch.multiple(validator, **patches),
                mock.patch.object(
                    validator,
                    "production_wheels_from_lock",
                    return_value=packages,
                ),
            ):
                errors: list[str] = []
                self.assertIsNotNone(
                    validator.validate_packed_runtime_manifest(
                        pack.resolve(), manifest_path.resolve(), errors
                    )
                )
                self.assertEqual(errors, [])

                extra = runtime_root / "extra.bin"
                extra.write_bytes(b"extra")
                errors = []
                validator.validate_packed_runtime_manifest(
                    pack.resolve(), manifest_path.resolve(), errors
                )
                self.assertTrue(any("missing or extra" in item for item in errors))
                extra.unlink()

                first_wheel = pack / packages[0]["path"]
                original = first_wheel.read_bytes()
                first_wheel.write_bytes(b"tampered")
                errors = []
                validator.validate_packed_runtime_manifest(
                    pack.resolve(), manifest_path.resolve(), errors
                )
                self.assertTrue(any("bytes differ" in item for item in errors))
                first_wheel.write_bytes(original)

                first_wheel.unlink()
                errors = []
                validator.validate_packed_runtime_manifest(
                    pack.resolve(), manifest_path.resolve(), errors
                )
                self.assertTrue(any("does not exist" in item for item in errors))

    def test_specialized_private_runtime_seal_rejects_hardlinks(self) -> None:
        validator = load_formal_campaign_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "runtime"
            root.mkdir()
            original = root / "original"
            original.write_bytes(b"content")
            os.link(original, root / "linked")
            with self.assertRaisesRegex(ValueError, "hardlinked"):
                validator._runtime_tree_seal((root,))

    def test_specialized_schema_v2_runtime_and_legacy_v1_are_disjoint(self) -> None:
        schema = load(
            ROOT / "schemas" / "batch35" / "formal-route-campaign.schema.json"
        )
        legacy = schema["allOf"][0]["then"]
        specialized = schema["allOf"][1]["then"]
        self.assertEqual(
            legacy["not"]["required"], ["packed_replay_runtime_evidence_id"]
        )
        self.assertIn("packed_replay_runtime_evidence_id", specialized["required"])
        specialized_command = specialized["properties"]["packed_route_replay"][
            "properties"
        ]["packed_validation"]["properties"]["command"]["const"]
        legacy_command = legacy["properties"]["packed_route_replay"]["properties"][
            "packed_validation"
        ]["properties"]["command"]["const"]
        self.assertEqual(specialized_command[:3], ["python", "-I", "-B"])
        self.assertEqual(legacy_command, PACKED_REPLAY_COMMAND)

    def test_packed_launcher_validates_engine_manifest_before_unique_insertion(
        self,
    ) -> None:
        launcher = load_packed_route_launcher()
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as source_directory,
        ):
            route = Path(directory).resolve()
            relative = (
                launcher.ENGINE_SOURCE_ROOT_RELATIVE
                + "/elmos_polyglot_route/__init__.py"
            )
            source = route / relative
            source.parent.mkdir(parents=True)
            source.write_bytes(b"VALUE = 1\n")
            entries = [
                {
                    "repository_path": relative.removeprefix(
                        launcher.ENGINE_SOURCE_PREFIX
                    ),
                    "captured_path": relative,
                    "sha256": launcher.sha256_file(source),
                    "bytes": source.stat().st_size,
                }
            ]
            source_route = ROOT / "routes" / "cpp-to-java"
            source_manifest = load(
                source_route
                / "certification/formal-artifacts/engine-source-manifest.json"
            )
            source_receipts = source_manifest["runtime_source_receipts"]
            python_receipt = source_receipts["python_source_archive"]
            typescript_receipt = source_receipts["typescript_compiler_closure"]
            self.assertEqual(
                python_receipt["capture_relative_path"],
                launcher.PYTHON_ARCHIVE_RELATIVE,
            )
            self.assertEqual(
                typescript_receipt["capture_relative_path"],
                launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
            )
            source_capture_root = (
                source_route / "certification/formal-artifacts/engine-sources"
            )
            python_source = source_capture_root / launcher.PYTHON_ARCHIVE_RELATIVE
            self.assertTrue(python_source.is_file())
            self.assertFalse(python_source.is_symlink())
            self.assertEqual(python_source.stat().st_size, python_receipt["bytes"])
            self.assertEqual(
                launcher.sha256_file(python_source),
                "sha256:" + python_receipt["sha256"],
            )
            typescript_source_root = (
                source_capture_root / launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE
            )
            typescript_sources: dict[str, tuple[Path, str]] = {}
            for record in typescript_receipt["files"]:
                record_path = str(record["path"])
                source_path = typescript_source_root / record_path
                if record_path == "bin/tsc":
                    source_path = Path(source_directory) / record_path
                    source_path.parent.mkdir(parents=True)
                    source_path.write_bytes(
                        b"#!/usr/bin/env node\nrequire('../lib/tsc.js')\n"
                    )
                    source_path.chmod(0o555)
                self.assertTrue(source_path.is_file())
                self.assertFalse(source_path.is_symlink())
                self.assertEqual(source_path.stat().st_size, record["bytes"])
                self.assertEqual(
                    launcher.sha256_file(source_path), "sha256:" + record["sha256"]
                )
                typescript_sources[
                    f"{launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{record_path}"
                ] = (source_path, str(record["mode"]))
            self.assertEqual(
                len(typescript_sources), launcher.TYPESCRIPT_FILE_COUNT
            )
            runtime_sources = {
                launcher.PYTHON_ARCHIVE_RELATIVE: (
                    python_source,
                    str(python_receipt["mode"]),
                ),
                **typescript_sources,
            }
            for repository_path, (runtime_source, mode) in runtime_sources.items():
                captured_relative = launcher.ENGINE_SOURCE_PREFIX + repository_path
                captured = route / captured_relative
                captured.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(runtime_source, captured)
                captured.chmod(int(mode, 8))
                entries.append(
                    {
                        "repository_path": repository_path,
                        "captured_path": captured_relative,
                        "sha256": launcher.sha256_file(captured),
                        "bytes": captured.stat().st_size,
                    }
                )
            manifest = {
                "schema_version": 1,
                "kind": "polyglot-route-engine-source-bundle",
                "file_count": len(entries),
                "files": entries,
                "runtime_source_receipts": {
                    "python_source_archive": {
                        key: python_receipt[key]
                        for key in (
                            "schema_version",
                            "capture_relative_path",
                            "sha256",
                            "bytes",
                            "mode",
                            "uid",
                            "gid",
                            "nlink",
                            "source_tree_sha256",
                            "source_tree_record_count",
                            "source_tree_file_count",
                            "source_tree_bytes",
                        )
                    },
                    "typescript_compiler_closure": {
                        "schema_version": 1,
                        "capture_relative_path": (
                            launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE
                        ),
                        "source_manifest_sha256": (
                            launcher.TYPESCRIPT_SOURCE_MANIFEST_SHA256
                        ),
                        "runtime_manifest_sha256": (
                            launcher.TYPESCRIPT_RUNTIME_MANIFEST_SHA256
                        ),
                        "compiler_closure_sha256": (
                            launcher.TYPESCRIPT_CLOSURE_SHA256
                        ),
                        "file_count": launcher.TYPESCRIPT_FILE_COUNT,
                        "bytes": launcher.TYPESCRIPT_CLOSURE_BYTES,
                        "files": [
                            {
                                key: record[key]
                                for key in ("path", "sha256", "bytes", "mode")
                            }
                            for record in typescript_receipt["files"]
                        ],
                        "semantic_soundness": "NOT_RUN",
                    },
                },
            }
            manifest_path = route / launcher.ENGINE_MANIFEST_RELATIVE
            write(manifest_path, manifest)
            references = {
                relative: {
                    "role": "engine-source",
                    "sha256": entries[0]["sha256"],
                    "bytes": entries[0]["bytes"],
                },
                launcher.ENGINE_MANIFEST_RELATIVE: {
                    "role": "engine-source-manifest",
                    "sha256": launcher.sha256_file(manifest_path),
                    "bytes": manifest_path.stat().st_size,
                },
            }
            references.update(
                {
                    launcher.ENGINE_SOURCE_PREFIX + repository_path: {
                        "role": "engine-source",
                        "sha256": entry["sha256"],
                        "bytes": entry["bytes"],
                    }
                    for repository_path, entry in zip(
                        runtime_sources, entries[1:], strict=True
                    )
                }
            )
            isolated_path = [
                existing
                for existing in sys.path
                if not (Path(existing or ".") / "elmos_polyglot_route").exists()
            ]
            preloaded_engine_modules = {
                name: module
                for name, module in tuple(sys.modules.items())
                if name == "elmos_polyglot_route"
                or name.startswith("elmos_polyglot_route.")
            }
            for name in preloaded_engine_modules:
                sys.modules.pop(name, None)
            try:
                with mock.patch.object(sys, "path", isolated_path):
                    inserted = launcher.validate_and_insert_engine_source(
                        route, references
                    )
                    try:
                        self.assertEqual(sys.path[0], str(inserted))
                        self.assertEqual(sys.path.count(str(inserted)), 1)
                    finally:
                        sys.path.remove(str(inserted))

                    source.write_bytes(b"tampered\n")
                    before = list(sys.path)
                    with self.assertRaisesRegex(ValueError, "digest mismatch"):
                        launcher.validate_and_insert_engine_source(route, references)
                    self.assertEqual(sys.path, before)
            finally:
                sys.modules.update(preloaded_engine_modules)

    def test_generator_installs_route_local_content_addressed_replay(self) -> None:
        generator = load_pack_generator()
        with tempfile.TemporaryDirectory() as directory:
            route = Path(directory) / "java-to-python"
            dummy_path = route / "certification" / "artifacts" / "dummy.json"
            dummy_path.parent.mkdir(parents=True)
            dummy_path.write_text("{}\n", encoding="utf-8")
            write(
                route / "certification" / "formal-equivalence.json",
                {
                    "artifact_refs": [
                        {
                            "artifact_id": "artifact-dummy-fixture",
                            "role": "solver-result",
                            "path": "certification/artifacts/dummy.json",
                            "sha256": digest(dummy_path.read_bytes()),
                            "bytes": dummy_path.stat().st_size,
                        }
                    ],
                    "formal_proof": {
                        "replay": {
                            "command": ["../../dangling-python", "missing.py"],
                            "cwd": ".",
                            "expected_result_artifact_id": ("artifact-dummy-fixture"),
                            "expected_result_sha256": digest(dummy_path.read_bytes()),
                            "expected_exit_code": 0,
                        }
                    },
                },
            )
            formal_path = route / "certification" / "formal-equivalence.json"
            write(
                route / "certification" / "certification.json",
                {
                    "formal_equivalence": {
                        "path": "certification/formal-equivalence.json",
                        "sha256": digest(formal_path.read_bytes()),
                        "bytes": formal_path.stat().st_size,
                    }
                },
            )
            formal, members = generator.install_packed_route_replay(
                route,
                repo_root=ROOT,
            )
            self.assertEqual(
                formal["formal_proof"]["replay"]["command"],
                PACKED_REPLAY_COMMAND,
            )
            self.assertEqual(len(members), 3)
            refs = {item["path"]: item for item in formal["artifact_refs"]}
            for _member, (role, relative, _source) in PACKED_REPLAY_FILES.items():
                self.assertEqual(refs[relative]["role"], role)
                self.assertEqual(
                    refs[relative]["sha256"], digest((route / relative).read_bytes())
                )
            certification = load(route / "certification" / "certification.json")
            self.assertEqual(
                certification["formal_equivalence"]["sha256"],
                digest(formal_path.read_bytes()),
            )

    def test_generator_publish_replaces_stale_tree(self) -> None:
        generator = load_pack_generator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "pack"
            staging = root / "staging"
            destination.mkdir()
            staging.mkdir()
            (destination / "stale.txt").write_text("stale", encoding="utf-8")
            (staging / "fresh.txt").write_text("fresh", encoding="utf-8")
            generator.publish_staged_pack(staging, destination)
            self.assertFalse((destination / "stale.txt").exists())
            self.assertEqual(
                (destination / "fresh.txt").read_text(encoding="utf-8"), "fresh"
            )
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()
