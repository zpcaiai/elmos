#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

ENGINE_RUNTIME_MODULES = {
    "elmos_polyglot_route.equivalence": "elmos_polyglot_route/equivalence.py",
    "elmos_polyglot_route.models": "elmos_polyglot_route/models.py",
    "elmos_polyglot_route.engine": "elmos_polyglot_route/engine.py",
    "elmos_polyglot_route.emitter": "elmos_polyglot_route/emitter.py",
    "elmos_polyglot_route.types": "elmos_polyglot_route/types.py",
    "elmos_polyglot_route.canonical": "elmos_polyglot_route/canonical.py",
}
PINNED_Z3_VERSION = "4.16.0"

REQUIRED_ROUTE = [
    "schema_version",
    "route_key",
    "version",
    "status",
    "owner",
    "source",
    "target",
    "paths",
    "gates",
]
REQUIRED_DIRS = [
    "lowering",
    "mappings",
    "compat-runtime",
    "corpus/development",
    "corpus/holdout",
    "corpus/real-repository",
    "certification",
]
ALLOWED_ROUTE_STATUS = {
    "research",
    "experimental",
    "limited",
    "certified",
    "deprecated",
    "blocked",
}
ALLOWED_CAP_STATUS = {
    "certified",
    "supported",
    "conditional",
    "experimental",
    "detected-only",
    "blocked",
}
LAYER_STATUSES = {"PASSED", "FAILED", "UNKNOWN", "NOT_RUN"}
PROOF_STATUSES = {
    "PROVED",
    "PROVED_UNDER_ASSUMPTIONS",
    "AXIOM",
    "BOUNDED",
    "UNKNOWN",
    "TIMEOUT",
    "NOT_RUN",
    "COUNTEREXAMPLE",
}
CHUNK_STATUSES = {"MATCHED", "UNMATCHED", "AMBIGUOUS", "FAILED"}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

FORMAL_REQUIRED_KEYS = {
    "schema_version",
    "route_key",
    "route_manifest_sha256",
    "semantic_profile",
    "semantic_profile_sha256",
    "artifact_sha256",
    "artifact_id",
    "environment_sha256",
    "environment_artifact_id",
    "artifact_refs",
    "semantic_ir",
    "semantic_chunks",
    "behavior_equivalence",
    "formal_proof",
}
SEMANTIC_IR_KEYS = {
    "status",
    "source_ir_artifact_id",
    "source_ir_sha256",
    "target_ir_artifact_id",
    "target_relift_ir_sha256",
    "unknown_or_dropped_nodes",
    "differences",
}
SEMANTIC_CHUNK_KEYS = {
    "status",
    "total",
    "matched",
    "unmatched",
    "ambiguous",
    "coverage",
    "evidence_artifact_ids",
    "chunks",
}
CHUNK_KEYS = {"chunk_id", "source_ref", "target_ref", "semantic_hash", "status"}
BEHAVIOR_KEYS = {
    "status",
    "total_cases",
    "passed_cases",
    "counterexamples",
    "evidence_artifact_ids",
    "source_runtime_artifact_ids",
    "target_runtime_artifact_ids",
    "canonical_oracle_passed",
    "source_runtime_passed",
    "target_runtime_passed",
}
COUNTEREXAMPLE_REQUIRED_KEYS = {"case_id", "reason"}
COUNTEREXAMPLE_ALLOWED_KEYS = COUNTEREXAMPLE_REQUIRED_KEYS | {"evidence_ref"}
FORMAL_PROOF_KEYS = {
    "status",
    "solver",
    "solver_version",
    "solver_options",
    "input_artifact_id",
    "input_digest",
    "result_artifact_ids",
    "assumptions",
    "obligations",
    "replay",
}
OBLIGATION_REQUIRED_KEYS = {
    "obligation_id",
    "status",
    "scope",
    "formal_input_artifact_id",
    "solver_input_artifact_id",
    "input_digest",
    "solver_result_artifact_id",
    "assumptions",
}
OBLIGATION_ALLOWED_KEYS = OBLIGATION_REQUIRED_KEYS | {"detail"}
REPLAY_KEYS = {
    "command",
    "cwd",
    "expected_result_artifact_id",
    "expected_result_sha256",
    "expected_exit_code",
}
ARTIFACT_REF_KEYS = {"artifact_id", "role", "path", "sha256", "bytes"}
ARTIFACT_ROLES = {
    "source-ir",
    "target-ir",
    "target-artifact",
    "environment",
    "chunk-map",
    "behavior-result",
    "formal-input",
    "solver-input",
    "solver-result",
    "proof-input-bundle",
    "formal-composition",
    "engine-source",
    "engine-source-manifest",
    "corpus-artifact",
    "replay-tool",
    "replay-schema",
}
ARTIFACT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{7,95}$")
FORMAL_INPUT_REQUIRED_KEYS = {
    "schema_version",
    "kind",
    "route",
    "claim_scope",
    "source_artifact",
    "target_artifact",
    "source_normalized_ir",
    "target_relift_normalized_ir",
    "implementation_identity",
    "analyzer_identity",
    "emitter_identity",
    "solver",
    "environment",
    "environment_assumptions",
    "unsupported_semantics",
}
MODULE_FUNCTION_LAYER_KEYS = {"semantic", "chunk", "behavior", "formal"}
MODULE_PASSING_PROOF_STATUSES = {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
MODULE_ARTIFACT_ROLES = {
    "source-module-semantic-ir",
    "target-module-semantic-ir",
    "source-module-observations",
    "target-module-observations",
    "emitted-target-module-artifact",
    "module-formal-input",
    "formal-function-input",
    "formal-function-smt2",
    "formal-function-result",
    "source-module-validation",
    "target-module-validation",
    "original-source-module-artifact",
    "module-case-manifest",
}
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC = "BLOCKED_NOT_EQUIVALENTLY_MODELED"
FORMAL_FUNCTION_INPUT_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "route",
    "input_domain",
    "module_input_sha256",
    "symbol",
    "signature",
    "source_function",
    "source_function_sha256",
    "target_function",
    "target_function_sha256",
    "case_manifest_sha256",
}
FORMAL_FUNCTION_RESULT_KEYS = {
    "schema_version",
    "kind",
    "profile",
    "symbol",
    "status",
    "property_status",
    "proof_strength",
    "solver",
    "version",
    "options",
    "assumptions",
    "countermodel",
    "formal_input_digest",
    "solver_input_digest",
    "formal_input",
    "solver_input",
    "replay_contract",
    "claim_scope",
    "reason",
    "external_soundness_boundary",
    "independent_encodings",
    "certification_status",
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
        )
    except Exception as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_sha256(value: object) -> str:
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _runtime_layout() -> tuple[Path, Path, Path] | None:
    """Resolve the only accepted locked engine/venv/solver layout.

    ``Path.resolve`` is intentionally not used for ``sys.executable`` because
    a venv interpreter may itself be a symlink to a system Python.  The
    lexical executable location is the trust anchor supplied by ``uv
    --directory engines/polyglot-route-engine run --locked``.
    """

    executable = Path(os.path.abspath(sys.executable))
    if executable.parent.name != "bin" or executable.parent.parent.name != ".venv":
        return None
    venv_root = executable.parent.parent
    engine_project = venv_root.parent
    source_root = engine_project / "src"
    if not all((source_root / relative).is_file() for relative in ENGINE_RUNTIME_MODULES.values()):
        return None
    return source_root.resolve(), venv_root.resolve(), (executable.parent / "z3").resolve()


def _clean_proof_environment() -> dict[str, str]:
    layout = _runtime_layout()
    if layout is None:
        return {}
    _, _, z3_cli = layout
    environment = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "PYTHONUSERBASE",
    ):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PATH"] = str(z3_cli.parent) + os.pathsep + os.defpath
    return environment


def _runtime_provenance(
    failures: list[str], label: str
) -> dict[str, Any] | None:
    """Bind proof imports and both Z3 entry points to the locked uv runtime."""

    layout = _runtime_layout()
    if layout is None:
        failures.append(
            f"{label} proof runtime is not the locked polyglot-route-engine uv environment"
        )
        return None
    source_root, venv_root, expected_cli = layout
    lock_path = source_root.parent / "uv.lock"
    if not lock_path.is_file():
        failures.append(f"{label} locked route-engine uv.lock is missing")
        return None
    modules: dict[str, dict[str, str]] = {}
    for module_name, relative in ENGINE_RUNTIME_MODULES.items():
        try:
            module = importlib.import_module(module_name)
            origin_value = getattr(module, "__file__", None)
            if not isinstance(origin_value, str):
                raise ValueError("module has no file origin")
            origin = Path(origin_value).resolve(strict=True)
            expected = (source_root / relative).resolve(strict=True)
            origin.relative_to(source_root)
            if origin != expected:
                raise ValueError(f"origin {origin} != {expected}")
            observed_digest = sha256_file(origin)
            expected_digest = sha256_file(expected)
            if observed_digest != expected_digest:
                raise ValueError("origin digest differs from locked live source")
        except Exception as exc:
            failures.append(f"{label} engine module origin rejected for {module_name}: {exc}")
            return None
        modules[module_name] = {
            "path": str(origin),
            "sha256": observed_digest,
        }

    try:
        z3_module = importlib.import_module("z3")
        z3_origin_value = getattr(z3_module, "__file__", None)
        if not isinstance(z3_origin_value, str):
            raise ValueError("z3 module has no file origin")
        z3_origin = Path(z3_origin_value).resolve(strict=True)
        z3_origin.relative_to(venv_root)
        z3_version = str(z3_module.get_version_string())
        if z3_version != PINNED_Z3_VERSION:
            raise ValueError(f"unexpected z3 Python version {z3_version}")
    except Exception as exc:
        failures.append(f"{label} z3 Python origin rejected: {exc}")
        return None

    resolved_cli = shutil.which("z3")
    try:
        if resolved_cli is None:
            raise ValueError("z3 is absent from PATH")
        cli_path = Path(resolved_cli).resolve(strict=True)
        if cli_path != expected_cli or not expected_cli.is_file():
            raise ValueError(f"PATH resolves {cli_path}, expected {expected_cli}")
        cli_version_run = subprocess.run(
            [str(expected_cli), "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=_clean_proof_environment(),
        )
        expected_version_line = f"Z3 version {PINNED_Z3_VERSION} - 64 bit"
        if cli_version_run.returncode != 0 or cli_version_run.stdout.strip() != expected_version_line:
            raise ValueError("z3 CLI version output is not exact")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        failures.append(f"{label} z3 CLI origin rejected: {exc}")
        return None

    return {
        "engine_modules": modules,
        "z3_python": {
            "path": str(z3_origin),
            "sha256": sha256_file(z3_origin),
            "version": z3_version,
        },
        "z3_cli": {
            "path": str(expected_cli),
            "sha256": sha256_file(expected_cli),
            "version": PINNED_Z3_VERSION,
        },
        "route_engine_lock": {
            "path": str(lock_path.resolve()),
            "sha256": sha256_file(lock_path),
        },
    }


def semantic_value(value: object) -> object:
    """Remove concrete locations while preserving the typed semantic subtree."""

    if isinstance(value, dict):
        return {
            key: semantic_value(item)
            for key, item in value.items()
            if key != "source_span"
        }
    if isinstance(value, list):
        return [semantic_value(item) for item in value]
    return value


def _engine_proof_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any] | None:
    """Load the pinned encoder/oracle used for independent evidence replay.

    All supported entry points run this validator in the route-engine's locked
    ``uv`` environment.  Failing to load that exact API is therefore a closed
    gate, never a reason to trust persisted solver or oracle output.
    """

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.equivalence import (  # type: ignore[import-not-found]
            behavior_equivalence,
            formal_equivalence,
        )
        from elmos_polyglot_route.models import Function  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned proof/oracle API: {exc}")
        return None
    return Function, formal_equivalence, behavior_equivalence


def _engine_domain_api(
    failures: list[str], label: str
) -> tuple[Any, Any, Any] | None:
    """Load the engine's exact-eight domain guards only after origin binding."""

    if _runtime_provenance(failures, label) is None:
        return None
    try:
        from elmos_polyglot_route.engine import (  # type: ignore[import-not-found]
            _enforce_specialized_case_domain,
            _enforce_specialized_semantic_domain,
        )
        from elmos_polyglot_route.models import SemanticIR  # type: ignore[import-not-found]
    except Exception as exc:
        failures.append(f"{label} cannot load pinned specialized-domain API: {exc}")
        return None
    return (
        SemanticIR,
        _enforce_specialized_semantic_domain,
        _enforce_specialized_case_domain,
    )


def _load_json_array(path: Path) -> list[Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
    )
    if not isinstance(value, list):
        raise ValueError(f"{path}: JSON root must be an array")
    return value


def _fresh_formal_equivalence(
    *,
    source_function: dict[str, Any],
    target_function: dict[str, Any],
    source_language: object,
    target_language: object,
    input_digest: str,
    formal_input_reference: dict[str, str],
    input_domain: str,
    label: str,
    failures: list[str],
) -> tuple[dict[str, Any], str] | None:
    """Regenerate a proof in a fresh Z3 process.

    Z3's pretty-printer uses context-local expression identities.  Replaying in
    a new process makes the byte comparison independent of validations already
    performed in this process and matches the generator's fresh-process
    contract.
    """

    parent_provenance = _runtime_provenance(failures, label)
    if parent_provenance is None:
        return None
    layout = _runtime_layout()
    if layout is None:  # already reported by _runtime_provenance
        return None
    source_root, _, _ = layout
    payload = {
        "source_function": source_function,
        "target_function": target_function,
        "source_language": source_language,
        "target_language": target_language,
        "input_digest": input_digest,
        "formal_input_reference": formal_input_reference,
        "input_domain": input_domain,
        "module_files": ENGINE_RUNTIME_MODULES,
        "lock_path": parent_provenance["route_engine_lock"]["path"],
    }
    program = """
import base64
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from elmos_polyglot_route.equivalence import formal_equivalence
from elmos_polyglot_route.models import Function
p = json.load(sys.stdin)
modules = {}
for module_name in p["module_files"]:
    module = importlib.import_module(module_name)
    origin = Path(module.__file__).resolve(strict=True)
    modules[module_name] = {
        "path": str(origin),
        "sha256": "sha256:" + hashlib.sha256(origin.read_bytes()).hexdigest(),
    }
z3_module = importlib.import_module("z3")
z3_origin = Path(z3_module.__file__).resolve(strict=True)
z3_cli = Path(shutil.which("z3") or "").resolve(strict=True)
z3_version_run = subprocess.run(
    [str(z3_cli), "-version"], capture_output=True, text=True, check=False, timeout=10
)
provenance = {
    "engine_modules": modules,
    "z3_python": {
        "path": str(z3_origin),
        "sha256": "sha256:" + hashlib.sha256(z3_origin.read_bytes()).hexdigest(),
        "version": str(z3_module.get_version_string()),
    },
    "z3_cli": {
        "path": str(z3_cli),
        "sha256": "sha256:" + hashlib.sha256(z3_cli.read_bytes()).hexdigest(),
        "version": str(z3_module.get_version_string()),
        "version_output": z3_version_run.stdout.strip(),
        "returncode": z3_version_run.returncode,
    },
    "route_engine_lock": {
        "path": str(Path(p["lock_path"]).resolve(strict=True)),
        "sha256": "sha256:" + hashlib.sha256(Path(p["lock_path"]).read_bytes()).hexdigest(),
    },
}
result, smt = formal_equivalence(
    Function.from_mapping(p["source_function"]),
    Function.from_mapping(p["target_function"]),
    p["source_language"],
    p["target_language"],
    p["input_digest"],
    formal_input_reference=p["formal_input_reference"],
    input_domain=p["input_domain"],
)
print(json.dumps({"result": result, "smt_base64": base64.b64encode(smt.encode("utf-8")).decode("ascii"), "provenance": provenance}, sort_keys=True, separators=(",", ":"), allow_nan=False))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", program],
            input=json.dumps(payload, ensure_ascii=False, allow_nan=False),
            capture_output=True,
            text=True,
            check=False,
            timeout=40,
            # ``PYTHONPATH`` is intentionally scrubbed.  Execute from the
            # digest-checked source root itself so ``sys.path[0]`` can load
            # only the pinned ``elmos_polyglot_route`` package.
            cwd=source_root,
            env=_clean_proof_environment(),
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        failures.append(f"{label} fresh formal re-encoding failed: {exc}")
        return None
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip().splitlines()[-1:] or ["unknown error"]
        failures.append(
            f"{label} fresh formal re-encoding exited nonzero: {diagnostic[0]}"
        )
        return None
    try:
        response = json.loads(
            completed.stdout, parse_constant=_reject_json_constant
        )
        result = response["result"]
        smt = base64.b64decode(response["smt_base64"], validate=True).decode("utf-8")
        child_provenance = response["provenance"]
    except Exception as exc:
        failures.append(f"{label} fresh formal re-encoding output is invalid: {exc}")
        return None
    if not isinstance(result, dict):
        failures.append(f"{label} fresh formal result is not an object")
        return None
    if not isinstance(child_provenance, dict):
        failures.append(f"{label} fresh proof runtime provenance is not an object")
        return None
    child_cli = child_provenance.get("z3_cli")
    if isinstance(child_cli, dict):
        child_cli = {
            key: child_cli.get(key) for key in ("path", "sha256", "version")
        }
    normalized_child = {
        **child_provenance,
        "z3_cli": child_cli,
    }
    if normalized_child != parent_provenance:
        failures.append(f"{label} fresh proof runtime provenance differs from parent")
        return None
    raw_child_cli = child_provenance.get("z3_cli")
    expected_version_line = f"Z3 version {PINNED_Z3_VERSION} - 64 bit"
    if (
        not isinstance(raw_child_cli, dict)
        or raw_child_cli.get("returncode") != 0
        or raw_child_cli.get("version_output") != expected_version_line
    ):
        failures.append(f"{label} fresh z3 CLI version replay is invalid")
        return None
    return result, smt


def _function_chunk_nodes(
    function: object,
) -> tuple[dict[str, dict[str, Any]], dict[str, str | None], dict[str, list[str]]]:
    """Enumerate exactly the syntax nodes emitted by ``semantic_chunks``."""

    if not isinstance(function, dict):
        raise ValueError("function must be an object")
    nodes: dict[str, dict[str, Any]] = {}
    parents: dict[str, str | None] = {}
    children: dict[str, list[str]] = {}

    def add(path: str, value: object, parent: str | None) -> dict[str, Any]:
        if not isinstance(value, dict) or path in nodes:
            raise ValueError(f"invalid/duplicate semantic node: {path}")
        nodes[path] = value
        parents[path] = parent
        if parent is not None:
            children.setdefault(parent, []).append(path)
        children.setdefault(path, [])
        return value

    def expression(value: object, path: str, parent: str) -> None:
        node = add(path, value, parent)
        if node.get("kind") == "binary":
            expression(node.get("left"), f"{path}/left", path)
            expression(node.get("right"), f"{path}/right", path)

    def statements(value: object, base: str, parent: str) -> None:
        if not isinstance(value, list):
            raise ValueError(f"statement list is invalid: {base}")
        for index, raw_statement in enumerate(value):
            path = f"{base}/{index}"
            statement = add(path, raw_statement, parent)
            if statement.get("expression") is not None:
                expression(statement.get("expression"), f"{path}/expression", path)
            if statement.get("condition") is not None:
                expression(statement.get("condition"), f"{path}/condition", path)
            statements(statement.get("then", []), f"{path}/then", path)
            statements(statement.get("else", []), f"{path}/else", path)

    root = "/functions/0"
    add(root, function, None)
    parameters = function.get("parameters")
    if not isinstance(parameters, list):
        raise ValueError("function parameters must be an array")
    for index, parameter in enumerate(parameters):
        add(f"{root}/parameters/{index}", parameter, root)
    statements(function.get("body"), f"{root}/body", root)
    return nodes, parents, children


def _expected_semantic_layer(
    source_function: object, target_function: object
) -> dict[str, Any]:
    source_view = {"functions": [semantic_value(source_function)]}
    target_view = {"functions": [semantic_value(target_function)]}
    differences: list[dict[str, Any]] = []
    if source_view != target_view:
        differences.append(
            {
                "path": "/functions",
                "source_sha256": canonical_json_sha256(source_view),
                "target_sha256": canonical_json_sha256(target_view),
            }
        )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.semantic-equivalence",
        "status": "PASSED" if not differences else "FAILED",
        "source_view_sha256": canonical_json_sha256(source_view),
        "target_view_sha256": canonical_json_sha256(target_view),
        "difference_count": len(differences),
        "differences": differences,
    }


def _validate_nonvacuous_smt(
    *,
    smt_text: str,
    persisted_path: Path,
    label: str,
    failures: list[str],
) -> None:
    """Replay assumptions-only SAT and assumptions+divergence UNSAT."""

    provenance = _runtime_provenance(failures, label)
    if provenance is None:
        return
    try:
        import z3  # type: ignore[import-not-found]

        assertions = list(z3.parse_smt2_string(smt_text))
        if not assertions:
            raise ValueError("SMT contains no assertions")
        assumptions_solver = z3.Solver()
        assumptions_solver.set(timeout=30000, random_seed=0)
        assumptions_solver.add(*assertions[:-1])
        assumption_verdict = assumptions_solver.check()
        divergence_solver = z3.Solver()
        divergence_solver.set(timeout=30000, random_seed=0)
        divergence_solver.add(*assertions)
        divergence_verdict = divergence_solver.check()
    except Exception as exc:
        failures.append(f"{label} independent SMT replay failed: {exc}")
        return
    if assumption_verdict != z3.sat:
        failures.append(f"{label} assumptions-only domain is not SAT")
    if divergence_verdict != z3.unsat:
        failures.append(f"{label} divergence is not UNSAT")
    try:
        replay = subprocess.run(
            [provenance["z3_cli"]["path"], "-smt2", persisted_path.name],
            cwd=persisted_path.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=35,
            env=_clean_proof_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(f"{label} z3 CLI replay failed: {exc}")
    else:
        if replay.returncode != 0 or replay.stdout.strip() != "unsat":
            failures.append(f"{label} z3 CLI replay did not reproduce exact UNSAT")


def _smt_assertions_equivalent(
    persisted: str,
    regenerated: str,
    *,
    label: str,
    failures: list[str],
) -> bool:
    """Compare ordered Z3 ASTs, ignoring unstable local let numbering."""

    if _runtime_provenance(failures, label) is None:
        return False
    try:
        import z3  # type: ignore[import-not-found]

        persisted_assertions = list(z3.parse_smt2_string(persisted))
        regenerated_assertions = list(z3.parse_smt2_string(regenerated))
    except Exception as exc:
        failures.append(f"{label} cannot parse persisted/regenerated SMT: {exc}")
        return False
    if len(persisted_assertions) != len(regenerated_assertions):
        failures.append(f"{label} SMT assertion count differs from re-encoding")
        return False
    if any(
        not z3.eq(persisted_item, regenerated_item)
        for persisted_item, regenerated_item in zip(
            persisted_assertions, regenerated_assertions, strict=True
        )
    ):
        failures.append(f"{label} SMT assertions differ from independent re-encoding")
        return False
    return True


def _validate_concrete_chunk_document(
    document: object,
    *,
    label: str,
    failures: list[str],
    source_record: tuple[dict[str, Any], Path, str] | None,
    target_record: tuple[dict[str, Any], Path, str] | None,
    source_function: object | None = None,
    target_function: object | None = None,
) -> None:
    """Recompute the exact UTF-8 span contract from bound source/target bytes."""

    if not isinstance(document, dict):
        failures.append(f"{label} must be an object")
        return
    if document.get("concrete_spans_required") is not True:
        failures.append(f"{label}.concrete_spans_required must be true")
    if document.get("span_scheme") != "relative-file-utf8-byte-range-end-exclusive-v1":
        failures.append(f"{label}.span_scheme is invalid")
    if document.get("kind") != "elmos.chunk-equivalence":
        failures.append(f"{label}.kind is invalid")
    if document.get("status") != "PASSED":
        failures.append(f"{label}.status must be PASSED")
    if document.get("path_scheme") != "rfc6901-json-pointer-v1":
        failures.append(f"{label}.path_scheme is invalid")
    if document.get("hash_scheme") != "sha256-canonical-semantic-subtree-v1":
        failures.append(f"{label}.hash_scheme is invalid")
    for field in (
        "missing_source_span_count",
        "missing_target_span_count",
        "mismatch_count",
        "unexpected_target_chunk_count",
    ):
        if document.get(field) != 0:
            failures.append(f"{label}.{field} must be zero")
    span_validation = document.get("span_validation")
    if not isinstance(span_validation, dict):
        failures.append(f"{label}.span_validation must be an object")
        return
    if span_validation.get("status") != "PASSED":
        failures.append(f"{label}.span_validation.status must be PASSED")
    mappings = document.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        failures.append(f"{label}.mappings must be non-empty")
        return
    if document.get("required_source_chunk_count") != len(mappings):
        failures.append(f"{label}.required_source_chunk_count drift")
    if document.get("mapped_source_chunk_count") != len(mappings):
        failures.append(f"{label}.mapped_source_chunk_count drift")
    if document.get("coverage") != 1.0:
        failures.append(f"{label}.coverage must be 1.0")
    if document.get("unexpected_target_paths") != []:
        failures.append(f"{label}.unexpected_target_paths must be empty")

    semantic_nodes: dict[str, dict[str, dict[str, Any]]] = {}
    semantic_parents: dict[str, dict[str, str | None]] = {}
    semantic_children: dict[str, dict[str, list[str]]] = {}
    for side, function in (("source", source_function), ("target", target_function)):
        if function is None:
            failures.append(f"{label} has no bound {side} semantic function")
            continue
        try:
            nodes, parents, children = _function_chunk_nodes(function)
        except Exception as exc:
            failures.append(f"{label} {side} semantic function is invalid: {exc}")
            continue
        semantic_nodes[side] = nodes
        semantic_parents[side] = parents
        semantic_children[side] = children
    declared_paths: list[str] = []
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            failures.append(f"{label}.mappings[{index}] must be an object")
            continue
        if mapping.get("status") != "EXACT":
            failures.append(f"{label}.mappings[{index}].status must be EXACT")
        semantic_path = mapping.get("semantic_path")
        if not isinstance(semantic_path, str) or not semantic_path.startswith("/"):
            failures.append(f"{label}.mappings[{index}].semantic_path is invalid")
            continue
        declared_paths.append(semantic_path)
    if len(declared_paths) != len(mappings):
        failures.append(f"{label}.mappings contain invalid/non-path entries")
    if len(declared_paths) != len(set(declared_paths)):
        failures.append(f"{label}.mappings contain duplicate semantic paths")
    for side, nodes in semantic_nodes.items():
        if set(declared_paths) != set(nodes):
            failures.append(f"{label} {side} semantic path set is not complete/exact")

    for side, record in (("source", source_record), ("target", target_record)):
        metadata = span_validation.get(side)
        if not isinstance(metadata, dict):
            failures.append(f"{label}.span_validation.{side} must be an object")
            continue
        if metadata.get("status") != "PASSED":
            failures.append(f"{label}.span_validation.{side}.status must be PASSED")
        if record is None:
            failures.append(f"{label} has no byte-bound {side} artifact")
            continue
        _, artifact_path, artifact_digest = record
        artifact_bytes = artifact_path.read_bytes()
        if metadata.get("artifact_sha256") != artifact_digest:
            failures.append(f"{label}.span_validation.{side} digest drift")
        if metadata.get("artifact_byte_count") != len(artifact_bytes):
            failures.append(f"{label}.span_validation.{side} byte count drift")
        if metadata.get("logical_file") != artifact_path.name:
            failures.append(f"{label}.span_validation.{side} logical file drift")
        if metadata.get("node_count") != len(mappings):
            failures.append(f"{label}.span_validation.{side} node count drift")
        nodes = semantic_nodes.get(side, {})
        spans_by_path: dict[str, dict[str, Any]] = {}
        for index, mapping in enumerate(mappings):
            if not isinstance(mapping, dict):
                failures.append(f"{label}.mappings[{index}] must be an object")
                continue
            span = mapping.get(f"{side}_span")
            if not isinstance(span, dict) or set(span) != {
                "file",
                "start_byte",
                "end_byte",
            }:
                failures.append(f"{label}.mappings[{index}].{side}_span is not exact")
                continue
            semantic_path = mapping.get("semantic_path")
            node = nodes.get(semantic_path) if isinstance(semantic_path, str) else None
            if node is None:
                failures.append(
                    f"{label}.mappings[{index}] has unknown {side} semantic path"
                )
            elif span != node.get("source_span"):
                failures.append(
                    f"{label}.mappings[{index}].{side}_span does not bind semantic IR"
                )
            if isinstance(semantic_path, str):
                spans_by_path[semantic_path] = span
            start = span.get("start_byte")
            end = span.get("end_byte")
            if span.get("file") != artifact_path.name:
                failures.append(
                    f"{label}.mappings[{index}].{side}_span logical file drift"
                )
            if (
                not _is_int(start, minimum=0)
                or not _is_int(end, minimum=1)
                or int(start) >= int(end)
                or int(end) > len(artifact_bytes)
            ):
                failures.append(
                    f"{label}.mappings[{index}].{side}_span is outside UTF-8 byte bounds"
                )
            pointer = mapping.get(f"{side}_artifact_pointer")
            if pointer != f"{artifact_digest}#{semantic_path}":
                failures.append(
                    f"{label}.mappings[{index}].{side}_artifact_pointer drift"
                )
            if mapping.get(f"{side}_semantic_pointer") != semantic_path:
                failures.append(
                    f"{label}.mappings[{index}].{side}_semantic_pointer drift"
                )
            if node is not None:
                observed_semantic_hash = canonical_json_sha256(semantic_value(node))
                if mapping.get("semantic_hash") != observed_semantic_hash:
                    failures.append(
                        f"{label}.mappings[{index}] {side} semantic_hash drift"
                    )
                expected_chunk_id = sha256_bytes(
                    f"{artifact_digest}\0{semantic_path}\0{observed_semantic_hash}".encode(
                        "utf-8"
                    )
                )
                if mapping.get(f"{side}_chunk_id") != expected_chunk_id:
                    failures.append(
                        f"{label}.mappings[{index}].{side}_chunk_id drift"
                    )

        parents = semantic_parents.get(side, {})
        children = semantic_children.get(side, {})
        for path, parent in parents.items():
            if parent is None or path not in spans_by_path or parent not in spans_by_path:
                continue
            child_span = spans_by_path[path]
            parent_span = spans_by_path[parent]
            if (
                child_span.get("start_byte", -1) < parent_span.get("start_byte", 0)
                or child_span.get("end_byte", 0) > parent_span.get("end_byte", -1)
            ):
                failures.append(f"{label} {side} parent span does not cover {path}")
        for parent, child_paths in children.items():
            ranged = [
                (
                    spans_by_path[path].get("start_byte"),
                    spans_by_path[path].get("end_byte"),
                    path,
                )
                for path in child_paths
                if path in spans_by_path
            ]
            if any(not _is_int(start) or not _is_int(end, minimum=1) for start, end, _ in ranged):
                continue
            ranged.sort()
            for previous, current in zip(ranged, ranged[1:], strict=False):
                if previous[1] > current[0]:
                    failures.append(
                        f"{label} {side} sibling spans overlap: {previous[2]} / {current[2]}"
                    )


def _validate_module_behavior_layer(
    *,
    symbol: str,
    source_function: object,
    layer: object,
    cases: object,
    source_validation: object,
    target_validation: object,
    source_observations: object,
    target_observations: object,
    failures: list[str],
) -> None:
    """Verify reported behavior rows against manifest cases and persisted observations."""

    label = f"module function {symbol} behavior"
    if not isinstance(layer, dict) or not isinstance(cases, list) or not cases:
        failures.append(f"{label} or its cases are invalid")
        return
    case_count = len(cases)
    expected_counts = {
        "case_count": case_count,
        "pass_count": case_count,
        "source_runtime_pass_count": case_count,
        "target_runtime_pass_count": case_count,
        "counterexample_count": 0,
        "oracle_conflict_count": 0,
    }
    for field, expected in expected_counts.items():
        if layer.get(field) != expected:
            failures.append(f"{label}.{field} must equal {expected}")
    if layer.get("status") != "PASSED":
        failures.append(f"{label}.status must be PASSED")
    for field in ("source_runtime_passed", "target_runtime_passed"):
        if layer.get(field) is not True:
            failures.append(f"{label}.{field} must be true")
    if layer.get("counterexamples") != []:
        failures.append(f"{label}.counterexamples must be empty")
    if not isinstance(source_validation, dict) or not isinstance(target_validation, dict):
        failures.append(f"{label} validation records are missing")
        return
    for side, validation, observations in (
        ("source", source_validation, source_observations),
        ("target", target_validation, target_observations),
    ):
        if validation.get("status") != "PASSED":
            failures.append(f"{label} {side} validation did not pass")
        if validation.get("case_count") != case_count:
            failures.append(f"{label} {side} validation case count drift")
        if not isinstance(observations, list) or len(observations) != case_count:
            failures.append(f"{label} {side} persisted observations are incomplete")
        elif validation.get("observations") != observations:
            failures.append(f"{label} {side} validation/observation artifact drift")
    results = layer.get("results")
    if not isinstance(results, list) or len(results) != case_count:
        failures.append(f"{label}.results count drift")
        return
    by_case_id = {
        item.get("case_id"): item for item in results if isinstance(item, dict)
    }
    if set(by_case_id) != set(range(case_count)) or len(by_case_id) != len(results):
        failures.append(f"{label}.results case ids are not exact")
        return
    if not isinstance(source_observations, list) or not isinstance(
        target_observations, list
    ):
        return
    for case_id, case in enumerate(cases):
        if not isinstance(case, dict):
            failures.append(f"{label} case {case_id} is invalid")
            continue
        result = by_case_id[case_id]
        expected = case.get("expected")
        if result.get("status") != "PASSED":
            failures.append(f"{label} case {case_id} did not pass")
        if result.get("independent_expected") != expected:
            failures.append(f"{label} case {case_id} expected value drift")
        canonical = result.get("canonical")
        if not isinstance(canonical, dict) or canonical.get("status") != "RETURNED":
            failures.append(f"{label} case {case_id} canonical result is invalid")
        elif canonical.get("error") is not None or canonical.get("value") != expected:
            failures.append(f"{label} case {case_id} canonical value drift")
        if result.get("source_native") != source_observations[case_id]:
            failures.append(f"{label} case {case_id} source observation drift")
        if result.get("target_native") != target_observations[case_id]:
            failures.append(f"{label} case {case_id} target observation drift")
        if (
            isinstance(result.get("source_native"), dict)
            and isinstance(result.get("target_native"), dict)
            and result["source_native"].get("raw") != result["target_native"].get("raw")
        ):
            failures.append(f"{label} case {case_id} raw native encodings differ")

    api = _engine_proof_api(failures, label)
    if api is None or not isinstance(source_function, dict):
        return
    Function, _, behavior_equivalence = api
    try:
        function = Function.from_mapping(source_function)
        regenerated = behavior_equivalence(
            function,
            cases,
            source_observations,
            target_observations,
        )
    except Exception as exc:
        failures.append(f"{label} independent canonical replay failed: {exc}")
        return
    if layer != regenerated:
        failures.append(f"{label} differs from independent canonical replay")

    return_type = function.return_type
    for side, observations in (
        ("source", source_observations),
        ("target", target_observations),
    ):
        for case_id, observation in enumerate(observations):
            observation_label = f"{label} {side} observation {case_id}"
            if not isinstance(observation, dict) or set(observation) != {
                "case_id",
                "encoding",
                "raw",
                "status",
                "value",
            }:
                failures.append(f"{observation_label} keys are not exact")
                continue
            value = observation.get("value")
            if observation.get("case_id") != case_id:
                failures.append(f"{observation_label} case_id drift")
            if observation.get("status") != "RETURNED":
                failures.append(f"{observation_label} status must be RETURNED")
            if return_type == "integer":
                valid = (
                    observation.get("encoding") == "i64-dec"
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                    and -(2**63) <= value <= 2**63 - 1
                    and observation.get("raw") == str(value)
                )
            elif return_type == "number":
                valid = (
                    observation.get("encoding") == "fp64-hex"
                    and isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and observation.get("raw")
                    == struct.pack(">d", float(value)).hex()
                )
            elif return_type == "boolean":
                valid = (
                    observation.get("encoding") == "bool"
                    and isinstance(value, bool)
                    and observation.get("raw") == ("true" if value else "false")
                )
            else:
                valid = False
            if not valid:
                failures.append(f"{observation_label} typed raw encoding drift")


def _validate_module_formal_closure(
    *,
    symbol: str,
    signature: object,
    source_function: object,
    target_function: object,
    semantic_layer: object,
    case_manifest_sha256: object,
    formal: object,
    module_input_sha256: object,
    route_scope: dict[str, Any],
    artifacts_by_path: dict[str, tuple[dict[str, Any], Path, str]],
    failures: list[str],
) -> None:
    """Rebind and replay one function's input/SMT/result proof closure."""

    label = f"module function {symbol} formal"
    if not isinstance(formal, dict):
        failures.append(f"{label} layer is invalid")
        return
    records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for field, role in (
        ("formal_input_path", "formal-function-input"),
        ("solver_input_path", "formal-function-smt2"),
        ("formal_result_path", "formal-function-result"),
    ):
        relative = formal.get(field)
        record = artifacts_by_path.get(relative) if isinstance(relative, str) else None
        if record is None or record[0].get("role") != role:
            failures.append(f"{label}.{field} is not bound to role {role}")
            continue
        digest_field = field.replace("_path", "_sha256")
        if formal.get(digest_field) != record[2]:
            failures.append(f"{label}.{digest_field} drift")
        records[role] = record
    if set(records) != {
        "formal-function-input",
        "formal-function-smt2",
        "formal-function-result",
    }:
        return
    input_record = records["formal-function-input"]
    solver_record = records["formal-function-smt2"]
    result_record = records["formal-function-result"]
    try:
        formal_input = load(input_record[1])
        formal_result = load(result_record[1])
    except Exception as exc:
        failures.append(f"{label} closure JSON is invalid: {exc}")
        return
    if set(formal_input) != FORMAL_FUNCTION_INPUT_KEYS:
        failures.append(f"{label} input keys are not exact")
    if set(formal_result) != FORMAL_FUNCTION_RESULT_KEYS:
        failures.append(f"{label} result keys are not exact")
    expected_route = {
        "route_key": route_scope.get("route_key"),
        "source_language": route_scope.get("source_language"),
        "target_language": route_scope.get("target_language"),
    }
    if formal_input.get("route") != expected_route:
        failures.append(f"{label} input route drift")
    for field, expected in (
        ("schema_version", "1.0.0"),
        ("kind", "typed-pure-module-function-formal-input"),
        ("profile", "typed-pure-module-v1"),
        ("input_domain", SPECIALIZED_INPUT_DOMAIN),
        ("module_input_sha256", module_input_sha256),
        ("symbol", symbol),
        ("signature", signature),
        ("case_manifest_sha256", case_manifest_sha256),
    ):
        if formal_input.get(field) != expected:
            failures.append(f"{label} input {field} drift")
    for side in ("source", "target"):
        function_value = formal_input.get(f"{side}_function")
        if canonical_json_sha256(function_value) != formal_input.get(
            f"{side}_function_sha256"
        ):
            failures.append(f"{label} {side} function digest drift")
    expected_source_function = semantic_value(source_function)
    expected_target_function = semantic_value(target_function)
    if formal_input.get("source_function") != expected_source_function:
        failures.append(f"{label} source function is detached from source module IR")
    if formal_input.get("target_function") != expected_target_function:
        failures.append(f"{label} target function is detached from target module IR")
    expected_semantic = _expected_semantic_layer(source_function, target_function)
    if semantic_layer != expected_semantic:
        failures.append(f"{label} semantic layer differs from bound module IR")
    for key, expected in (
        ("schema_version", "1.0.0"),
        ("kind", "typed-pure-module-function-formal-result"),
        ("profile", "typed-pure-module-v1"),
        ("symbol", symbol),
        ("status", "PROVED_UNDER_ASSUMPTIONS"),
        ("property_status", "PROVED"),
        ("proof_strength", "THEOREM_UNDER_ASSUMPTIONS"),
        ("solver", "z3"),
        ("version", "4.16.0"),
        ("countermodel", None),
        ("formal_input_digest", input_record[2]),
        ("solver_input_digest", solver_record[2]),
        ("certification_status", "NOT_CERTIFIED"),
    ):
        if formal_result.get(key) != expected:
            failures.append(f"{label} result {key} drift")
    for key in FORMAL_FUNCTION_RESULT_KEYS:
        if formal.get(key) != formal_result.get(key):
            failures.append(f"{label} report/result {key} drift")
    assumptions = formal_result.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or any(
        not isinstance(item, str) or not item for item in assumptions
    ):
        failures.append(f"{label} assumptions must be non-empty")
    claim_scope = formal_result.get("claim_scope")
    if (
        not isinstance(claim_scope, dict)
        or claim_scope.get("input_domain") != SPECIALIZED_INPUT_DOMAIN
    ):
        failures.append(f"{label} claim input domain drift")
    if formal_result.get("external_soundness_boundary") != {
        "analyzer_and_emitter_soundness": "ASSUMPTION",
        "source_compiler_runtime_soundness": "NOT_RUN",
        "target_compiler_runtime_soundness": "NOT_RUN",
    }:
        failures.append(f"{label} external soundness boundary is overstated")
    expected_input_ref = {"path": input_record[1].name, "sha256": input_record[2]}
    expected_solver_ref = {"path": solver_record[1].name, "sha256": solver_record[2]}
    if formal_result.get("formal_input") != expected_input_ref:
        failures.append(f"{label} result formal_input ref drift")
    if formal_result.get("solver_input") != expected_solver_ref:
        failures.append(f"{label} result solver_input ref drift")
    expected_replay = {
        "kind": "z3-cli-check-sat",
        "argv": ["z3", "-smt2", solver_record[1].name],
        "working_directory": ".",
        "expected_exit_code": 0,
        "expected_stdout": "unsat",
    }
    if formal_result.get("replay_contract") != expected_replay:
        failures.append(f"{label} replay contract drift")
    options = formal_result.get("options")
    if options != {
        "timeout_ms": 30000,
        "random_seed": 0,
        "theories": ["QF_BV", "FP", "Seq", "Bool", "Int"],
    }:
        failures.append(f"{label} solver options drift")
    solver_text = solver_record[1].read_text(encoding="utf-8")
    required_headers = (
        f"; formal_input_digest: {input_record[2]}",
        f"; formal-input-sha256: {input_record[2]}",
        f"; formal-input-path: {input_record[1].name}",
        f"; input-domain: {SPECIALIZED_INPUT_DOMAIN}",
    )
    if any(header not in solver_text.splitlines()[:16] for header in required_headers):
        failures.append(f"{label} SMT input header is not bound to formal input/domain")
    regenerated_closure = _fresh_formal_equivalence(
        source_function=expected_source_function,
        target_function=expected_target_function,
        source_language=route_scope.get("source_language"),
        target_language=route_scope.get("target_language"),
        input_digest=input_record[2],
        formal_input_reference=expected_input_ref,
        input_domain=SPECIALIZED_INPUT_DOMAIN,
        label=label,
        failures=failures,
    )
    if regenerated_closure is None:
        return
    regenerated, regenerated_smt = regenerated_closure
    _smt_assertions_equivalent(
        solver_text,
        regenerated_smt,
        label=label,
        failures=failures,
    )
    regenerated_solver = regenerated.get("solver")
    if not isinstance(regenerated_solver, dict):
        failures.append(f"{label} regenerated solver identity is invalid")
        return
    expected_result = {
        "schema_version": "1.0.0",
        "kind": "typed-pure-module-function-formal-result",
        "profile": "typed-pure-module-v1",
        "symbol": symbol,
        "status": regenerated.get("status"),
        "property_status": regenerated.get("property_status"),
        "proof_strength": regenerated.get("proof_strength"),
        "solver": regenerated_solver.get("name"),
        "version": regenerated_solver.get("version"),
        "options": {
            "timeout_ms": regenerated_solver.get("timeout_ms"),
            "random_seed": regenerated_solver.get("random_seed"),
            "theories": regenerated_solver.get("theories"),
        },
        "assumptions": regenerated.get("assumptions"),
        "countermodel": regenerated.get("countermodel"),
        "formal_input_digest": input_record[2],
        "solver_input_digest": solver_record[2],
        "formal_input": expected_input_ref,
        "solver_input": expected_solver_ref,
        "replay_contract": expected_replay,
        "claim_scope": regenerated.get("claim_scope"),
        "reason": regenerated.get("reason"),
        "external_soundness_boundary": regenerated.get(
            "external_soundness_boundary"
        ),
        "independent_encodings": regenerated.get("independent_encodings"),
        "certification_status": regenerated.get("certification_status"),
    }
    if formal_result != expected_result:
        failures.append(f"{label} result differs from independent re-encoding")
    if regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS" or regenerated.get(
        "property_status"
    ) != "PROVED":
        failures.append(f"{label} independent re-encoding did not prove the property")
    _validate_nonvacuous_smt(
        smt_text=regenerated_smt,
        persisted_path=solver_record[1],
        label=label,
        failures=failures,
    )


def _validate_function_formal_closure(
    *,
    label: str,
    manifest: dict[str, Any],
    formal_input: object,
    formal_input_record: tuple[dict[str, Any], Path, str],
    solver_input_record: tuple[dict[str, Any], Path, str],
    solver_result: object,
    failures: list[str],
) -> None:
    """Independently regenerate one corpus proof from its byte-bound input."""

    if not isinstance(formal_input, dict) or not isinstance(solver_result, dict):
        failures.append(f"{label} input/result documents are invalid")
        return
    source_binding = formal_input.get("source_normalized_ir")
    target_binding = formal_input.get("target_relift_normalized_ir")
    if not isinstance(source_binding, dict) or not isinstance(target_binding, dict):
        failures.append(f"{label} normalized function bindings are missing")
        return
    source_function = source_binding.get("formal_function")
    target_function = target_binding.get("formal_function")
    if not isinstance(source_function, dict) or not isinstance(target_function, dict):
        failures.append(f"{label} normalized formal functions are missing")
        return
    source_language = manifest.get("source", {}).get("language")
    target_language = manifest.get("target", {}).get("language")
    domain_api = _engine_domain_api(failures, label)
    if domain_api is None:
        return
    SemanticIR, enforce_semantic_domain, enforce_case_domain = domain_api
    try:
        source_ir = SemanticIR.from_mapping(source_binding.get("semantic_ir"))
        target_ir = SemanticIR.from_mapping(target_binding.get("semantic_ir"))
        enforce_semantic_domain(source_ir, source_language, target_language)
        enforce_semantic_domain(target_ir, source_language, target_language)
        if len(source_ir.functions) != 1 or len(target_ir.functions) != 1:
            raise ValueError("formal semantic IR must contain exactly one function")
        cases_path = formal_input_record[1].parent / "inputs" / "cases.json"
        cases = _load_json_array(cases_path)
        enforce_case_domain(
            source_ir.functions[0], cases, source_language, target_language
        )
    except Exception as exc:
        failures.append(f"{label} specialized semantic/case domain rejected: {exc}")
        return
    formal_input_reference = {
        "path": formal_input_record[1].name,
        "sha256": formal_input_record[2],
    }
    input_domain = "profile-total-domain"
    claim_scope = formal_input.get("claim_scope")
    if isinstance(claim_scope, dict) and isinstance(
        claim_scope.get("input_domain"), str
    ):
        input_domain = claim_scope["input_domain"]
    regenerated_closure = _fresh_formal_equivalence(
        source_function=source_function,
        target_function=target_function,
        source_language=source_language,
        target_language=target_language,
        input_digest=formal_input_record[2],
        formal_input_reference=formal_input_reference,
        input_domain=input_domain,
        label=label,
        failures=failures,
    )
    if regenerated_closure is None:
        return
    regenerated, regenerated_smt = regenerated_closure
    persisted_smt = solver_input_record[1].read_bytes()
    try:
        persisted_smt_text = persisted_smt.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{label} persisted SMT is not UTF-8: {exc}")
        return
    _smt_assertions_equivalent(
        persisted_smt_text,
        regenerated_smt,
        label=label,
        failures=failures,
    )
    expected_result = {
        **regenerated,
        "formal_input_digest": formal_input_record[2],
        "solver_input_digest": solver_input_record[2],
    }
    if solver_result != expected_result:
        failures.append(f"{label} solver result differs from independent re-encoding")
    if regenerated.get("status") != "PROVED_UNDER_ASSUMPTIONS" or regenerated.get(
        "property_status"
    ) != "PROVED":
        failures.append(f"{label} independent re-encoding did not prove the property")
    _validate_nonvacuous_smt(
        smt_text=persisted_smt_text,
        persisted_path=solver_input_record[1],
        label=label,
        failures=failures,
    )


def strict_evidence_requested(certification: dict[str, Any]) -> bool:
    evidence_format = certification.get("evidence_format")
    return (
        isinstance(evidence_format, int)
        and not isinstance(evidence_format, bool)
        and evidence_format >= 2
    ) or "formal_equivalence" in certification


def _is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _require_exact_keys(
    failures: list[str],
    value: object,
    *,
    required: set[str],
    allowed: set[str] | None = None,
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        failures.append(f"{label} must be an object")
        return None
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - (allowed or required))
    if missing:
        failures.append(f"{label} missing keys: {', '.join(missing)}")
    if extra:
        failures.append(f"{label} has unknown keys: {', '.join(extra)}")
    return value


def _require_nonempty_strings(
    failures: list[str], values: object, label: str
) -> list[str] | None:
    if not isinstance(values, list) or any(
        not isinstance(item, str) or not item for item in values
    ):
        failures.append(f"{label} must be an array of non-empty strings")
        return None
    return values


def _require_digest(failures: list[str], value: object, label: str) -> str | None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        failures.append(f"{label} must be a canonical sha256 digest")
        return None
    return value


def _resolve_below(
    root: Path, relative: object, label: str, failures: list[str]
) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        failures.append(f"{label} must be a non-empty route-relative path")
        return None
    root_resolved = root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        failures.append(f"{label} escapes the route directory: {relative}")
        return None
    return candidate


def _replay_execution_root(route: Path) -> Path:
    """Return the immutable root within which a replay command may resolve.

    Checked-in routes live below ``<repo>/routes`` and may invoke the pinned
    engine or runner from that repository.  Relocated evidence bundles keep
    their replay launcher below the route directory itself.
    """

    resolved = route.resolve()
    if resolved.parent.name == "routes":
        return resolved.parent.parent
    return resolved


def _resolve_replay_path(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_file():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _resolve_replay_directory(
    cwd: Path,
    token: str,
    execution_root: Path,
    label: str,
    failures: list[str],
) -> Path | None:
    if not token or Path(token).is_absolute() or "://" in token or "\\" in token:
        failures.append(f"{label} must be a relative POSIX path")
        return None
    candidate = (cwd / token).resolve(strict=False)
    try:
        candidate.relative_to(execution_root.resolve())
    except ValueError:
        failures.append(f"{label} escapes the replay execution root: {token}")
        return None
    if not candidate.is_dir():
        failures.append(f"{label} does not exist: {token}")
        return None
    return candidate


def _validate_replay_command(
    *,
    route: Path,
    manifest: dict[str, Any],
    command: list[str],
    cwd: Path,
    records: dict[str, tuple[dict[str, Any], Path, str]],
    failures: list[str],
) -> None:
    """Validate that replay argv is executable, scoped, and byte-bound.

    The command is intentionally restricted to a Python launcher, optionally
    provisioned by ``uv run --locked``.  Repository evidence may invoke the
    exact route runner; a relocated pack may invoke its route-local integrity
    launcher.  In either case the executed Python file must be present in
    ``artifact_refs`` with the exact observed digest.
    """

    execution_root = _replay_execution_root(route)
    executable = command[0]
    script_index: int | None = None

    if executable == "uv":
        if shutil.which("uv") is None:
            failures.append("formal_proof.replay.command executable uv is unavailable")
        if len(command) < 8 or command[1] != "--directory":
            failures.append(
                "formal_proof.replay.command uv form must declare --directory"
            )
            return
        _resolve_replay_directory(
            cwd,
            command[2],
            execution_root,
            "formal_proof.replay.command uv directory",
            failures,
        )
        if command[3:6] != ["run", "--locked", "python"]:
            failures.append(
                "formal_proof.replay.command uv form must use run --locked python"
            )
        script_index = 6
    elif executable in {"python", "python3"}:
        if shutil.which(executable) is None:
            failures.append(
                f"formal_proof.replay.command executable {executable} is unavailable"
            )
        script_index = 1
    elif "/" in executable:
        interpreter = _resolve_replay_path(
            cwd,
            executable,
            execution_root,
            "formal_proof.replay.command interpreter",
            failures,
        )
        if interpreter is not None and (
            not interpreter.name.startswith("python")
            or not os.access(interpreter, os.X_OK)
        ):
            failures.append(
                "formal_proof.replay.command interpreter must be an executable Python binary"
            )
        script_index = 1
    else:
        failures.append(
            "formal_proof.replay.command must use python, python3, a relative Python binary, or uv"
        )
        return

    if script_index >= len(command):
        failures.append("formal_proof.replay.command is missing its Python script")
        return
    script = _resolve_replay_path(
        cwd,
        command[script_index],
        execution_root,
        "formal_proof.replay.command script",
        failures,
    )
    if script is None:
        return
    if script.suffix != ".py":
        failures.append("formal_proof.replay.command script must be a Python file")

    script_digest = sha256_file(script)
    try:
        route_relative = script.relative_to(route.resolve()).as_posix()
    except ValueError:
        root_relative = script.relative_to(execution_root.resolve()).as_posix()

        def path_matches(reference: str) -> bool:
            return reference == root_relative or reference.endswith("/" + root_relative)

    else:

        def path_matches(reference: str) -> bool:
            return reference == route_relative

    bindings = [
        record
        for record in records.values()
        if record[0].get("role") in {"engine-source", "replay-tool"}
        and record[2] == script_digest
        and isinstance(record[0].get("path"), str)
        and path_matches(record[0]["path"])
    ]
    if len(bindings) != 1:
        failures.append(
            "formal_proof.replay.command script must have exactly one matching engine-source or replay-tool artifact"
        )

    arguments = command[script_index + 1 :]
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in {"--repo-root", "--route"} or index + 1 >= len(arguments):
            failures.append(
                f"formal_proof.replay.command has unsupported argument: {option}"
            )
            return
        if option in parsed:
            failures.append(f"formal_proof.replay.command repeats argument: {option}")
            return
        parsed[option] = arguments[index + 1]
        index += 2

    route_argument = parsed.get("--route")
    if route_argument == ".":
        if cwd.resolve() != route.resolve():
            failures.append(
                "formal_proof.replay.command --route . requires the route directory as cwd"
            )
    elif route_argument != manifest.get("route_key"):
        failures.append(
            "formal_proof.replay.command --route must bind the exact route_key"
        )
    repository_argument = parsed.get("--repo-root")
    if repository_argument is not None:
        repository_root = (cwd / repository_argument).resolve(strict=False)
        if repository_root != execution_root.resolve() or not repository_root.is_dir():
            failures.append(
                "formal_proof.replay.command --repo-root must resolve to the replay execution root"
            )


def validate_artifact_ref(
    route: Path,
    reference: object,
    label: str,
    failures: list[str],
    *,
    require_identity: bool = True,
) -> tuple[Path, str] | None:
    value = _require_exact_keys(
        failures,
        reference,
        required=ARTIFACT_REF_KEYS if require_identity else {"path", "sha256", "bytes"},
        label=label,
    )
    if value is None:
        return None
    if require_identity:
        artifact_id = value.get("artifact_id")
        if (
            not isinstance(artifact_id, str)
            or ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        ):
            failures.append(f"{label}.artifact_id is invalid")
        role = value.get("role")
        if role not in ARTIFACT_ROLES:
            failures.append(f"{label}.role is invalid")
    path = _resolve_below(route, value.get("path"), f"{label}.path", failures)
    digest = _require_digest(failures, value.get("sha256"), f"{label}.sha256")
    byte_count = value.get("bytes")
    if not _is_int(byte_count, minimum=1):
        failures.append(f"{label}.bytes must be a positive integer")
    if path is None or digest is None or not _is_int(byte_count, minimum=1):
        return None
    if not path.is_file():
        failures.append(f"{label} artifact is missing: {value.get('path')}")
        return None
    observed_bytes = path.stat().st_size
    if observed_bytes != byte_count:
        failures.append(
            f"{label} byte count mismatch: expected {byte_count}, observed {observed_bytes}"
        )
    observed_digest = sha256_file(path)
    if observed_digest != digest:
        failures.append(f"{label} digest mismatch: {value.get('path')}")
    return path, observed_digest


def _artifact_record(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    artifact_id: object,
    *,
    expected_roles: set[str],
    label: str,
    failures: list[str],
) -> tuple[dict[str, Any], Path, str] | None:
    if not isinstance(artifact_id, str) or artifact_id not in records:
        failures.append(f"{label} references unknown artifact_id: {artifact_id}")
        return None
    record = records[artifact_id]
    role = record[0].get("role")
    if role not in expected_roles:
        failures.append(
            f"{label} artifact {artifact_id} has role {role}, expected one of {sorted(expected_roles)}"
        )
        return None
    return record


def _json_pointer_value(document: object, pointer: str) -> object:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"invalid array index {token!r}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"array index out of range: {index}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise ValueError(f"object key does not exist: {token!r}")
            current = current[token]
        else:
            raise ValueError(f"cannot traverse through {type(current).__name__}")
    return current


def _artifact_pointer(
    records: dict[str, tuple[dict[str, Any], Path, str]],
    reference: object,
    *,
    expected_role: str,
    label: str,
    failures: list[str],
) -> tuple[str, str, object, tuple[dict[str, Any], Path, str]] | None:
    if not isinstance(reference, str) or reference.count("#") != 1:
        failures.append(f"{label} must be <artifact_id>#<RFC6901 JSON pointer>")
        return None
    artifact_id, pointer = reference.split("#", 1)
    record = _artifact_record(
        records,
        artifact_id,
        expected_roles={expected_role},
        label=label,
        failures=failures,
    )
    if record is None:
        return None
    try:
        document = json.loads(
            record[1].read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
        value = _json_pointer_value(document, pointer)
    except Exception as exc:
        failures.append(f"{label} cannot resolve JSON pointer {pointer!r}: {exc}")
        return None
    return artifact_id, pointer, value, record


def _validate_formal_input_document(
    route: Path,
    record: tuple[dict[str, Any], Path, str],
    records: dict[str, tuple[dict[str, Any], Path, str]],
    manifest: dict[str, Any],
    proof: dict[str, Any],
    label: str,
    failures: list[str],
) -> dict[str, Any] | None:
    try:
        document = load(record[1])
    except Exception as exc:
        failures.append(f"{label} is invalid JSON: {exc}")
        return None
    missing = FORMAL_INPUT_REQUIRED_KEYS - set(document)
    if missing:
        failures.append(f"{label} missing keys: {', '.join(sorted(missing))}")
        return document
    if document.get("kind") != "elmos.formal-equivalence-input":
        failures.append(f"{label}.kind is invalid")
    route_scope = document.get("route")
    if not isinstance(route_scope, dict):
        failures.append(f"{label}.route must be an object")
    else:
        expected_route = {
            "source_language": manifest.get("source", {}).get("language"),
            "target_language": manifest.get("target", {}).get("language"),
            "profile": manifest.get("profiles", {}).get("semantic_profile"),
        }
        if route_scope != expected_route:
            failures.append(f"{label}.route does not match route.json")
    claim_scope = document.get("claim_scope")
    if not isinstance(claim_scope, dict):
        failures.append(f"{label}.claim_scope must be an object")
    else:
        if (
            claim_scope.get("relation")
            != "canonical-normalized-source-ir-to-target-relift-ir"
            or claim_scope.get("original_source_bytes_theorem") is not False
            or claim_scope.get("source_compiler_runtime_soundness") != "NOT_RUN"
            or claim_scope.get("target_compiler_runtime_soundness") != "NOT_RUN"
        ):
            failures.append(f"{label}.claim_scope overstates the proved relation")
        if (
            manifest.get("gates", {}).get(
                "canonical_finite_no_error_input_domain_required"
            )
            is True
            and claim_scope.get("input_domain") != SPECIALIZED_INPUT_DOMAIN
        ):
            failures.append(f"{label}.claim_scope input domain drift")

    by_relative = {
        item[0].get("path"): item
        for item in records.values()
        if isinstance(item[0].get("path"), str)
    }
    formal_parent = record[1].parent

    def bound_sibling(
        reference: object, expected_role: str, child_label: str
    ) -> tuple[dict[str, Any], Path, str] | None:
        if not isinstance(reference, dict):
            failures.append(f"{label}.{child_label} reference must be an object")
            return None
        relative = reference.get("path")
        digest = reference.get("sha256")
        if not isinstance(relative, str) or not relative:
            failures.append(f"{label}.{child_label}.path is invalid")
            return None
        candidate = (formal_parent / relative).resolve(strict=False)
        try:
            route_relative = candidate.relative_to(route.resolve()).as_posix()
        except ValueError:
            failures.append(f"{label}.{child_label} escapes the route")
            return None
        child_record = by_relative.get(route_relative)
        if child_record is None:
            failures.append(
                f"{label}.{child_label} is not bound by artifact_refs: {route_relative}"
            )
            return None
        if child_record[0].get("role") != expected_role:
            failures.append(
                f"{label}.{child_label} has role {child_record[0].get('role')}, expected {expected_role}"
            )
        if digest != child_record[2]:
            failures.append(f"{label}.{child_label} digest mismatch")
        return child_record

    for field, role, expected_binding_role in (
        (
            "source_artifact",
            "corpus-artifact",
            "original-source-analyzer-input",
        ),
        ("target_artifact", "target-artifact", "emitted-target-analyzer-input"),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        encoded = binding.get("content_base64")
        expected_digest = binding.get("sha256")
        expected_bytes = binding.get("byte_count")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, TypeError, ValueError):
            failures.append(f"{label}.{field}.content_base64 is invalid")
            decoded = b""
        if (
            not _is_int(expected_bytes, minimum=1)
            or len(decoded) != expected_bytes
            or sha256_bytes(decoded) != expected_digest
        ):
            failures.append(f"{label}.{field} embedded bytes do not match digest")
        child_record = bound_sibling(
            binding.get("content_reference"), role, f"{field}.content_reference"
        )
        if child_record is not None and child_record[1].read_bytes() != decoded:
            failures.append(f"{label}.{field} embedded/reference bytes differ")

    normalized_documents: dict[str, dict[str, Any]] = {}
    for field, role, expected_binding_role in (
        (
            "source_normalized_ir",
            "source-ir",
            "canonical-source-normalized-ir",
        ),
        (
            "target_relift_normalized_ir",
            "target-ir",
            "emitted-target-relift-normalized-ir",
        ),
    ):
        binding = document.get(field)
        if not isinstance(binding, dict):
            failures.append(f"{label}.{field} must be an object")
            continue
        if binding.get("role") != expected_binding_role:
            failures.append(f"{label}.{field}.role is invalid")
        child_record = bound_sibling(binding.get("artifact"), role, f"{field}.artifact")
        semantic_ir = binding.get("semantic_ir")
        formal_function = binding.get("formal_function")
        if not isinstance(semantic_ir, dict) or not isinstance(formal_function, dict):
            failures.append(f"{label}.{field} semantic IR/function is invalid")
            continue
        normalized_documents[field] = semantic_ir
        if child_record is not None:
            try:
                persisted_ir = load(child_record[1])
            except Exception as exc:
                failures.append(f"{label}.{field} persisted IR is invalid: {exc}")
            else:
                if persisted_ir != semantic_ir:
                    failures.append(f"{label}.{field} embedded/persisted IR differ")
        functions = semantic_ir.get("functions")
        if not isinstance(functions, list) or len(functions) != 1:
            failures.append(f"{label}.{field} must contain exactly one function")
        elif semantic_value(functions[0]) != formal_function:
            failures.append(f"{label}.{field} formal_function drift")
        if binding.get("semantic_ir_sha256") != canonical_json_sha256(semantic_ir):
            failures.append(f"{label}.{field} semantic_ir_sha256 mismatch")
        if binding.get("formal_function_sha256") != canonical_json_sha256(
            formal_function
        ):
            failures.append(f"{label}.{field} formal_function_sha256 mismatch")
    if semantic_value(
        normalized_documents.get("source_normalized_ir", {}).get("functions")
    ) != semantic_value(
        normalized_documents.get("target_relift_normalized_ir", {}).get("functions")
    ):
        failures.append(f"{label} source/target normalized functions differ")

    analyzer_identity = document.get("analyzer_identity")
    if not isinstance(analyzer_identity, dict):
        failures.append(f"{label}.analyzer_identity must be an object")
    else:
        for identity_field, ir_field, expected_language, expected_mode in (
            (
                "source",
                "source_normalized_ir",
                manifest.get("source", {}).get("language"),
                None,
            ),
            (
                "target_relift",
                "target_relift_normalized_ir",
                manifest.get("target", {}).get("language"),
                "emitted-target",
            ),
        ):
            identity = analyzer_identity.get(identity_field)
            semantic_ir = normalized_documents.get(ir_field, {})
            if (
                not isinstance(identity, dict)
                or identity.get("name") != semantic_ir.get("analyzer")
                or identity.get("version") != semantic_ir.get("analyzer_version")
                or identity.get("language") != expected_language
                or (expected_mode is not None and identity.get("mode") != expected_mode)
            ):
                failures.append(
                    f"{label}.analyzer_identity.{identity_field} differs from bound IR"
                )
    emitter_identity = document.get("emitter_identity")
    if (
        not isinstance(emitter_identity, dict)
        or emitter_identity.get("target_language")
        != manifest.get("target", {}).get("language")
        or not isinstance(emitter_identity.get("normalization_rules"), list)
        or not isinstance(emitter_identity.get("helper_digests"), list)
    ):
        failures.append(f"{label}.emitter_identity is invalid")

    implementation = document.get("implementation_identity")
    if not isinstance(implementation, dict):
        failures.append(f"{label}.implementation_identity must be an object")
    else:
        expected_files = {
            "engine": "src/elmos_polyglot_route/engine.py",
            "equivalence_encoder": "src/elmos_polyglot_route/equivalence.py",
            "emitter": "src/elmos_polyglot_route/emitter.py",
        }
        engine_records = [
            item for item in records.values() if item[0].get("role") == "engine-source"
        ]
        for identity, expected_suffix in expected_files.items():
            value = implementation.get(identity)
            if not isinstance(value, dict) or value.get("path") != expected_suffix:
                failures.append(
                    f"{label}.implementation_identity.{identity} is invalid"
                )
                continue
            matches = [
                item
                for item in engine_records
                if str(item[0].get("path", "")).endswith(
                    f"engines/polyglot-route-engine/{expected_suffix}"
                )
            ]
            if len(matches) != 1:
                failures.append(
                    f"{label}.implementation_identity.{identity} has no unique captured source"
                )
            elif (
                value.get("sha256") != matches[0][2]
                or value.get("byte_count") != matches[0][1].stat().st_size
            ):
                failures.append(
                    f"{label}.implementation_identity.{identity} digest/bytes drift"
                )

    assumptions = document.get("environment_assumptions")
    if (
        not isinstance(assumptions, list)
        or not assumptions
        or any(not isinstance(item, str) or not item for item in assumptions)
    ):
        failures.append(f"{label}.environment_assumptions must be non-empty")
    unsupported = document.get("unsupported_semantics")
    if (
        not isinstance(unsupported, list)
        or not unsupported
        or any(not isinstance(item, str) or not item for item in unsupported)
    ):
        failures.append(f"{label}.unsupported_semantics must be non-empty")
    solver = document.get("solver")
    if not isinstance(solver, dict):
        failures.append(f"{label}.solver must be an object")
    else:
        if solver.get("name") != proof.get("solver") or solver.get(
            "version"
        ) != proof.get("solver_version"):
            failures.append(f"{label}.solver identity differs from formal_proof")
        options = proof.get("solver_options")
        if isinstance(options, dict):
            for key in ("timeout_ms", "random_seed"):
                if solver.get(key) != options.get(key):
                    failures.append(f"{label}.solver {key} differs from formal_proof")
    return document


def _validate_optional_json_schema(
    data: dict[str, Any], schema_name: str, failures: list[str], label: str
) -> None:
    """Use jsonschema when the invoking environment provides it.

    Direct semantic validation below remains authoritative because the route CI
    intentionally runs with the standard-library Python interpreter as well as
    through the Batch 29 Make target that installs jsonschema.
    """

    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return
    schema = Path(__file__).resolve().parents[2] / "schemas" / "batch29" / schema_name
    try:
        jsonschema.Draft202012Validator(load(schema)).validate(data)
    except Exception as exc:
        failures.append(f"{label} schema validation failed: {exc}")


def validate_formal_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate strict evidence format v2 without upgrading its proof claim.

    The return value is consumed by the route gate. Structural validation here
    proves only that referenced bytes and reported counts are internally
    consistent; the gate separately decides whether those states can pass.
    """

    failures: list[str] = []
    evidence_format = certification.get("evidence_format")
    if evidence_format is not None and not _is_int(evidence_format, minimum=1):
        failures.append("certification evidence_format must be a positive integer")
    if not strict_evidence_requested(certification):
        return None, failures

    reference = certification.get("formal_equivalence")
    resolved = validate_artifact_ref(
        route,
        reference,
        "formal_equivalence",
        failures,
        require_identity=False,
    )
    if resolved is None:
        return None, failures
    evidence_path, _ = resolved
    try:
        evidence = load(evidence_path)
    except Exception as exc:
        failures.append(str(exc))
        return None, failures

    _validate_optional_json_schema(
        evidence,
        "formal-equivalence-evidence.schema.json",
        failures,
        "formal equivalence evidence",
    )
    top = _require_exact_keys(
        failures,
        evidence,
        required=FORMAL_REQUIRED_KEYS,
        label="formal equivalence evidence",
    )
    if top is None:
        return evidence, failures
    if top.get("schema_version") != 2:
        failures.append("formal equivalence schema_version must be 2")
    if top.get("route_key") != manifest.get("route_key"):
        failures.append("formal equivalence route_key mismatch")
    profile = manifest.get("profiles", {}).get("semantic_profile")
    if top.get("semantic_profile") != profile:
        failures.append("formal equivalence semantic_profile mismatch")

    route_manifest_digest = _require_digest(
        failures, top.get("route_manifest_sha256"), "route_manifest_sha256"
    )
    if route_manifest_digest is not None and route_manifest_digest != sha256_file(
        route / "route.json"
    ):
        failures.append("route_manifest_sha256 does not bind route.json")
    profile_digest = _require_digest(
        failures, top.get("semantic_profile_sha256"), "semantic_profile_sha256"
    )
    profile_path = route / "lowering" / "profile.json"
    if not profile_path.is_file():
        failures.append("semantic profile artifact is missing")
    elif profile_digest is not None and profile_digest != sha256_file(profile_path):
        failures.append("semantic_profile_sha256 does not bind lowering/profile.json")
    artifact_digest = _require_digest(
        failures, top.get("artifact_sha256"), "artifact_sha256"
    )
    environment_digest = _require_digest(
        failures, top.get("environment_sha256"), "environment_sha256"
    )

    artifact_refs = top.get("artifact_refs")
    ref_digests: set[str] = set()
    ref_paths: set[str] = set()
    ref_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    if not isinstance(artifact_refs, list) or not artifact_refs:
        failures.append("artifact_refs must be a non-empty array")
    else:
        for index, item in enumerate(artifact_refs):
            verified = validate_artifact_ref(
                route, item, f"artifact_refs[{index}]", failures
            )
            if not isinstance(item, dict):
                continue
            relative = item.get("path")
            if isinstance(relative, str):
                if relative in ref_paths:
                    failures.append(
                        f"artifact_refs contains duplicate path: {relative}"
                    )
                ref_paths.add(relative)
            if verified is not None:
                ref_digests.add(verified[1])
                artifact_id = item.get("artifact_id")
                if isinstance(artifact_id, str):
                    if artifact_id in ref_records:
                        failures.append(
                            f"artifact_refs contains duplicate artifact_id: {artifact_id}"
                        )
                    else:
                        ref_records[artifact_id] = (item, verified[0], verified[1])

    top_artifact_records: dict[str, tuple[dict[str, Any], Path, str]] = {}
    for label, artifact_id, digest, roles in (
        (
            "artifact",
            top.get("artifact_id"),
            artifact_digest,
            {"target-artifact"},
        ),
        (
            "environment",
            top.get("environment_artifact_id"),
            environment_digest,
            {"environment"},
        ),
    ):
        record = _artifact_record(
            ref_records,
            artifact_id,
            expected_roles=roles,
            label=f"{label}_artifact_id",
            failures=failures,
        )
        if record is not None and digest is not None and record[2] != digest:
            failures.append(
                f"{label}_sha256 does not match {label}_artifact_id {artifact_id}"
            )
        if record is not None:
            top_artifact_records[label] = record

    environment_document: dict[str, Any] | None = None
    environment_record = top_artifact_records.get("environment")
    if environment_record is not None:
        try:
            environment_document = load(environment_record[1])
        except Exception as exc:
            failures.append(f"environment artifact is invalid JSON: {exc}")
        else:
            if environment_document.get("route_key") != manifest.get("route_key"):
                failures.append("environment artifact route_key mismatch")
            if environment_document.get("independent_verification") != "NOT_RUN":
                failures.append(
                    "environment independent_verification must remain NOT_RUN"
                )
            if environment_document.get("external_certification") != "NOT_RUN":
                failures.append(
                    "environment external_certification must remain NOT_RUN"
                )
            source_manifest = environment_document.get("engine_source_manifest")
            if not isinstance(source_manifest, dict):
                failures.append("environment engine_source_manifest is missing")
            else:
                manifest_relative = source_manifest.get("path")
                manifest_record = next(
                    (
                        item
                        for item in ref_records.values()
                        if item[0].get("path") == manifest_relative
                    ),
                    None,
                )
                if (
                    manifest_record is None
                    or manifest_record[0].get("role") != "engine-source-manifest"
                ):
                    failures.append(
                        "environment engine_source_manifest is not role-bound"
                    )
                elif (
                    source_manifest.get("sha256") != manifest_record[2]
                    or source_manifest.get("bytes") != manifest_record[1].stat().st_size
                ):
                    failures.append(
                        "environment engine_source_manifest digest/bytes mismatch"
                    )
                else:
                    try:
                        source_manifest_document = load(manifest_record[1])
                    except Exception as exc:
                        failures.append(
                            f"engine source manifest is invalid JSON: {exc}"
                        )
                    else:
                        files = source_manifest_document.get("files")
                        if not isinstance(files, list) or not files:
                            failures.append("engine source manifest files are empty")
                        else:
                            declared_sources: set[str] = set()
                            live_repository_root = _replay_execution_root(route)
                            validate_live_sources = (
                                (live_repository_root / "engines").is_dir()
                                and (
                                    live_repository_root / "scripts" / "batch29"
                                ).is_dir()
                                and (
                                    live_repository_root / "schemas" / "batch29"
                                ).is_dir()
                            )
                            for index, item in enumerate(files):
                                if not isinstance(item, dict):
                                    failures.append(
                                        f"engine source manifest files[{index}] is invalid"
                                    )
                                    continue
                                repository_path = item.get("repository_path")
                                if (
                                    not isinstance(repository_path, str)
                                    or not repository_path
                                    or Path(repository_path).is_absolute()
                                    or "\\" in repository_path
                                    or any(
                                        part in {"", ".", ".."}
                                        for part in Path(repository_path).parts
                                    )
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}].repository_path is invalid"
                                    )
                                    repository_path = None
                                captured_path = item.get("captured_path")
                                declared_sources.add(str(captured_path))
                                captured_record = next(
                                    (
                                        record
                                        for record in ref_records.values()
                                        if record[0].get("path") == captured_path
                                    ),
                                    None,
                                )
                                if (
                                    captured_record is None
                                    or captured_record[0].get("role") != "engine-source"
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] is not role-bound"
                                    )
                                elif (
                                    item.get("sha256") != captured_record[2]
                                    or item.get("bytes")
                                    != captured_record[1].stat().st_size
                                ):
                                    failures.append(
                                        f"engine source manifest files[{index}] digest/bytes mismatch"
                                    )
                                if (
                                    validate_live_sources
                                    and repository_path is not None
                                ):
                                    live_path = (
                                        live_repository_root / repository_path
                                    ).resolve(strict=False)
                                    try:
                                        live_path.relative_to(live_repository_root)
                                    except ValueError:
                                        failures.append(
                                            f"engine source manifest files[{index}].repository_path escapes the repository"
                                        )
                                    else:
                                        if not live_path.is_file():
                                            failures.append(
                                                f"engine source manifest live file is missing: {repository_path}"
                                            )
                                        elif (
                                            item.get("sha256") != sha256_file(live_path)
                                            or item.get("bytes")
                                            != live_path.stat().st_size
                                        ):
                                            failures.append(
                                                f"engine source manifest live file drifted: {repository_path}"
                                            )
                            actual_sources = {
                                str(record[0].get("path"))
                                for record in ref_records.values()
                                if record[0].get("role") == "engine-source"
                            }
                            if declared_sources != actual_sources:
                                failures.append(
                                    "engine source manifest does not exactly cover engine-source artifacts"
                                )
                            if source_manifest_document.get("file_count") != len(files):
                                failures.append(
                                    "engine source manifest file_count mismatch"
                                )
                            lock_reference = environment_document.get(
                                "route_engine_lock"
                            )
                            if not isinstance(lock_reference, dict):
                                failures.append(
                                    "environment route_engine_lock is missing"
                                )
                            else:
                                lock_entries = [
                                    item
                                    for item in files
                                    if isinstance(item, dict)
                                    and item.get("repository_path")
                                    == lock_reference.get("path")
                                ]
                                if len(lock_entries) != 1 or lock_entries[0].get(
                                    "sha256"
                                ) != lock_reference.get("sha256"):
                                    failures.append(
                                        "environment route_engine_lock is not bound by engine source manifest"
                                    )

    semantic_ir = _require_exact_keys(
        failures,
        top.get("semantic_ir"),
        required=SEMANTIC_IR_KEYS,
        label="semantic_ir",
    )
    if semantic_ir is not None:
        if semantic_ir.get("status") not in LAYER_STATUSES:
            failures.append("semantic_ir.status is invalid")
        for id_field, digest_field, role in (
            ("source_ir_artifact_id", "source_ir_sha256", "source-ir"),
            ("target_ir_artifact_id", "target_relift_ir_sha256", "target-ir"),
        ):
            digest = _require_digest(
                failures, semantic_ir.get(digest_field), f"semantic_ir.{digest_field}"
            )
            record = _artifact_record(
                ref_records,
                semantic_ir.get(id_field),
                expected_roles={role},
                label=f"semantic_ir.{id_field}",
                failures=failures,
            )
            if record is not None and digest is not None and record[2] != digest:
                failures.append(f"semantic_ir.{digest_field} does not match {id_field}")
        if not _is_int(semantic_ir.get("unknown_or_dropped_nodes"), minimum=0):
            failures.append(
                "semantic_ir.unknown_or_dropped_nodes must be a non-negative integer"
            )
        _require_nonempty_strings(
            failures, semantic_ir.get("differences"), "semantic_ir.differences"
        )

    semantic_chunks = _require_exact_keys(
        failures,
        top.get("semantic_chunks"),
        required=SEMANTIC_CHUNK_KEYS,
        label="semantic_chunks",
    )
    if semantic_chunks is not None:
        if semantic_chunks.get("status") not in LAYER_STATUSES:
            failures.append("semantic_chunks.status is invalid")
        chunk_evidence_ids = semantic_chunks.get("evidence_artifact_ids")
        if not isinstance(chunk_evidence_ids, list) or not chunk_evidence_ids:
            failures.append(
                "semantic_chunks.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(chunk_evidence_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"chunk-map"},
                    label=f"semantic_chunks.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
        for field, minimum in (
            ("total", 1),
            ("matched", 0),
            ("unmatched", 0),
            ("ambiguous", 0),
        ):
            if not _is_int(semantic_chunks.get(field), minimum=minimum):
                failures.append(
                    f"semantic_chunks.{field} must be an integer >= {minimum}"
                )
        coverage = semantic_chunks.get("coverage")
        if not _is_number(coverage) or not 0 <= float(coverage) <= 1:
            failures.append("semantic_chunks.coverage must be between 0 and 1")
        chunks = semantic_chunks.get("chunks")
        ids: set[str] = set()
        observed = {"MATCHED": 0, "UNMATCHED": 0, "AMBIGUOUS": 0, "FAILED": 0}
        if not isinstance(chunks, list) or not chunks:
            failures.append("semantic_chunks.chunks must be a non-empty array")
        else:
            for index, item in enumerate(chunks):
                chunk = _require_exact_keys(
                    failures,
                    item,
                    required=CHUNK_KEYS,
                    label=f"semantic_chunks.chunks[{index}]",
                )
                if chunk is None:
                    continue
                chunk_id = chunk.get("chunk_id")
                if not isinstance(chunk_id, str) or not chunk_id:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].chunk_id is invalid"
                    )
                elif chunk_id in ids:
                    failures.append(f"semantic chunk id is duplicated: {chunk_id}")
                else:
                    ids.add(chunk_id)
                semantic_hash = _require_digest(
                    failures,
                    chunk.get("semantic_hash"),
                    f"semantic_chunks.chunks[{index}].semantic_hash",
                )
                source_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("source_ref"),
                    expected_role="source-ir",
                    label=f"semantic_chunks.chunks[{index}].source_ref",
                    failures=failures,
                )
                target_pointer = _artifact_pointer(
                    ref_records,
                    chunk.get("target_ref"),
                    expected_role="target-ir",
                    label=f"semantic_chunks.chunks[{index}].target_ref",
                    failures=failures,
                )
                if source_pointer is not None and target_pointer is not None:
                    if source_pointer[1] != target_pointer[1]:
                        failures.append(
                            f"semantic_chunks.chunks[{index}] source/target JSON pointers differ"
                        )
                    for pointer_label, pointer in (
                        ("source", source_pointer),
                        ("target", target_pointer),
                    ):
                        observed_hash = canonical_json_sha256(
                            semantic_value(pointer[2])
                        )
                        if semantic_hash is not None and observed_hash != semantic_hash:
                            failures.append(
                                f"semantic_chunks.chunks[{index}] {pointer_label} subtree hash mismatch"
                            )
                status = chunk.get("status")
                if status not in CHUNK_STATUSES:
                    failures.append(
                        f"semantic_chunks.chunks[{index}].status is invalid"
                    )
                else:
                    observed[status] += 1
            total = semantic_chunks.get("total")
            if _is_int(total, minimum=1) and total != len(chunks):
                failures.append("semantic_chunks.total does not equal chunks length")
            if (
                _is_int(semantic_chunks.get("matched"))
                and semantic_chunks.get("matched") != observed["MATCHED"]
            ):
                failures.append("semantic_chunks.matched does not match chunk statuses")
            if (
                _is_int(semantic_chunks.get("unmatched"))
                and semantic_chunks.get("unmatched") != observed["UNMATCHED"]
            ):
                failures.append(
                    "semantic_chunks.unmatched does not match chunk statuses"
                )
            if (
                _is_int(semantic_chunks.get("ambiguous"))
                and semantic_chunks.get("ambiguous") != observed["AMBIGUOUS"]
            ):
                failures.append(
                    "semantic_chunks.ambiguous does not match chunk statuses"
                )
            if _is_int(total, minimum=1) and _is_number(coverage):
                expected_coverage = observed["MATCHED"] / total
                if abs(float(coverage) - expected_coverage) > 1e-12:
                    failures.append(
                        "semantic_chunks.coverage does not equal matched / total"
                    )
        expected_chunk_rows: set[tuple[str, str, str, str, str]] = set()
        if isinstance(chunk_evidence_ids, list):
            for artifact_id in chunk_evidence_ids:
                chunk_record = ref_records.get(artifact_id)
                if chunk_record is None:
                    continue
                try:
                    chunk_document = load(chunk_record[1])
                except Exception as exc:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} is invalid JSON: {exc}"
                    )
                    continue
                if chunk_document.get("status") != "PASSED":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} did not pass"
                    )
                if chunk_document.get("path_scheme") != "rfc6901-json-pointer-v1":
                    failures.append(
                        f"semantic chunk artifact {artifact_id} does not use RFC6901 pointers"
                    )
                mappings = chunk_document.get("mappings")
                if not isinstance(mappings, list) or not mappings:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} has no mappings"
                    )
                    continue
                parent = chunk_record[1].parent
                source_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "source-ir"
                    and record[1].parent == parent
                ]
                target_candidates = [
                    (candidate_id, record)
                    for candidate_id, record in ref_records.items()
                    if record[0].get("role") == "target-ir"
                    and record[1].parent == parent
                ]
                if len(source_candidates) != 1 or len(target_candidates) != 1:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} must have one sibling source IR and target IR"
                    )
                    continue
                source_artifact_id = source_candidates[0][0]
                target_artifact_id = target_candidates[0][0]
                source_semantic_function = None
                target_semantic_function = None
                for side, candidate, destination in (
                    ("source", source_candidates[0][1], "source"),
                    ("target", target_candidates[0][1], "target"),
                ):
                    try:
                        semantic_document = load(candidate[1])
                        semantic_functions = semantic_document.get("functions")
                    except Exception as exc:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} {side} IR is invalid: {exc}"
                        )
                        continue
                    if not isinstance(semantic_functions, list) or len(semantic_functions) != 1:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} {side} IR must contain one function"
                        )
                        continue
                    if destination == "source":
                        source_semantic_function = semantic_functions[0]
                    else:
                        target_semantic_function = semantic_functions[0]
                for mapping_index, mapping in enumerate(mappings):
                    if (
                        not isinstance(mapping, dict)
                        or mapping.get("status") != "EXACT"
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is not EXACT"
                        )
                        continue
                    pointer = mapping.get("semantic_path")
                    semantic_hash = mapping.get("semantic_hash")
                    source_chunk_id = mapping.get("source_chunk_id")
                    target_chunk_id = mapping.get("target_chunk_id")
                    source_artifact_pointer = mapping.get("source_artifact_pointer")
                    target_artifact_pointer = mapping.get("target_artifact_pointer")
                    if not all(
                        isinstance(item, str) and item
                        for item in (
                            pointer,
                            semantic_hash,
                            source_chunk_id,
                            target_chunk_id,
                            source_artifact_pointer,
                            target_artifact_pointer,
                        )
                    ):
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} is incomplete"
                        )
                        continue
                    for pointer_label, artifact_pointer, expected_roles in (
                        (
                            "source_artifact_pointer",
                            source_artifact_pointer,
                            {"corpus-artifact"},
                        ),
                        (
                            "target_artifact_pointer",
                            target_artifact_pointer,
                            {"target-artifact"},
                        ),
                    ):
                        if artifact_pointer.count("#") != 1:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} is invalid"
                            )
                            continue
                        artifact_digest, artifact_json_pointer = artifact_pointer.split(
                            "#", 1
                        )
                        if artifact_json_pointer != pointer:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} pointer drift"
                            )
                        matches = [
                            record
                            for record in ref_records.values()
                            if record[2] == artifact_digest
                            and record[0].get("role") in expected_roles
                            and (
                                pointer_label != "target_artifact_pointer"
                                or record[1].parent == parent
                            )
                        ]
                        if not matches:
                            failures.append(
                                f"semantic chunk artifact {artifact_id} mapping {mapping_index} {pointer_label} digest is not role-bound"
                            )
                    expected_source_chunk_id = sha256_bytes(
                        (
                            f"{source_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    expected_target_chunk_id = sha256_bytes(
                        (
                            f"{target_artifact_pointer.split('#', 1)[0]}\0{pointer}\0{semantic_hash}"
                        ).encode("utf-8")
                    )
                    if source_chunk_id != expected_source_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} source_chunk_id drift"
                        )
                    if target_chunk_id != expected_target_chunk_id:
                        failures.append(
                            f"semantic chunk artifact {artifact_id} mapping {mapping_index} target_chunk_id drift"
                        )
                    expected_chunk_rows.add(
                        (
                            f"{parent.name}:{source_chunk_id}",
                            f"{source_artifact_id}#{pointer}",
                            f"{target_artifact_id}#{pointer}",
                            semantic_hash,
                            "MATCHED",
                        )
                    )
                required = chunk_document.get("required_source_chunk_count")
                mapped = chunk_document.get("mapped_source_chunk_count")
                if required != len(mappings) or mapped != len(mappings):
                    failures.append(
                        f"semantic chunk artifact {artifact_id} count fields do not match mappings"
                    )
                if chunk_document.get("coverage") != 1.0:
                    failures.append(
                        f"semantic chunk artifact {artifact_id} coverage is not 1.0"
                    )
                if manifest.get("gates", {}).get("concrete_spans_required") is True:
                    span_validation = chunk_document.get("span_validation")
                    source_digest = (
                        span_validation.get("source", {}).get("artifact_sha256")
                        if isinstance(span_validation, dict)
                        and isinstance(span_validation.get("source"), dict)
                        else None
                    )
                    target_digest = (
                        span_validation.get("target", {}).get("artifact_sha256")
                        if isinstance(span_validation, dict)
                        and isinstance(span_validation.get("target"), dict)
                        else None
                    )
                    source_record = next(
                        (
                            record
                            for record in ref_records.values()
                            if record[2] == source_digest
                            and record[0].get("role") == "corpus-artifact"
                        ),
                        None,
                    )
                    target_record = next(
                        (
                            record
                            for record in ref_records.values()
                            if record[2] == target_digest
                            and record[0].get("role") == "target-artifact"
                        ),
                        None,
                    )
                    _validate_concrete_chunk_document(
                        chunk_document,
                        label=f"semantic chunk artifact {artifact_id}",
                        failures=failures,
                        source_record=source_record,
                        target_record=target_record,
                        source_function=source_semantic_function,
                        target_function=target_semantic_function,
                    )
        if isinstance(chunks, list):
            actual_chunk_rows = {
                (
                    item.get("chunk_id"),
                    item.get("source_ref"),
                    item.get("target_ref"),
                    item.get("semantic_hash"),
                    item.get("status"),
                )
                for item in chunks
                if isinstance(item, dict)
            }
            if actual_chunk_rows != expected_chunk_rows:
                failures.append(
                    "semantic_chunks.chunks do not exactly match bound chunk-map artifacts"
                )

    behavior = _require_exact_keys(
        failures,
        top.get("behavior_equivalence"),
        required=BEHAVIOR_KEYS,
        label="behavior_equivalence",
    )
    if behavior is not None:
        if behavior.get("status") not in LAYER_STATUSES:
            failures.append("behavior_equivalence.status is invalid")
        behavior_artifact_ids = behavior.get("evidence_artifact_ids")
        observed_behavior_documents: list[dict[str, Any]] = []
        if not isinstance(behavior_artifact_ids, list) or not behavior_artifact_ids:
            failures.append(
                "behavior_equivalence.evidence_artifact_ids must be a non-empty array"
            )
        else:
            for index, artifact_id in enumerate(behavior_artifact_ids):
                record = _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.evidence_artifact_ids[{index}]",
                    failures=failures,
                )
                if record is None:
                    continue
                try:
                    document = load(record[1])
                except Exception as exc:
                    failures.append(
                        f"behavior artifact {artifact_id} is not valid JSON: {exc}"
                    )
                else:
                    observed_behavior_documents.append(document)
        for field in (
            "source_runtime_artifact_ids",
            "target_runtime_artifact_ids",
        ):
            runtime_ids = behavior.get(field)
            if not isinstance(runtime_ids, list) or not runtime_ids:
                failures.append(f"behavior_equivalence.{field} must be non-empty")
                continue
            for index, artifact_id in enumerate(runtime_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"behavior-result"},
                    label=f"behavior_equivalence.{field}[{index}]",
                    failures=failures,
                )
                if (
                    isinstance(behavior_artifact_ids, list)
                    and artifact_id not in behavior_artifact_ids
                ):
                    failures.append(
                        f"behavior_equivalence.{field}[{index}] is absent from evidence_artifact_ids"
                    )
        total_cases = behavior.get("total_cases")
        passed_cases = behavior.get("passed_cases")
        if not _is_int(total_cases, minimum=1):
            failures.append(
                "behavior_equivalence.total_cases must be a positive integer"
            )
        if not _is_int(passed_cases, minimum=0):
            failures.append(
                "behavior_equivalence.passed_cases must be a non-negative integer"
            )
        elif _is_int(total_cases, minimum=1) and passed_cases > total_cases:
            failures.append("behavior_equivalence.passed_cases exceeds total_cases")
        for field in (
            "canonical_oracle_passed",
            "source_runtime_passed",
            "target_runtime_passed",
        ):
            if not isinstance(behavior.get(field), bool):
                failures.append(f"behavior_equivalence.{field} must be boolean")
        counterexamples = behavior.get("counterexamples")
        if not isinstance(counterexamples, list):
            failures.append("behavior_equivalence.counterexamples must be an array")
        else:
            case_ids: set[str] = set()
            for index, item in enumerate(counterexamples):
                counterexample = _require_exact_keys(
                    failures,
                    item,
                    required=COUNTEREXAMPLE_REQUIRED_KEYS,
                    allowed=COUNTEREXAMPLE_ALLOWED_KEYS,
                    label=f"behavior_equivalence.counterexamples[{index}]",
                )
                if counterexample is None:
                    continue
                case_id = counterexample.get("case_id")
                reason = counterexample.get("reason")
                if not isinstance(case_id, str) or not case_id:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].case_id is invalid"
                    )
                elif case_id in case_ids:
                    failures.append(
                        f"behavior counterexample id is duplicated: {case_id}"
                    )
                else:
                    case_ids.add(case_id)
                if not isinstance(reason, str) or not reason:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].reason is invalid"
                    )
                evidence_ref = counterexample.get("evidence_ref")
                if evidence_ref is not None and evidence_ref not in ref_paths:
                    failures.append(
                        f"behavior_equivalence.counterexamples[{index}].evidence_ref is not in artifact_refs"
                    )
            if _is_int(total_cases, minimum=1) and _is_int(passed_cases):
                if total_cases - passed_cases != len(counterexamples):
                    failures.append(
                        "behavior counterexample count must equal total_cases - passed_cases"
                    )
        if observed_behavior_documents:
            observed_counts: list[tuple[int, int]] = []
            for index, item in enumerate(observed_behavior_documents):
                case_count = item.get("case_count")
                pass_count = item.get("pass_count")
                if not _is_int(case_count, minimum=1) or not _is_int(
                    pass_count, minimum=0
                ):
                    failures.append(
                        f"behavior artifact {index} has invalid case/pass counts"
                    )
                    continue
                observed_counts.append((case_count, pass_count))
            observed_total = sum(item[0] for item in observed_counts)
            observed_passed = sum(item[1] for item in observed_counts)
            if observed_total != total_cases:
                failures.append(
                    "behavior_equivalence.total_cases does not match behavior artifacts"
                )
            if observed_passed != passed_cases:
                failures.append(
                    "behavior_equivalence.passed_cases does not match behavior artifacts"
                )
            observed_oracle = all(
                item.get("oracle_conflict_count") == 0
                for item in observed_behavior_documents
            )
            observed_source = all(
                item.get("source_runtime_passed") is True
                for item in observed_behavior_documents
            )
            observed_target = all(
                item.get("target_runtime_passed") is True
                for item in observed_behavior_documents
            )
            for field, observed in (
                ("canonical_oracle_passed", observed_oracle),
                ("source_runtime_passed", observed_source),
                ("target_runtime_passed", observed_target),
            ):
                if behavior.get(field) is not observed:
                    failures.append(
                        f"behavior_equivalence.{field} does not match behavior artifacts"
                    )

    formal_proof = _require_exact_keys(
        failures,
        top.get("formal_proof"),
        required=FORMAL_PROOF_KEYS,
        label="formal_proof",
    )
    if formal_proof is not None:
        status = formal_proof.get("status")
        if status not in PROOF_STATUSES:
            failures.append("formal_proof.status is invalid")
        for field in ("solver", "solver_version"):
            if not isinstance(formal_proof.get(field), str) or not formal_proof.get(
                field
            ):
                failures.append(f"formal_proof.{field} must be a non-empty string")
        if isinstance(environment_document, dict):
            environment_solver = environment_document.get("solver")
            if (
                not isinstance(environment_solver, dict)
                or environment_solver.get("name") != formal_proof.get("solver")
                or environment_solver.get("version")
                != formal_proof.get("solver_version")
            ):
                failures.append(
                    "formal_proof solver identity differs from environment artifact"
                )
        options = formal_proof.get("solver_options")
        if not isinstance(options, dict) or not options:
            failures.append("formal_proof.solver_options must be a non-empty object")
        elif any(
            not isinstance(value, str | int | float | bool)
            for value in options.values()
        ):
            failures.append("formal_proof.solver_options contains a non-scalar value")
        input_digest = _require_digest(
            failures, formal_proof.get("input_digest"), "formal_proof.input_digest"
        )
        proof_input_record = _artifact_record(
            ref_records,
            formal_proof.get("input_artifact_id"),
            expected_roles={"proof-input-bundle"},
            label="formal_proof.input_artifact_id",
            failures=failures,
        )
        if (
            proof_input_record is not None
            and input_digest is not None
            and proof_input_record[2] != input_digest
        ):
            failures.append(
                "formal_proof.input_digest does not match input_artifact_id"
            )
        result_artifact_ids = formal_proof.get("result_artifact_ids")
        if not isinstance(result_artifact_ids, list) or not result_artifact_ids:
            failures.append("formal_proof.result_artifact_ids must be non-empty")
        else:
            for index, artifact_id in enumerate(result_artifact_ids):
                _artifact_record(
                    ref_records,
                    artifact_id,
                    expected_roles={"solver-result"},
                    label=f"formal_proof.result_artifact_ids[{index}]",
                    failures=failures,
                )
        assumptions = _require_nonempty_strings(
            failures, formal_proof.get("assumptions"), "formal_proof.assumptions"
        )
        obligations = formal_proof.get("obligations")
        obligation_statuses: list[str] = []
        obligation_ids: set[str] = set()
        obligation_formal_input_ids: set[str] = set()
        obligation_solver_input_ids: set[str] = set()
        obligation_solver_result_ids: set[str] = set()
        obligation_assumption_union: set[str] = set()
        if not isinstance(obligations, list) or not obligations:
            failures.append("formal_proof.obligations must be a non-empty array")
        else:
            for index, item in enumerate(obligations):
                obligation = _require_exact_keys(
                    failures,
                    item,
                    required=OBLIGATION_REQUIRED_KEYS,
                    allowed=OBLIGATION_ALLOWED_KEYS,
                    label=f"formal_proof.obligations[{index}]",
                )
                if obligation is None:
                    continue
                obligation_id = obligation.get("obligation_id")
                if not isinstance(obligation_id, str) or not obligation_id:
                    failures.append(
                        f"formal_proof.obligations[{index}].obligation_id is invalid"
                    )
                elif obligation_id in obligation_ids:
                    failures.append(
                        f"formal proof obligation id is duplicated: {obligation_id}"
                    )
                else:
                    obligation_ids.add(obligation_id)
                obligation_status = obligation.get("status")
                if obligation_status not in PROOF_STATUSES:
                    failures.append(
                        f"formal_proof.obligations[{index}].status is invalid"
                    )
                else:
                    obligation_statuses.append(obligation_status)
                if not isinstance(obligation.get("scope"), str) or not obligation.get(
                    "scope"
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].scope is invalid"
                    )
                obligation_digest = _require_digest(
                    failures,
                    obligation.get("input_digest"),
                    f"formal_proof.obligations[{index}].input_digest",
                )
                formal_input_record = _artifact_record(
                    ref_records,
                    obligation.get("formal_input_artifact_id"),
                    expected_roles={"formal-input"},
                    label=f"formal_proof.obligations[{index}].formal_input_artifact_id",
                    failures=failures,
                )
                for field_name, destination in (
                    ("formal_input_artifact_id", obligation_formal_input_ids),
                    ("solver_input_artifact_id", obligation_solver_input_ids),
                    ("solver_result_artifact_id", obligation_solver_result_ids),
                ):
                    value = obligation.get(field_name)
                    if isinstance(value, str):
                        destination.add(value)
                solver_input_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_input_artifact_id"),
                    expected_roles={"solver-input"},
                    label=f"formal_proof.obligations[{index}].solver_input_artifact_id",
                    failures=failures,
                )
                solver_result_record = _artifact_record(
                    ref_records,
                    obligation.get("solver_result_artifact_id"),
                    expected_roles={"solver-result"},
                    label=f"formal_proof.obligations[{index}].solver_result_artifact_id",
                    failures=failures,
                )
                formal_input_document = None
                if formal_input_record is not None:
                    formal_input_document = _validate_formal_input_document(
                        route,
                        formal_input_record,
                        ref_records,
                        manifest,
                        formal_proof,
                        f"formal_proof.obligations[{index}].formal_input",
                        failures,
                    )
                    environment_assumptions = (
                        formal_input_document.get("environment_assumptions")
                        if isinstance(formal_input_document, dict)
                        else None
                    )
                    obligation_assumptions = obligation.get("assumptions")
                    if (
                        isinstance(environment_assumptions, list)
                        and isinstance(obligation_assumptions, list)
                        and not set(environment_assumptions).issubset(
                            set(obligation_assumptions)
                        )
                    ):
                        failures.append(
                            f"formal_proof.obligations[{index}] omits formal-input assumptions"
                        )
                if (
                    solver_input_record is not None
                    and obligation_digest is not None
                    and solver_input_record[2] != obligation_digest
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}].input_digest does not match solver_input_artifact_id"
                    )
                if (
                    isinstance(result_artifact_ids, list)
                    and obligation.get("solver_result_artifact_id")
                    not in result_artifact_ids
                ):
                    failures.append(
                        f"formal_proof.obligations[{index}] result is absent from formal_proof.result_artifact_ids"
                    )
                if formal_input_record is not None and solver_input_record is not None:
                    try:
                        solver_input_text = solver_input_record[1].read_text(
                            encoding="utf-8"
                        )
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver input is unreadable: {exc}"
                        )
                    else:
                        if formal_input_record[2] not in solver_input_text:
                            failures.append(
                                f"formal_proof.obligations[{index}] SMT input does not bind formal input"
                            )
                if formal_input_record is not None and solver_result_record is not None:
                    try:
                        result_document = load(solver_result_record[1])
                    except Exception as exc:
                        failures.append(
                            f"formal_proof.obligations[{index}] solver result is invalid JSON: {exc}"
                        )
                    else:
                        formal_input_digest = formal_input_record[2]
                        declared_formal_input_digest = result_document.get(
                            "formal_input_digest"
                        )
                        if declared_formal_input_digest != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind formal input"
                            )
                        if result_document.get("input_digest") != formal_input_digest:
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input_digest differs from formal input"
                            )
                        formal_input_reference = result_document.get("formal_input")
                        expected_formal_input_path = formal_input_record[1].name
                        if (
                            not isinstance(formal_input_reference, dict)
                            or formal_input_reference.get("path")
                            != expected_formal_input_path
                            or formal_input_reference.get("sha256")
                            != formal_input_digest
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result formal_input reference drift"
                            )
                        declared_solver_input_digest = result_document.get(
                            "solver_input_digest"
                        )
                        if (
                            solver_input_record is not None
                            and declared_solver_input_digest != solver_input_record[2]
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result does not bind SMT input"
                            )
                        result_status = result_document.get("status")
                        if result_status != obligation_status:
                            failures.append(
                                f"formal_proof.obligations[{index}] status does not match solver result"
                            )
                        if (
                            manifest.get("gates", {}).get(
                                "canonical_finite_no_error_input_domain_required"
                            )
                            is True
                            and (
                                not isinstance(
                                    result_document.get("claim_scope"), dict
                                )
                                or result_document["claim_scope"].get("input_domain")
                                != SPECIALIZED_INPUT_DOMAIN
                            )
                        ):
                            failures.append(
                                f"formal_proof.obligations[{index}] solver result input domain drift"
                            )
                        if (
                            isinstance(formal_input_document, dict)
                            and solver_input_record is not None
                            and manifest.get("gates", {}).get(
                                "canonical_finite_no_error_input_domain_required"
                            )
                            is True
                        ):
                            _validate_function_formal_closure(
                                label=f"formal_proof.obligations[{index}]",
                                manifest=manifest,
                                formal_input=formal_input_document,
                                formal_input_record=formal_input_record,
                                solver_input_record=solver_input_record,
                                solver_result=result_document,
                                failures=failures,
                            )
                _require_nonempty_strings(
                    failures,
                    obligation.get("assumptions"),
                    f"formal_proof.obligations[{index}].assumptions",
                )
                if isinstance(obligation.get("assumptions"), list):
                    obligation_assumption_union.update(obligation["assumptions"])

        if (
            isinstance(result_artifact_ids, list)
            and set(result_artifact_ids) != obligation_solver_result_ids
        ):
            failures.append(
                "formal_proof.result_artifact_ids do not exactly match obligations"
            )
        if (
            isinstance(assumptions, list)
            and set(assumptions) != obligation_assumption_union
        ):
            failures.append(
                "formal_proof.assumptions do not equal the obligation assumption union"
            )

        if proof_input_record is not None:
            try:
                proof_bundle = load(proof_input_record[1])
            except Exception as exc:
                failures.append(f"formal proof input bundle is invalid JSON: {exc}")
            else:
                if proof_bundle.get("route_key") != manifest.get("route_key"):
                    failures.append("formal proof input bundle route_key mismatch")
                if proof_bundle.get("same_input_required") is not True:
                    failures.append(
                        "formal proof input bundle must require same-input composition"
                    )
                runs = proof_bundle.get("runs")
                observed_bundle_ids: dict[str, set[str]] = {
                    "formal_input": set(),
                    "smt2": set(),
                    "result": set(),
                }
                if not isinstance(runs, list) or not runs:
                    failures.append("formal proof input bundle runs are empty")
                else:
                    corpora: set[str] = set()
                    by_relative = {
                        record[0].get("path"): (artifact_id, record)
                        for artifact_id, record in ref_records.items()
                    }
                    for run_index, run in enumerate(runs):
                        if not isinstance(run, dict):
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] is invalid"
                            )
                            continue
                        corpus = run.get("corpus")
                        if not isinstance(corpus, str) or corpus in corpora:
                            failures.append(
                                f"formal proof input bundle runs[{run_index}] corpus is invalid/duplicate"
                            )
                        else:
                            corpora.add(corpus)
                        for field, roles in (
                            ("formal_input", {"formal-input"}),
                            ("smt2", {"solver-input"}),
                            ("result", {"solver-result"}),
                            ("composition", {"formal-composition"}),
                        ):
                            reference = run.get(field)
                            if not isinstance(reference, dict):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is invalid"
                                )
                                continue
                            relative = reference.get("path")
                            bound = by_relative.get(relative)
                            if bound is None or bound[1][0].get("role") not in roles:
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} is not role-bound"
                                )
                                continue
                            if (
                                reference.get("sha256") != bound[1][2]
                                or reference.get("bytes") != bound[1][1].stat().st_size
                            ):
                                failures.append(
                                    f"formal proof input bundle runs[{run_index}].{field} digest/bytes mismatch"
                                )
                            if field in observed_bundle_ids:
                                observed_bundle_ids[field].add(bound[0])
                    expected_bundle_ids = {
                        "formal_input": obligation_formal_input_ids,
                        "smt2": obligation_solver_input_ids,
                        "result": obligation_solver_result_ids,
                    }
                    for field, expected_ids in expected_bundle_ids.items():
                        if observed_bundle_ids[field] != expected_ids:
                            failures.append(
                                f"formal proof input bundle {field} set does not match obligations"
                            )

        if status == "PROVED":
            if any(item != "PROVED" for item in obligation_statuses):
                failures.append(
                    "formal_proof PROVED requires every obligation to be PROVED"
                )
            if assumptions:
                failures.append("formal_proof PROVED cannot carry assumptions")
            if isinstance(obligations, list) and any(
                item.get("assumptions")
                for item in obligations
                if isinstance(item, dict)
            ):
                failures.append("PROVED obligations cannot carry assumptions")
        elif status == "PROVED_UNDER_ASSUMPTIONS":
            if not assumptions:
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS requires explicit assumptions"
                )
            if any(
                item not in {"PROVED", "PROVED_UNDER_ASSUMPTIONS"}
                for item in obligation_statuses
            ):
                failures.append(
                    "PROVED_UNDER_ASSUMPTIONS cannot contain unresolved obligations"
                )
        elif status == "AXIOM" and not assumptions:
            failures.append("AXIOM evidence requires explicit assumptions")
        if status in PROOF_STATUSES and obligation_statuses:
            precedence = (
                "COUNTEREXAMPLE",
                "TIMEOUT",
                "UNKNOWN",
                "NOT_RUN",
                "BOUNDED",
                "AXIOM",
                "PROVED_UNDER_ASSUMPTIONS",
                "PROVED",
            )
            derived = next(item for item in precedence if item in obligation_statuses)
            if status != derived:
                failures.append(
                    f"formal_proof.status {status} does not match obligation aggregate {derived}"
                )

        replay = _require_exact_keys(
            failures,
            formal_proof.get("replay"),
            required=REPLAY_KEYS,
            label="formal_proof.replay",
        )
        if replay is not None:
            command = replay.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(item, str) or not item for item in command)
            ):
                failures.append(
                    "formal_proof.replay.command must be a non-empty argv array"
                )
            cwd = _resolve_below(
                route, replay.get("cwd"), "formal_proof.replay.cwd", failures
            )
            if cwd is not None and not cwd.is_dir():
                failures.append("formal_proof.replay.cwd is not an existing directory")
            if (
                cwd is not None
                and cwd.is_dir()
                and isinstance(command, list)
                and command
            ):
                _validate_replay_command(
                    route=route,
                    manifest=manifest,
                    command=command,
                    cwd=cwd,
                    records=ref_records,
                    failures=failures,
                )
            if replay.get("expected_exit_code") != 0:
                failures.append("formal_proof.replay.expected_exit_code must be zero")
            replay_result_digest = _require_digest(
                failures,
                replay.get("expected_result_sha256"),
                "formal_proof.replay.expected_result_sha256",
            )
            replay_result = _artifact_record(
                ref_records,
                replay.get("expected_result_artifact_id"),
                expected_roles={"solver-result"},
                label="formal_proof.replay.expected_result_artifact_id",
                failures=failures,
            )
            if (
                replay_result is not None
                and replay_result_digest is not None
                and replay_result[2] != replay_result_digest
            ):
                failures.append(
                    "formal_proof.replay expected result digest does not match artifact"
                )

    return evidence, failures


def validate_module_equivalence(
    route: Path,
    manifest: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate module composition evidence without turning NOT_RUN into pass."""

    failures: list[str] = []
    gates = manifest.get("gates", {})
    required = gates.get("module_equivalence_required") is True
    minimum_functions = gates.get("minimum_module_functions", 3)
    if not _is_int(minimum_functions, minimum=3):
        failures.append("minimum_module_functions must be an integer >= 3")
        minimum_functions = 3
    reference = certification.get("module_equivalence")
    if reference is None:
        if required:
            failures.append("required module_equivalence evidence is missing")
        return None, failures
    resolved = validate_artifact_ref(
        route,
        reference,
        "module_equivalence",
        failures,
        require_identity=False,
    )
    if resolved is None:
        return None, failures
    evidence_path, _ = resolved
    try:
        evidence = load(evidence_path)
    except Exception as exc:
        failures.append(f"module equivalence evidence is invalid JSON: {exc}")
        return None, failures
    _validate_optional_json_schema(
        evidence,
        "module-equivalence-evidence.schema.json",
        failures,
        "module equivalence evidence",
    )
    route_scope = evidence.get("route")
    expected_route_scope = {
        "route_key": manifest.get("route_key"),
        "source_language": manifest.get("source", {}).get("language"),
        "target_language": manifest.get("target", {}).get("language"),
    }
    if route_scope != expected_route_scope:
        failures.append("module equivalence route tuple does not match route.json")
    if evidence.get("profile") != manifest.get("profiles", {}).get("module_profile"):
        failures.append("module equivalence profile does not match route.json")
    if evidence.get("certification_status") != "NOT_CERTIFIED":
        failures.append("module equivalence must remain NOT_CERTIFIED")
    if evidence.get("external_verification_status") != "NOT_RUN":
        failures.append("module equivalence external verification must remain NOT_RUN")

    artifact_refs = evidence.get("artifact_refs")
    artifacts_by_path: dict[str, tuple[dict[str, Any], Path, str]] = {}
    if not isinstance(artifact_refs, list):
        failures.append("module artifact_refs must be an array")
        artifact_refs = []
    for index, item in enumerate(artifact_refs):
        if not isinstance(item, dict):
            failures.append(f"module artifact_refs[{index}] must be an object")
            continue
        relative = item.get("path")
        role = item.get("role")
        digest = _require_digest(
            failures, item.get("sha256"), f"module artifact_refs[{index}].sha256"
        )
        size = item.get("bytes")
        path = _resolve_below(
            route, relative, f"module artifact_refs[{index}].path", failures
        )
        if path is None:
            continue
        if not path.is_file() or path.is_symlink():
            failures.append(f"module artifact_refs[{index}] is not a regular file")
            continue
        if not _is_int(size, minimum=1) or path.stat().st_size != size:
            failures.append(f"module artifact_refs[{index}] byte count mismatch")
        observed = sha256_file(path)
        if digest is not None and observed != digest:
            failures.append(f"module artifact_refs[{index}] digest mismatch")
        if not isinstance(relative, str):
            continue
        if relative in artifacts_by_path:
            failures.append(f"duplicate module artifact path: {relative}")
        else:
            artifacts_by_path[relative] = (item, path, observed)
        if role not in MODULE_ARTIFACT_ROLES:
            failures.append(f"module artifact_refs[{index}] role is invalid")

    module_input_digest = None
    if evidence.get("status") == "PASSED":
        module_input_digest = _require_digest(
            failures, evidence.get("module_input_sha256"), "module_input_sha256"
        )
    module_inputs = [
        item for item in artifacts_by_path.values() if item[0].get("role") == "module-formal-input"
    ]
    role_records: dict[str, list[tuple[dict[str, Any], Path, str]]] = {}
    for record in artifacts_by_path.values():
        role_records.setdefault(str(record[0].get("role")), []).append(record)
    module_cases: dict[str, Any] = {}
    source_validation_document: dict[str, Any] = {}
    target_validation_document: dict[str, Any] = {}
    source_observation_document: dict[str, Any] = {}
    target_observation_document: dict[str, Any] = {}
    source_semantic_document: dict[str, Any] = {}
    target_semantic_document: dict[str, Any] = {}
    if evidence.get("status") == "PASSED":
        if len(module_inputs) != 1:
            failures.append("passed module evidence must bind exactly one module formal input")
        elif module_input_digest is not None and module_inputs[0][2] != module_input_digest:
            failures.append("module_input_sha256 does not bind module-formal-input")
        module_input = evidence.get("module_input")
        if not isinstance(module_input, dict):
            failures.append("passed module evidence must include module_input")
        else:
            if canonical_json_sha256(module_input) != module_input_digest:
                failures.append("module_input_sha256 is not the canonical module_input digest")
            if module_inputs:
                try:
                    persisted_module_input = load(module_inputs[0][1])
                except Exception as exc:
                    failures.append(f"module-formal-input is invalid JSON: {exc}")
                else:
                    if persisted_module_input != module_input:
                        failures.append("module-formal-input differs from module_input")

            single_roles = MODULE_ARTIFACT_ROLES - {
                "formal-function-input",
                "formal-function-smt2",
                "formal-function-result",
            }
            for role in sorted(single_roles):
                if len(role_records.get(role, [])) != 1:
                    failures.append(f"passed module evidence must bind exactly one {role}")
            input_bindings = (
                ("original-source-module-artifact", "source_artifact_sha256"),
                ("emitted-target-module-artifact", "target_artifact_sha256"),
                ("module-case-manifest", "corpus_sha256"),
            )
            for role, field in input_bindings:
                records = role_records.get(role, [])
                if len(records) == 1 and module_input.get(field) != records[0][2]:
                    failures.append(f"module_input.{field} does not bind {role}")
            if module_input.get("route") != {
                "source_language": manifest.get("source", {}).get("language"),
                "target_language": manifest.get("target", {}).get("language"),
            }:
                failures.append("module_input route tuple does not match route.json")
            if module_input.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                failures.append("module_input input domain drift")
            source_records = role_records.get("original-source-module-artifact", [])
            if len(source_records) == 1 and module_input.get(
                "source_logical_file"
            ) != source_records[0][1].name:
                failures.append("module_input source_logical_file drift")
            target_records = role_records.get("emitted-target-module-artifact", [])
            if len(target_records) == 1 and module_input.get(
                "target_logical_file"
            ) != target_records[0][1].name:
                failures.append("module_input target_logical_file drift")
            count_bindings = (
                ("original-source-module-artifact", "source_artifact_byte_count"),
                ("emitted-target-module-artifact", "target_artifact_byte_count"),
            )
            for role, field in count_bindings:
                records = role_records.get(role, [])
                if len(records) == 1 and module_input.get(field) != records[0][1].stat().st_size:
                    failures.append(f"module_input.{field} does not bind {role}")
            semantic_bindings = (
                ("source-module-semantic-ir", "source_semantic_ir_sha256"),
                ("target-module-semantic-ir", "target_semantic_ir_sha256"),
            )
            for role, field in semantic_bindings:
                records = role_records.get(role, [])
                if len(records) != 1:
                    continue
                try:
                    semantic_document = load(records[0][1])
                except Exception as exc:
                    failures.append(f"{role} is invalid JSON: {exc}")
                else:
                    if canonical_json_sha256(semantic_document) != module_input.get(field):
                        failures.append(f"module_input.{field} does not bind {role}")
                    side = "source" if role.startswith("source-") else "target"
                    expected_language = manifest.get(side, {}).get("language")
                    expected_logical_file = module_input.get(
                        f"{side}_logical_file"
                    )
                    if set(semantic_document) != {
                        "schema_version",
                        "source_language",
                        "source_file",
                        "analyzer",
                        "analyzer_version",
                        "functions",
                        "diagnostics",
                    }:
                        failures.append(f"{role} top-level keys are not exact")
                    if semantic_document.get("schema_version") != "1.0.0":
                        failures.append(f"{role} schema_version drift")
                    if semantic_document.get("source_language") != expected_language:
                        failures.append(f"{role} language does not bind route tuple")
                    if semantic_document.get("source_file") != expected_logical_file:
                        failures.append(f"{role} source_file does not bind module artifact")
                    if semantic_document.get("diagnostics") != []:
                        failures.append(f"{role} diagnostics must be empty")
                    for identity_field in ("analyzer", "analyzer_version"):
                        if not isinstance(
                            semantic_document.get(identity_field), str
                        ) or not semantic_document.get(identity_field):
                            failures.append(f"{role} {identity_field} is missing")
                    try:
                        from elmos_polyglot_route.models import (  # type: ignore[import-not-found]
                            SemanticIR,
                        )

                        round_trip = SemanticIR.from_mapping(
                            semantic_document
                        ).to_mapping()
                    except Exception as exc:
                        failures.append(f"{role} typed reconstruction failed: {exc}")
                    else:
                        if round_trip != semantic_document:
                            failures.append(f"{role} typed reconstruction drift")
                    if role == "source-module-semantic-ir":
                        source_semantic_document = semantic_document
                    else:
                        target_semantic_document = semantic_document
            case_records = role_records.get("module-case-manifest", [])
            if len(case_records) == 1:
                try:
                    case_manifest = load(case_records[0][1])
                except Exception as exc:
                    failures.append(f"module-case-manifest is invalid JSON: {exc}")
                else:
                    if canonical_json_sha256(case_manifest) != module_input.get(
                        "case_manifest_sha256"
                    ):
                        failures.append(
                            "module_input.case_manifest_sha256 does not bind module-case-manifest"
                        )
                    try:
                        _validate_optional_json_schema(
                            case_manifest,
                            "module-case-manifest.schema.json",
                            failures,
                            "module case manifest",
                        )
                    except Exception as exc:
                        failures.append(f"module case manifest schema validation crashed: {exc}")

            for role, report_field, destination_name in (
                ("source-module-validation", "source_validation", "source_validation"),
                ("target-module-validation", "target_validation", "target_validation"),
                ("source-module-observations", None, "source_observations"),
                ("target-module-observations", None, "target_observations"),
            ):
                records = role_records.get(role, [])
                if len(records) != 1:
                    continue
                try:
                    document = load(records[0][1])
                except Exception as exc:
                    failures.append(f"{role} is invalid JSON: {exc}")
                    continue
                if report_field is not None and evidence.get(report_field) != document:
                    failures.append(f"module report {report_field} differs from {role}")
                if destination_name == "source_validation":
                    source_validation_document = document
                elif destination_name == "target_validation":
                    target_validation_document = document
                elif destination_name == "source_observations":
                    source_observation_document = document
                else:
                    target_observation_document = document
            case_records = role_records.get("module-case-manifest", [])
            if len(case_records) == 1:
                try:
                    module_cases = load(case_records[0][1])
                except Exception:
                    pass

    contract = evidence.get("module_contract")
    if not isinstance(contract, dict):
        failures.append("module_contract must be an object")
        contract = {}
    symbol_sets: dict[str, list[str]] = {}
    for field in ("source_symbols", "target_symbols", "manifest_symbols"):
        values = contract.get(field)
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item for item in values
        ):
            failures.append(f"module_contract.{field} must contain non-empty symbols")
            values = []
        if len(values) != len(set(values)):
            failures.append(f"module_contract.{field} contains duplicate symbols")
        symbol_sets[field] = values

    functions = evidence.get("functions")
    if not isinstance(functions, list):
        failures.append("module functions must be an array")
        functions = []
    module_entries = module_cases.get("functions")
    manifest_by_symbol = {
        item.get("symbol"): item
        for item in (module_entries if isinstance(module_entries, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("symbol"), str)
    }
    source_artifact_record = next(
        iter(role_records.get("original-source-module-artifact", [])), None
    )
    target_artifact_record = next(
        iter(role_records.get("emitted-target-module-artifact", [])), None
    )
    semantic_functions: dict[str, dict[str, dict[str, Any]]] = {}
    for side, document in (
        ("source", source_semantic_document),
        ("target", target_semantic_document),
    ):
        raw_functions = document.get("functions")
        index_by_symbol: dict[str, dict[str, Any]] = {}
        if not isinstance(raw_functions, list) or not raw_functions:
            failures.append(f"{side} module semantic IR functions are missing")
        else:
            for function_index, raw_function in enumerate(raw_functions):
                if not isinstance(raw_function, dict):
                    failures.append(
                        f"{side} module semantic IR function {function_index} is invalid"
                    )
                    continue
                name = raw_function.get("name")
                if not isinstance(name, str) or not name or name in index_by_symbol:
                    failures.append(
                        f"{side} module semantic IR symbol set is invalid/duplicate"
                    )
                    continue
                index_by_symbol[name] = raw_function
        semantic_functions[side] = index_by_symbol
    if evidence.get("status") == "PASSED":
        domain_api = _engine_domain_api(failures, "module equivalence")
        if domain_api is not None:
            SemanticIR, enforce_semantic_domain, enforce_case_domain = domain_api
            source_language = manifest.get("source", {}).get("language")
            target_language = manifest.get("target", {}).get("language")
            try:
                source_typed_ir = SemanticIR.from_mapping(source_semantic_document)
                target_typed_ir = SemanticIR.from_mapping(target_semantic_document)
                enforce_semantic_domain(
                    source_typed_ir, source_language, target_language
                )
                enforce_semantic_domain(
                    target_typed_ir, source_language, target_language
                )
                typed_source_by_symbol = {
                    function.name: function for function in source_typed_ir.functions
                }
                entries = module_cases.get("functions")
                if not isinstance(entries, list):
                    raise ValueError("module case functions are missing")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("module case function entry is invalid")
                    symbol = entry.get("symbol")
                    cases = entry.get("cases")
                    if symbol not in typed_source_by_symbol or not isinstance(cases, list):
                        raise ValueError(f"module cases are detached for {symbol}")
                    enforce_case_domain(
                        typed_source_by_symbol[symbol],
                        cases,
                        source_language,
                        target_language,
                    )
            except Exception as exc:
                failures.append(
                    f"module equivalence specialized semantic/case domain rejected: {exc}"
                )
    function_symbols: list[str] = []
    for index, function in enumerate(functions):
        if not isinstance(function, dict):
            failures.append(f"module functions[{index}] must be an object")
            continue
        symbol = function.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            failures.append(f"module functions[{index}].symbol is invalid")
            continue
        function_symbols.append(symbol)
        layers = function.get("layers")
        if not isinstance(layers, dict) or set(layers) != MODULE_FUNCTION_LAYER_KEYS:
            failures.append(f"module function {symbol} layers are incomplete")
            continue
        if evidence.get("status") == "PASSED":
            if function.get("status") != "PASSED":
                failures.append(f"module function {symbol} did not pass")
            for layer_name in ("semantic", "chunk", "behavior"):
                layer = layers.get(layer_name)
                if not isinstance(layer, dict) or layer.get("status") != "PASSED":
                    failures.append(f"module function {symbol} {layer_name} did not pass")
            entry = manifest_by_symbol.get(symbol)
            cases = entry.get("cases") if isinstance(entry, dict) else None
            source_function = semantic_functions.get("source", {}).get(symbol)
            target_function = semantic_functions.get("target", {}).get(symbol)
            if source_function is None or target_function is None:
                failures.append(f"module function {symbol} is absent from bound semantic IR")
                continue
            expected_signature = (
                entry.get("signature") if isinstance(entry, dict) else None
            )
            if function.get("signature") != expected_signature:
                failures.append(f"module function {symbol} signature differs from manifest")
            semantic_signature = {
                "parameters": [
                    {"name": item.get("name"), "type": item.get("type")}
                    for item in source_function.get("parameters", [])
                    if isinstance(item, dict)
                ],
                "return_type": source_function.get("return_type"),
            }
            if expected_signature != semantic_signature:
                failures.append(f"module function {symbol} signature differs from semantic IR")
            if isinstance(cases, list) and function.get(
                "case_manifest_sha256"
            ) != canonical_json_sha256(cases):
                failures.append(f"module function {symbol} case manifest digest drift")
            _validate_concrete_chunk_document(
                layers.get("chunk"),
                label=f"module function {symbol} chunk",
                failures=failures,
                source_record=source_artifact_record,
                target_record=target_artifact_record,
                source_function=source_function,
                target_function=target_function,
            )
            _validate_module_behavior_layer(
                symbol=symbol,
                source_function=source_function,
                layer=layers.get("behavior"),
                cases=cases,
                source_validation=source_validation_document.get(symbol),
                target_validation=target_validation_document.get(symbol),
                source_observations=source_observation_document.get(symbol),
                target_observations=target_observation_document.get(symbol),
                failures=failures,
            )
            formal = layers.get("formal")
            if not isinstance(formal, dict):
                failures.append(f"module function {symbol} formal layer is invalid")
            else:
                if formal.get("status") not in MODULE_PASSING_PROOF_STATUSES:
                    failures.append(f"module function {symbol} proof is non-passing")
                if formal.get("property_status") != "PROVED":
                    failures.append(f"module function {symbol} formal property is not proved")
                if formal.get("proof_strength") != "THEOREM_UNDER_ASSUMPTIONS":
                    failures.append(
                        f"module function {symbol} proof strength must be THEOREM_UNDER_ASSUMPTIONS"
                    )
                _validate_module_formal_closure(
                    symbol=symbol,
                    signature=function.get("signature"),
                    source_function=source_function,
                    target_function=target_function,
                    semantic_layer=layers.get("semantic"),
                    case_manifest_sha256=function.get("case_manifest_sha256"),
                    formal=formal,
                    module_input_sha256=module_input_digest,
                    route_scope=expected_route_scope,
                    artifacts_by_path=artifacts_by_path,
                    failures=failures,
                )
    if len(function_symbols) != len(set(function_symbols)):
        failures.append("module functions contain duplicate symbols")

    composition = evidence.get("composition")
    if not isinstance(composition, dict):
        failures.append("module composition must be an object")
        composition = {}
    if evidence.get("status") == "PASSED":
        expected_symbols = set(function_symbols)
        if len(functions) < int(minimum_functions):
            failures.append(
                f"module equivalence requires at least {minimum_functions} functions"
            )
        for field, values in symbol_sets.items():
            if set(values) != expected_symbols:
                failures.append(f"module_contract.{field} does not match function symbols")
        if contract.get("exact_symbol_set") is not True:
            failures.append("module exact_symbol_set is not true")
        if contract.get("exact_signature_set") is not True:
            failures.append("module exact_signature_set is not true")
        if composition.get("function_count") != len(functions):
            failures.append("module composition function_count mismatch")
        if composition.get("passed_function_count") != len(functions):
            failures.append("module composition passed_function_count mismatch")
        if composition.get("status") != "PASSED":
            failures.append("module composition did not pass")
        if composition.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
            failures.append("module composition input domain drift")
        if (
            composition.get("out_of_domain_arithmetic_behavior")
            != SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
        ):
            failures.append("module composition out-of-domain boundary drift")
        if composition.get("original_source_bytes_theorem") is not False:
            failures.append("module composition overstates original-source theorem")
        if composition.get("source_compiler_runtime_soundness") != "NOT_RUN":
            failures.append("module source compiler/runtime soundness must remain NOT_RUN")
        if composition.get("target_compiler_runtime_soundness") != "NOT_RUN":
            failures.append("module target compiler/runtime soundness must remain NOT_RUN")
        if composition.get("proof_strength") != "COMPOSED_THEOREMS_UNDER_ASSUMPTIONS":
            failures.append("module composition proof strength is overstated or invalid")
        if composition.get("analyzer_and_emitter_soundness") != "ASSUMPTION":
            failures.append("module analyzer/emitter soundness boundary must remain ASSUMPTION")
        for role in (
            "formal-function-input",
            "formal-function-smt2",
            "formal-function-result",
        ):
            if len(role_records.get(role, [])) != len(functions):
                failures.append(
                    f"module {role} artifact count must equal function count"
                )
        observed_types: set[str] = set()
        for function in functions:
            if not isinstance(function, dict):
                continue
            signature = function.get("signature")
            if not isinstance(signature, dict):
                continue
            observed_types.add(str(signature.get("return_type")))
            parameters = signature.get("parameters")
            if isinstance(parameters, list):
                observed_types.update(
                    str(parameter.get("type"))
                    for parameter in parameters
                    if isinstance(parameter, dict)
                )
        if observed_types != {"integer", "number", "boolean"}:
            failures.append(
                "module signatures must cover exactly integer, number, and boolean"
            )
        case_records = role_records.get("module-case-manifest", [])
        if len(case_records) == 1:
            try:
                module_cases = load(case_records[0][1])
            except Exception as exc:
                failures.append(f"module-case-manifest is invalid JSON: {exc}")
            else:
                entries = module_cases.get("functions")
                if not isinstance(entries, list):
                    failures.append("module-case-manifest functions are invalid")
                else:
                    if set(manifest_by_symbol) != expected_symbols:
                        failures.append(
                            "module-case-manifest symbols do not match module functions"
                        )
                    for function in functions:
                        if not isinstance(function, dict):
                            continue
                        symbol = function.get("symbol")
                        entry = manifest_by_symbol.get(symbol)
                        if entry is None:
                            continue
                        if function.get("signature") != entry.get("signature"):
                            failures.append(
                                f"module function {symbol} signature differs from manifest"
                            )
                        if function.get("case_manifest_sha256") != canonical_json_sha256(
                            entry.get("cases")
                        ):
                            failures.append(
                                f"module function {symbol} case manifest digest drift"
                            )
    elif evidence.get("status") == "NOT_RUN":
        if functions or artifact_refs:
            failures.append("NOT_RUN module evidence cannot contain executed artifacts")
        limitations = evidence.get("limitations")
        if not isinstance(limitations, list) or not limitations:
            failures.append("NOT_RUN module evidence must explain its limitations")
    return evidence, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir")
    args = parser.parse_args()
    route = Path(args.route_dir)
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    certification: dict[str, Any] = {}
    specialized = False
    if not route.is_dir():
        errors.append(f"missing route dir: {route}")
    for directory in REQUIRED_DIRS:
        if not (route / directory).exists():
            errors.append(f"missing: {route / directory}")
    try:
        manifest = load(route / "route.json")
        from route_sets import (  # imported only at the CLI boundary for packed replay
            EVIDENCED_ROUTE_KEYS,
            SPECIALIZED_ROUTE_KEYS,
            split_route_key,
        )

        route_key = manifest.get("route_key")
        if route.name != route_key:
            errors.append("route directory name does not match route.json.route_key")
        if route_key not in EVIDENCED_ROUTE_KEYS:
            errors.append("route_key is outside the explicit Batch 29 allowlist")
        else:
            expected_source, expected_target = split_route_key(str(route_key))
            if (
                manifest.get("source", {}).get("language") != expected_source
                or manifest.get("target", {}).get("language") != expected_target
            ):
                errors.append("route source/target tuple does not match route_key")
            specialized = route_key in SPECIALIZED_ROUTE_KEYS
        for key in REQUIRED_ROUTE:
            if key not in manifest:
                errors.append(f"route.json missing key: {key}")
        if manifest.get("status") not in ALLOWED_ROUTE_STATUS:
            errors.append("invalid route status")
        if manifest.get("source", {}).get("language") == manifest.get("target", {}).get(
            "language"
        ):
            errors.append("source and target must differ")
        if not manifest.get("source", {}).get("versions"):
            errors.append("source versions are empty")
        if not manifest.get("target", {}).get("versions"):
            errors.append("target versions are empty")
        if manifest.get("owner") in {"", "UNASSIGNED", None}:
            errors.append("route owner is unassigned")
        if specialized:
            profiles = manifest.get("profiles", {})
            gates = manifest.get("gates", {})
            if manifest.get("status") != "limited":
                errors.append("specialized exact route status must remain limited")
            if profiles.get("module_profile") != "typed-pure-module-v1":
                errors.append("specialized module profile drift")
            if profiles.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized input domain drift")
            for field in (
                "module_equivalence_required",
                "concrete_spans_required",
                "canonical_finite_no_error_input_domain_required",
            ):
                if gates.get(field) is not True:
                    errors.append(f"specialized gate {field} must be true")
            if gates.get("specialized_string_semantics_allowed") is not False:
                errors.append("specialized string semantics must remain blocked")
            cpp_versions = [
                "C++20",
                "Apple clang version 21.0.0 (clang-2100.1.1.101)",
                "arm64-apple-darwin25.6.0",
            ]
            for side in ("source", "target"):
                side_value = manifest.get(side, {})
                if side_value.get("language") == "cpp" and side_value.get(
                    "versions"
                ) != cpp_versions:
                    errors.append(f"specialized {side} C++20/Apple clang tuple drift")
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(route / "support-matrix.json")
        if support.get("route_key") != manifest.get("route_key"):
            errors.append("support matrix route_key mismatch")
        for capability in support.get("capabilities", []):
            if capability.get("status") not in ALLOWED_CAP_STATUS:
                errors.append(f"invalid capability status: {capability.get('id')}")
            evidence_refs = capability.get("evidence_refs")
            if (
                capability.get("status") in {"certified", "supported"}
                and not evidence_refs
            ):
                errors.append(
                    f"{capability.get('status')} capability lacks evidence: {capability.get('id')}"
                )
            if capability.get("status") in {
                "conditional",
                "blocked",
            } and not capability.get("reason"):
                errors.append(
                    f"conditional/blocked capability lacks reason: {capability.get('id')}"
                )
            if isinstance(evidence_refs, list):
                for index, reference in enumerate(evidence_refs):
                    path = _resolve_below(
                        route,
                        reference,
                        f"capability {capability.get('id')} evidence_refs[{index}]",
                        errors,
                    )
                    if path is not None and not path.is_file():
                        errors.append(
                            f"capability evidence is missing: {capability.get('id')}:{reference}"
                        )
        if specialized:
            capability_by_id = {
                item.get("id"): item
                for item in support.get("capabilities", [])
                if isinstance(item, dict)
            }
            expected_statuses = {
                "typed-pure-function-v1": "conditional",
                "primitive-types": "conditional",
                "canonical-finite-no-error-input-domain": "supported",
                "string-semantics": "blocked",
                "arithmetic-error-domain": "blocked",
                "finite-number-transport-comparison": "conditional",
                "number-arithmetic": "blocked",
            }
            for capability_id, expected_status in expected_statuses.items():
                if capability_by_id.get(capability_id, {}).get("status") != expected_status:
                    errors.append(
                        f"specialized capability {capability_id} status drift"
                    )
            mappings = load(route / "mappings" / "types.json")
            if mappings.get("types") != ["integer", "number", "boolean"]:
                errors.append("specialized type mapping is not exact integer/number/boolean")
            if mappings.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized type mapping input domain drift")
            if mappings.get("string_semantics") != "BLOCK":
                errors.append("specialized type mapping does not block string")
            if mappings.get("type_evidence_corpora") != {
                "integer": "corpus/development",
                "number": "corpus/holdout",
                "boolean": "corpus/real-repository",
            }:
                errors.append("specialized type evidence corpus mapping drift")
            lowering = load(route / "lowering" / "profile.json")
            if lowering.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                errors.append("specialized lowering input domain drift")
            if lowering.get("concrete_spans_required") is not True:
                errors.append("specialized lowering does not require concrete spans")
            if lowering.get("string_semantics") != "BLOCKED":
                errors.append("specialized lowering does not block string")
            if lowering.get("operator_domains", {}).get("number_arithmetic") != {
                "operators": [],
                "blocked_operators": ["+", "-", "*", "/", "%"],
                "status": "BLOCKED",
            }:
                errors.append("specialized number arithmetic lowering policy drift")
    except Exception as exc:
        errors.append(str(exc))
    for file_path in [
        route / "compat-runtime" / "manifest.json",
        route / "certification" / "evidence.json",
        route / "certification" / "certification.json",
    ]:
        try:
            load(file_path)
        except Exception as exc:
            errors.append(str(exc))
    try:
        certification = load(route / "certification" / "certification.json")
        route_evidence = load(route / "certification" / "evidence.json")
        if (
            str(certification.get("status", "")).lower()
            != str(manifest.get("status", "")).lower()
        ):
            errors.append("route and certification statuses must match")
        _, strict_errors = validate_formal_equivalence(route, manifest, certification)
        errors.extend(strict_errors)
        _, module_errors = validate_module_equivalence(
            route, manifest, certification
        )
        errors.extend(module_errors)
        if specialized:
            if certification.get("certification_decision") != "NOT_CERTIFIED":
                errors.append("specialized route must remain NOT_CERTIFIED")
            expected_type_coverage = {
                "development": ["integer"],
                "holdout": ["number"],
                "real-repository": ["boolean"],
            }
            for corpus, coverage in expected_type_coverage.items():
                corpus_manifest = load(
                    route / "corpus" / corpus / "manifest.json"
                )
                if corpus_manifest.get("type_coverage") != coverage:
                    errors.append(f"specialized {corpus} type coverage drift")
                if corpus_manifest.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append(f"specialized {corpus} input domain drift")
            if route_evidence.get("execution_status") == "PASSED_LOCAL":
                if route_evidence.get("evidenced_type_coverage") != [
                    "integer",
                    "number",
                    "boolean",
                ]:
                    errors.append("specialized evidence type coverage drift")
                if route_evidence.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append("specialized evidence input domain drift")
                if (
                    route_evidence.get("out_of_domain_arithmetic_behavior")
                    != SPECIALIZED_OUT_OF_DOMAIN_ARITHMETIC
                ):
                    errors.append(
                        "specialized evidence out-of-domain arithmetic boundary drift"
                    )
        if manifest.get("gates", {}).get("module_equivalence_required") is True:
            module_root = route / "corpus" / "module"
            module_manifest_path = module_root / "manifest.json"
            if not module_manifest_path.is_file():
                errors.append("specialized route module corpus manifest is missing")
            else:
                module_manifest = load(module_manifest_path)
                if module_manifest.get("corpus") != "module":
                    errors.append("module corpus identity is invalid")
                if module_manifest.get("profile") != "typed-pure-module-v1":
                    errors.append("module corpus profile is invalid")
                if module_manifest.get("input_domain") != SPECIALIZED_INPUT_DOMAIN:
                    errors.append("module corpus input domain is invalid")
                if module_manifest.get("type_coverage_required") != [
                    "integer",
                    "number",
                    "boolean",
                ]:
                    errors.append("module corpus type coverage requirement drift")
                if module_manifest.get("source_language") != manifest.get("source", {}).get(
                    "language"
                ):
                    errors.append("module corpus source language mismatch")
                if module_manifest.get("minimum_function_count") != 3:
                    errors.append("module corpus minimum function count must be exactly 3")
                if (
                    module_manifest.get("independent") is not True
                    or module_manifest.get("independent_functions") is not True
                    or module_manifest.get("rule_authoring_input") is not False
                    or module_manifest.get("call_graph") != []
                ):
                    errors.append("module corpus independence contract is invalid")
                for field in ("source_file", "cases_file"):
                    value = module_manifest.get(field)
                    if (
                        not isinstance(value, str)
                        or not value
                        or Path(value).is_absolute()
                        or ".." in Path(value).parts
                        or not (module_root / value).is_file()
                    ):
                        errors.append(f"module corpus {field} is missing or unsafe")
                cases_value = module_manifest.get("cases_file")
                if isinstance(cases_value, str) and (module_root / cases_value).is_file():
                    module_cases = load(module_root / cases_value)
                    _validate_optional_json_schema(
                        module_cases,
                        "module-case-manifest.schema.json",
                        errors,
                        "module case manifest",
                    )
            for name in (
                "gap-inventory.md",
                "customer-support-profile.md",
                "economics.json",
            ):
                path = route / "certification" / name
                if not path.is_file() or path.stat().st_size == 0:
                    errors.append(f"specialized route certification file is missing: {name}")
            economics_path = route / "certification" / "economics.json"
            if economics_path.is_file():
                economics = load(economics_path)
                if economics.get("route_key") != manifest.get("route_key"):
                    errors.append("economics route_key mismatch")
                if economics.get("status") not in {"NOT_RUN", "PASSED"}:
                    errors.append("economics status is invalid")
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
