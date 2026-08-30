#!/usr/bin/env python3
"""Produce a digest-bound local qualification receipt for the v3.1 delta.

Only fixed repository-owned commands are executed.  The untrusted source ZIP,
its reference runtime, scripts, SQL and policies are never executed.  A PASS
receipt is self-attested local engineering evidence; PostgreSQL/provider/live
executor/independent/production conformance and certification remain NOT_RUN
or NOT_CERTIFIED.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Iterator, Mapping, Sequence
import zipfile


PACKAGE_NAME = "elmos-v3-harness-runtime-assurance-delta"
PACKAGE_VERSION = "3.1.0"
ARCHIVE_SHA256 = "13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37"
ARCHIVE_BYTES = 173_228
ENGINE_RELATIVE = Path("engines/proof-driven-harness-engine")
ARCHIVE_RELATIVE = Path(
    "skills/subskills/elmos-v3-harness-runtime-assurance-delta-v3.1.0.zip"
)
RUNNER_RELATIVE = ENGINE_RELATIVE / "tools/run_structured_unittest.py"
QUALIFIER_RELATIVE = ENGINE_RELATIVE / "tools/qualify_delta.py"
IMPORTER_RELATIVE = Path("tooling/integrate_harness_runtime_assurance_delta.py")
DELTA_TEST_RELATIVE = ENGINE_RELATIVE / "tests/test_delta_skills.py"
IMPORTER_TEST_RELATIVE = Path("tests/proof-driven-harness-v3/test_delta_integration.py")
ACCEPTANCE_BINDINGS_RELATIVE = (
    ENGINE_RELATIVE / "supply-chain/delta-v3.1-acceptance-bindings.json"
)
ENGINE_DELTA_TEST_PATTERN = "test_delta_*.py"
REQUIRED_ENGINE_DELTA_TESTS = (
    ENGINE_RELATIVE / "tests/test_delta_contract_closure.py",
    ENGINE_RELATIVE / "tests/test_delta_migration.py",
    ENGINE_RELATIVE / "tests/test_delta_qualification.py",
    ENGINE_RELATIVE / "tests/test_delta_skills.py",
)
# Reserved fixed entrypoints for the control-plane and durable-store bindings.
# They become mandatory inputs automatically when present; no arbitrary
# test_delta_*.py file may join the qualification corpus.
OPTIONAL_ENGINE_DELTA_TESTS = (
    ENGINE_RELATIVE / "tests/test_delta_control_plane.py",
    ENGINE_RELATIVE / "tests/test_delta_storage.py",
)
RECEIPT_RELATIVE = ENGINE_RELATIVE / "qualification/delta-v3.1/local-qualification.json"
RAW_RELATIVE = ENGINE_RELATIVE / "qualification/delta-v3.1/raw"
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_ENGINE_FILES = 10_000
MAX_ENGINE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_COMMAND_OUTPUT_BYTES = 16 * 1024 * 1024
EXCLUDED = frozenset(
    {
        "qualification",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
    }
)
TEST_TOTAL_KEYS = (
    "selected",
    "passed",
    "failed",
    "errors",
    "skipped",
    "expected_failures",
    "unexpected_successes",
)
LOCAL_EVIDENCE_BOUNDARY = "LOCAL_EXECUTED_SELF_ATTESTED"
TARGET_EVIDENCE_BOUNDARY = "NOT_RUN"
CERTIFICATION_BOUNDARY = "NOT_CERTIFIED"
EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL = 8
EXPECTED_ACCEPTANCE_SCENARIO_COUNT = 104
_ACCEPTANCE_ID_PATTERN = re.compile(
    r"ELMOS-V3D-(?P<number>\d{3})-"
    r"(?P<case>A0[1-5]|NEG-STALE|NEG-REPLAY|RECOVERY)"
)
_TEST_SELECTOR_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}")

# These are repository-owned pins for the 13 declarative acceptance documents
# inside the byte-pinned, untrusted source archive.  The qualifier reads only
# these exact members as bounded data; it never imports or executes ZIP code.
EXPECTED_ACCEPTANCE_SOURCES: Mapping[str, Mapping[str, Any]] = {
    "elmos-tool-result-interception-commit": {
        "priority": "P0",
        "number": "001",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-tool-result-interception-commit/acceptance.yaml",
        "sha256": "sha256:5899a783fb88568b847f0216c5ab99542aa5a9022545ae6c0d99b901af3f63fa",
        "bytes": 4331,
    },
    "elmos-step-finalized-execution-plan": {
        "priority": "P0",
        "number": "002",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-step-finalized-execution-plan/acceptance.yaml",
        "sha256": "sha256:69ea973a1920a132dd491bbafbf76e4d36e4491b243fd2fb62878dc615dede96",
        "bytes": 4160,
    },
    "elmos-lossless-permission-replay": {
        "priority": "P0",
        "number": "003",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-lossless-permission-replay/acceptance.yaml",
        "sha256": "sha256:35bf117108f3795c015f45bb84cf05461b731d8a43d9664b94934b2634f282bd",
        "bytes": 4034,
    },
    "elmos-invocation-scoped-capability-lease": {
        "priority": "P0",
        "number": "004",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-invocation-scoped-capability-lease/acceptance.yaml",
        "sha256": "sha256:c5bf7c691b2b4c623b6cc7ac1db7c78999b621c5259a00da0673db1abf088f1f",
        "bytes": 4079,
    },
    "elmos-host-minted-security-context": {
        "priority": "P0",
        "number": "005",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-host-minted-security-context/acceptance.yaml",
        "sha256": "sha256:7c77ec1eab3e1e333f2f7ee092b38833ae0ef6572243a521a7eb447bf9b9d398",
        "bytes": 4322,
    },
    "elmos-environment-attachment-authority": {
        "priority": "P0",
        "number": "006",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-environment-attachment-authority/acceptance.yaml",
        "sha256": "sha256:be88c48775799b87b596384c12bba2ee275068eb8ddbab1faa3d81e8a52d7c54",
        "bytes": 4100,
    },
    "elmos-executor-generation-fencing": {
        "priority": "P0",
        "number": "007",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-executor-generation-fencing/acceptance.yaml",
        "sha256": "sha256:43346d677759774890f99feafe8204b8e149e1f8fb1a87c1cb317ac2320dbebc",
        "bytes": 4115,
    },
    "elmos-workspace-ownership-lease": {
        "priority": "P0",
        "number": "008",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-workspace-ownership-lease/acceptance.yaml",
        "sha256": "sha256:8d20baca448f17061c9c2284d5b228e4f5f0ef8605ad1f3e9138511505040cd6",
        "bytes": 3995,
    },
    "elmos-harness-transport-version-negotiation": {
        "priority": "P0",
        "number": "009",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-harness-transport-version-negotiation/acceptance.yaml",
        "sha256": "sha256:1e99db46ff3a4768dfda6232165a11746a0151996d7708e46fe7b09c393dca53",
        "bytes": 4229,
    },
    "elmos-skill-trust-domain-provenance": {
        "priority": "P0",
        "number": "010",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P0/elmos-skill-trust-domain-provenance/acceptance.yaml",
        "sha256": "sha256:5f379ff123b476650e00367908b72a124a09e173fc6af0385fb9fd83fbba0fdf",
        "bytes": 4184,
    },
    "elmos-registered-durable-plugin-events": {
        "priority": "P1",
        "number": "011",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P1/elmos-registered-durable-plugin-events/acceptance.yaml",
        "sha256": "sha256:12540cc7b24258662c8c41d0b24e4aef5089f64a0970d6e0c61c833db1f63d15",
        "bytes": 4145,
    },
    "elmos-typed-external-ingress": {
        "priority": "P1",
        "number": "012",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P1/elmos-typed-external-ingress/acceptance.yaml",
        "sha256": "sha256:18649ba6606a46c8f0b4f322596b7051339b2b8e5718a82096c99832e543e1c3",
        "bytes": 4022,
    },
    "elmos-subagent-model-execution-spec": {
        "priority": "P1",
        "number": "013",
        "archive_member": "elmos-v3-harness-runtime-assurance-delta-v3.1.0/payload/skills/extensions/P1/elmos-subagent-model-execution-spec/acceptance.yaml",
        "sha256": "sha256:c6d7d907ff2d7217eefdee5434b8a091d10e6dcdd93199d56b55b25c436222e7",
        "bytes": 4142,
    },
}


class QualificationError(RuntimeError):
    pass


def _lock_path(repo_root: Path) -> Path:
    lock_root = Path(tempfile.gettempdir()).resolve(strict=True)
    return lock_root / (
        "elmos-harness-runtime-delta-"
        + hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:24]
        + ".lock"
    )


def _assert_lock_binding(path: Path, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    try:
        pathname = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise QualificationError(
            "delta qualification lock pathname disappeared"
        ) from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(pathname.st_mode)
        or opened.st_uid != os.geteuid()
        or pathname.st_uid != os.geteuid()
        or opened.st_nlink != 1
        or pathname.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) & 0o022
        or stat.S_IMODE(pathname.st_mode) & 0o022
        or (opened.st_dev, opened.st_ino) != (pathname.st_dev, pathname.st_ino)
    ):
        raise QualificationError("delta qualification lock pathname binding is unsafe")


@contextmanager
def _exclusive_lock(repo_root: Path) -> Iterator[None]:
    """Serialize receipt publication with importer promotion."""

    path = _lock_path(repo_root)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise QualificationError(
            f"cannot safely open delta qualification lock {path}: {exc}"
        ) from exc
    try:
        _assert_lock_binding(path, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _assert_lock_binding(path, descriptor)
        try:
            yield
        except BaseException:
            raise
        else:
            _assert_lock_binding(path, descriptor)
    finally:
        os.close(descriptor)


def qualification_inputs(inventory: Sequence[Mapping[str, Any]]) -> tuple[Path, ...]:
    inventory_paths = {
        ENGINE_RELATIVE / str(row.get("path"))
        for row in inventory
        if isinstance(row.get("path"), str)
    }
    discovered = {
        ENGINE_RELATIVE / str(row.get("path"))
        for row in inventory
        if PurePosixPath(str(row.get("path"))).parent == PurePosixPath("tests")
        and PurePosixPath(str(row.get("path"))).match(ENGINE_DELTA_TEST_PATTERN)
    }
    required = set(REQUIRED_ENGINE_DELTA_TESTS)
    allowed = required | set(OPTIONAL_ENGINE_DELTA_TESTS)
    missing = required - discovered
    unexpected = discovered - allowed
    missing_support = (
        set()
        if ACCEPTANCE_BINDINGS_RELATIVE in inventory_paths
        else {ACCEPTANCE_BINDINGS_RELATIVE}
    )
    if missing or unexpected or missing_support:
        raise QualificationError(
            "delta qualification test inventory drifted: "
            f"missing={sorted(map(str, missing))} "
            f"unexpected={sorted(map(str, unexpected))} "
            f"missing_support={sorted(map(str, missing_support))}"
        )
    return (
        QUALIFIER_RELATIVE,
        RUNNER_RELATIVE,
        IMPORTER_RELATIVE,
        ACCEPTANCE_BINDINGS_RELATIVE,
        *tuple(sorted(discovered)),
        IMPORTER_TEST_RELATIVE,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QualificationError(f"duplicate JSON key in command output: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise QualificationError(f"non-finite JSON value in command output: {value}")


def _strict_json_text(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as exc:
        raise QualificationError(f"invalid JSON command output: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_mapping_keys(
    value: Any,
    expected: set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise QualificationError(f"{label} has an invalid shape")
    if any(not isinstance(key, str) for key in value):
        raise QualificationError(f"{label} has a non-string key")
    return value


def _parse_acceptance_source(
    payload: bytes,
    *,
    expected_skill: str,
    expected_number: str,
) -> tuple[tuple[str, str], ...]:
    """Read only the fixed identity/priority fields from one YAML document."""

    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise QualificationError("acceptance source is not canonical UTF-8") from exc
    if "\r" in text or "\x00" in text:
        raise QualificationError("acceptance source has non-canonical line content")
    skill_values = [
        line.removeprefix("  skill: ")
        for line in text.splitlines()
        if line.startswith("  skill: ")
    ]
    version_values = [
        line.removeprefix("  version: ")
        for line in text.splitlines()
        if line.startswith("  version: ")
    ]
    if skill_values != [expected_skill] or version_values != [PACKAGE_VERSION]:
        raise QualificationError("acceptance source identity drifted")

    scenarios: list[tuple[str, str]] = []
    current_id: str | None = None
    current_priorities: list[str] = []

    def finish() -> None:
        nonlocal current_id, current_priorities
        if current_id is None:
            return
        if len(current_priorities) != 1 or current_priorities[0] not in {"P0", "P1"}:
            raise QualificationError(
                f"acceptance scenario priority is invalid: {current_id}"
            )
        scenarios.append((current_id, current_priorities[0]))
        current_id = None
        current_priorities = []

    for line in text.splitlines():
        if line.startswith("  - id: "):
            finish()
            current_id = line.removeprefix("  - id: ")
            match = _ACCEPTANCE_ID_PATTERN.fullmatch(current_id)
            if match is None or match.group("number") != expected_number:
                raise QualificationError(
                    f"acceptance scenario identity is invalid: {current_id}"
                )
        elif current_id is not None and line.startswith("    priority: "):
            current_priorities.append(line.removeprefix("    priority: "))
    finish()
    if len(scenarios) != EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL:
        raise QualificationError(
            f"acceptance source must contain exactly eight scenarios: {expected_skill}"
        )
    expected_suffixes = {
        "A01",
        "A02",
        "A03",
        "A04",
        "A05",
        "NEG-STALE",
        "NEG-REPLAY",
        "RECOVERY",
    }
    observed_suffixes = {
        identifier.removeprefix(f"ELMOS-V3D-{expected_number}-")
        for identifier, _ in scenarios
    }
    if observed_suffixes != expected_suffixes:
        raise QualificationError(f"acceptance scenario set drifted: {expected_skill}")
    return tuple(scenarios)


def _acceptance_sources_from_archive(
    archive_payload: bytes,
) -> Mapping[str, tuple[bytes, tuple[tuple[str, str], ...]]]:
    if (
        len(archive_payload) != ARCHIVE_BYTES
        or sha256(archive_payload) != ARCHIVE_SHA256
    ):
        raise QualificationError("delta source archive identity drifted")
    expected_members = {
        str(source["archive_member"]): skill
        for skill, source in EXPECTED_ACCEPTANCE_SOURCES.items()
    }
    try:
        with zipfile.ZipFile(io.BytesIO(archive_payload), mode="r") as archive:
            matching: dict[str, list[zipfile.ZipInfo]] = {
                member: [] for member in expected_members
            }
            for info in archive.infolist():
                if info.filename in matching:
                    matching[info.filename].append(info)
            result: dict[str, tuple[bytes, tuple[tuple[str, str], ...]]] = {}
            for member, skill in expected_members.items():
                infos = matching[member]
                expected = EXPECTED_ACCEPTANCE_SOURCES[skill]
                if len(infos) != 1:
                    raise QualificationError(
                        f"acceptance archive member is missing or duplicated: {member}"
                    )
                info = infos[0]
                unix_mode = (info.external_attr >> 16) & 0o170000
                if (
                    info.is_dir()
                    or info.flag_bits & 0x1
                    or info.file_size != expected["bytes"]
                    or info.file_size > 64 * 1024
                    or unix_mode not in {0, stat.S_IFREG}
                ):
                    raise QualificationError(
                        f"acceptance archive member is unsafe: {member}"
                    )
                payload = archive.read(info)
                observed_digest = "sha256:" + sha256(payload)
                if (
                    len(payload) != expected["bytes"]
                    or observed_digest != expected["sha256"]
                ):
                    raise QualificationError(
                        f"acceptance archive member digest drifted: {member}"
                    )
                scenarios = _parse_acceptance_source(
                    payload,
                    expected_skill=skill,
                    expected_number=str(expected["number"]),
                )
                result[skill] = (payload, scenarios)
            return result
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise QualificationError("delta acceptance archive could not be read") from exc


def _load_acceptance_bindings(
    binding_payload: bytes,
    archive_payload: bytes,
) -> Mapping[str, Any]:
    """Validate the fixed static mapping against exact ZIP source documents."""

    if len(binding_payload) > 2 * 1024 * 1024:
        raise QualificationError("acceptance binding exceeds the byte limit")
    try:
        decoded = binding_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise QualificationError("acceptance binding is not canonical UTF-8") from exc
    value = _strict_json_text(decoded)
    root = _exact_mapping_keys(
        value,
        {
            "schema_version",
            "kind",
            "package",
            "source_archive",
            "binding_semantics",
            "expected_skill_count",
            "expected_scenarios_per_skill",
            "expected_scenario_count",
            "skills",
        },
        label="acceptance binding",
    )
    expected_archive = {
        "path": ARCHIVE_RELATIVE.as_posix(),
        "sha256": "sha256:" + ARCHIVE_SHA256,
        "bytes": ARCHIVE_BYTES,
        "executed": False,
    }
    expected_semantics = {
        "classification": "STATIC_TRACEABILITY_ONLY",
        "successful_local_result_boundary": LOCAL_EVIDENCE_BOUNDARY,
        "target_environment": TARGET_EVIDENCE_BOUNDARY,
        "independent_verification": TARGET_EVIDENCE_BOUNDARY,
        "certification": CERTIFICATION_BOUNDARY,
        "static_mapping_is_execution_evidence": False,
    }
    if (
        root.get("schema_version") != "1.0.0"
        or root.get("kind")
        != "elmos.harness-runtime-assurance-delta.acceptance-bindings"
        or root.get("package") != f"{PACKAGE_NAME}@{PACKAGE_VERSION}"
        or root.get("source_archive") != expected_archive
        or root.get("binding_semantics") != expected_semantics
        or root.get("expected_skill_count") != len(EXPECTED_ACCEPTANCE_SOURCES)
        or root.get("expected_scenarios_per_skill")
        != EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL
        or root.get("expected_scenario_count") != EXPECTED_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise QualificationError("acceptance binding header drifted")
    if len(
        {str(source["sha256"]) for source in EXPECTED_ACCEPTANCE_SOURCES.values()}
    ) != len(EXPECTED_ACCEPTANCE_SOURCES):
        raise QualificationError("acceptance source digests are not unique")
    source_documents = _acceptance_sources_from_archive(archive_payload)
    skills = root.get("skills")
    if not isinstance(skills, list) or len(skills) != len(EXPECTED_ACCEPTANCE_SOURCES):
        raise QualificationError("acceptance binding skill inventory is incomplete")
    observed_skill_order: list[str] = []
    observed_ids: set[str] = set()
    cases: list[dict[str, Any]] = []
    skill_keys = {"skill", "priority", "source_acceptance", "cases"}
    source_keys = {"archive_member", "sha256", "bytes", "executed"}
    case_keys = {
        "acceptance_id",
        "priority",
        "repository_test_selectors",
        "local_evidence_boundary",
        "target_environment",
        "certification",
    }
    for raw_skill in skills:
        skill_record = _exact_mapping_keys(
            raw_skill,
            skill_keys,
            label="acceptance skill binding",
        )
        skill = skill_record.get("skill")
        if not isinstance(skill, str) or skill not in EXPECTED_ACCEPTANCE_SOURCES:
            raise QualificationError("acceptance binding has an unknown skill")
        expected = EXPECTED_ACCEPTANCE_SOURCES[skill]
        observed_skill_order.append(skill)
        source_record = _exact_mapping_keys(
            skill_record.get("source_acceptance"),
            source_keys,
            label="acceptance source binding",
        )
        expected_source_record = {
            "archive_member": expected["archive_member"],
            "sha256": expected["sha256"],
            "bytes": expected["bytes"],
            "executed": False,
        }
        if (
            skill_record.get("priority") != expected["priority"]
            or source_record != expected_source_record
        ):
            raise QualificationError(f"acceptance source binding drifted: {skill}")
        raw_cases = skill_record.get("cases")
        if not isinstance(raw_cases, list) or len(raw_cases) != (
            EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL
        ):
            raise QualificationError(
                f"acceptance skill binding must contain eight cases: {skill}"
            )
        source_scenarios = source_documents[skill][1]
        expected_case_order = [identifier for identifier, _ in source_scenarios]
        observed_case_order: list[str] = []
        source_priorities = dict(source_scenarios)
        for raw_case in raw_cases:
            case = _exact_mapping_keys(
                raw_case,
                case_keys,
                label="acceptance case binding",
            )
            acceptance_id = case.get("acceptance_id")
            selectors = case.get("repository_test_selectors")
            if (
                not isinstance(acceptance_id, str)
                or acceptance_id in observed_ids
                or acceptance_id not in source_priorities
                or case.get("priority") != source_priorities.get(acceptance_id)
                or not isinstance(selectors, list)
                or not 1 <= len(selectors) <= 8
                or any(
                    not isinstance(selector, str)
                    or len(selector) > 1024
                    or _TEST_SELECTOR_PATTERN.fullmatch(selector) is None
                    for selector in selectors
                )
                or len(set(selectors)) != len(selectors)
                or case.get("local_evidence_boundary") != LOCAL_EVIDENCE_BOUNDARY
                or case.get("target_environment") != TARGET_EVIDENCE_BOUNDARY
                or case.get("certification") != CERTIFICATION_BOUNDARY
            ):
                raise QualificationError(
                    f"acceptance case binding drifted: {acceptance_id}"
                )
            observed_ids.add(acceptance_id)
            observed_case_order.append(acceptance_id)
            cases.append(
                {
                    "acceptance_id": acceptance_id,
                    "priority": str(case["priority"]),
                    "skill": skill,
                    "source_acceptance_sha256": str(expected["sha256"]),
                    "repository_test_selectors": list(selectors),
                }
            )
        if observed_case_order != expected_case_order:
            raise QualificationError(
                f"acceptance case order or identity drifted: {skill}"
            )
    if observed_skill_order != list(EXPECTED_ACCEPTANCE_SOURCES):
        raise QualificationError("acceptance binding skill order or identity drifted")
    if (
        len(observed_ids) != EXPECTED_ACCEPTANCE_SCENARIO_COUNT
        or len(cases) != EXPECTED_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise QualificationError("acceptance binding is not exactly 13x8")
    return {
        "path": ACCEPTANCE_BINDINGS_RELATIVE.as_posix(),
        "sha256": "sha256:" + sha256(binding_payload),
        "skills": len(EXPECTED_ACCEPTANCE_SOURCES),
        "scenarios_per_skill": EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL,
        "scenarios": EXPECTED_ACCEPTANCE_SCENARIO_COUNT,
        "cases": cases,
        "mapping_classification": "STATIC_TRACEABILITY_ONLY",
        "static_mapping_is_execution_evidence": False,
    }


def _assert_acceptance_results(
    bindings: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    raw_cases = bindings.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != (
        EXPECTED_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise QualificationError("validated acceptance cases are unavailable")
    by_selector: dict[str, Mapping[str, Any]] = {}
    for outcome in outcomes:
        selector = outcome.get("selector")
        if not isinstance(selector, str) or selector in by_selector:
            raise QualificationError("test outcomes contain duplicate selectors")
        by_selector[selector] = outcome
    case_results: list[dict[str, Any]] = []
    priorities = {"P0": 0, "P1": 0}
    for raw_case in raw_cases:
        case = _exact_mapping_keys(
            raw_case,
            {
                "acceptance_id",
                "priority",
                "skill",
                "source_acceptance_sha256",
                "repository_test_selectors",
            },
            label="validated acceptance case",
        )
        selectors = case.get("repository_test_selectors")
        if not isinstance(selectors, list) or not selectors:
            raise QualificationError("validated acceptance selectors are unavailable")
        test_evidence: list[dict[str, str]] = []
        for selector in selectors:
            bound_outcome = (
                by_selector.get(selector) if isinstance(selector, str) else None
            )
            if bound_outcome is None or bound_outcome.get("status") != "PASSED":
                raise QualificationError(
                    "acceptance selector did not pass: "
                    f"{case.get('acceptance_id')}:{selector}"
                )
            source_path = bound_outcome.get("source_path")
            source_digest = bound_outcome.get("source_sha256")
            if (
                not isinstance(source_path, str)
                or not isinstance(source_digest, str)
                or len(source_digest) != 71
                or not source_digest.startswith("sha256:")
                or any(
                    character not in "0123456789abcdef"
                    for character in source_digest[7:]
                )
            ):
                raise QualificationError(
                    "acceptance selector lacks source-bound evidence"
                )
            test_evidence.append(
                {
                    "selector": selector,
                    "source_path": source_path,
                    "source_sha256": source_digest,
                }
            )
        priority = case.get("priority")
        if not isinstance(priority, str) or priority not in priorities:
            raise QualificationError("acceptance result priority is invalid")
        priorities[priority] += 1
        case_results.append(
            {
                "acceptance_id": case["acceptance_id"],
                "skill": case["skill"],
                "priority": priority,
                "source_acceptance_sha256": case["source_acceptance_sha256"],
                "repository_test_selectors": list(selectors),
                "repository_test_evidence": test_evidence,
                "local_result": "PASSED",
                "local_evidence_boundary": LOCAL_EVIDENCE_BOUNDARY,
                "target_environment": TARGET_EVIDENCE_BOUNDARY,
                "certification": CERTIFICATION_BOUNDARY,
            }
        )
    return {
        "binding_path": bindings["path"],
        "binding_sha256": bindings["sha256"],
        "mapping_classification": bindings["mapping_classification"],
        "static_mapping_is_execution_evidence": False,
        "skills": bindings["skills"],
        "scenarios_per_skill": bindings["scenarios_per_skill"],
        "scenarios": bindings["scenarios"],
        "local_cases": {
            "passed": len(case_results),
            "failed": 0,
            "p0_passed": priorities["P0"],
            "p1_passed": priorities["P1"],
            "evidence_boundary": LOCAL_EVIDENCE_BOUNDARY,
        },
        "target_environment": TARGET_EVIDENCE_BOUNDARY,
        "independent_verification": TARGET_EVIDENCE_BOUNDARY,
        "certification": CERTIFICATION_BOUNDARY,
        "case_results": case_results,
    }


def _safe_bytes(
    path: Path, *, limit: int = MAX_FILE_BYTES
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise QualificationError(
            f"cannot safely read qualification input {path}: {exc}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise QualificationError(
                f"qualification input is not a bounded regular file: {path}"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise QualificationError(f"qualification input exceeds limit: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)

        def identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        payload = b"".join(chunks)
        if identity(before) != identity(after) or len(payload) != before.st_size:
            raise QualificationError(
                f"qualification input changed while reading: {path}"
            )
        return payload, before
    finally:
        os.close(descriptor)


def _safe_repo_bytes(
    repo_root: Path, relative: Path, *, limit: int = MAX_FILE_BYTES
) -> tuple[bytes, os.stat_result]:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise QualificationError(f"unsafe repository qualification path: {relative}")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = os.open(repo_root, directory_flags)
    opened: list[int] = []
    directory_bindings: list[tuple[int, str, int, os.stat_result]] = []
    descriptor = root_fd
    try:
        root_opened = os.fstat(root_fd)
        root_path = os.stat(repo_root, follow_symlinks=False)
        if (root_opened.st_dev, root_opened.st_ino) != (
            root_path.st_dev,
            root_path.st_ino,
        ):
            raise QualificationError("repository root changed while opening")
        for component in relative.parts[:-1]:
            metadata = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise QualificationError(
                    f"linked qualification input directory is forbidden: {relative}"
                )
            child = os.open(component, directory_flags, dir_fd=descriptor)
            opened.append(child)
            child_metadata = os.fstat(child)
            if (metadata.st_dev, metadata.st_ino) != (
                child_metadata.st_dev,
                child_metadata.st_ino,
            ):
                raise QualificationError(
                    f"qualification input directory changed: {relative}"
                )
            directory_bindings.append((descriptor, component, child, metadata))
            descriptor = child
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=descriptor,
        )
        opened.append(file_fd)
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 0
            or before.st_size > limit
        ):
            raise QualificationError(
                f"qualification input is not a bounded regular file: {relative}"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_fd, min(remaining, 1024 * 1024))
            if not chunk:
                raise QualificationError(
                    f"qualification input changed while reading: {relative}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            raise QualificationError(
                f"qualification input grew while reading: {relative}"
            )
        after = os.fstat(file_fd)

        def identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
            return (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        if identity(before) != identity(after):
            raise QualificationError(
                f"qualification input changed while reading: {relative}"
            )
        pathname = os.stat(relative.parts[-1], dir_fd=descriptor, follow_symlinks=False)
        if identity(pathname) != identity(before):
            raise QualificationError(
                f"qualification input pathname changed while reading: {relative}"
            )
        for parent_fd, component, child_fd, expected in reversed(directory_bindings):
            current = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            child_metadata = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino)
                != (expected.st_dev, expected.st_ino)
                or (current.st_dev, current.st_ino)
                != (child_metadata.st_dev, child_metadata.st_ino)
            ):
                raise QualificationError(
                    f"qualification input directory binding changed: {relative}"
                )
        current_root = os.stat(repo_root, follow_symlinks=False)
        if (current_root.st_dev, current_root.st_ino) != (
            root_opened.st_dev,
            root_opened.st_ino,
        ):
            raise QualificationError(
                "repository root changed while reading qualification input"
            )
        return b"".join(chunks), before
    except OSError as exc:
        raise QualificationError(
            f"cannot safely read qualification input {relative}: {exc}"
        ) from exc
    finally:
        for item in reversed(opened):
            os.close(item)
        os.close(root_fd)


def _excluded(relative: PurePosixPath) -> bool:
    return (
        any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts)
        or relative.suffix == ".pyc"
    )


def engine_inventory(engine_root: Path) -> list[dict[str, Any]]:
    if engine_root.is_symlink() or not engine_root.is_dir():
        raise QualificationError("engine root must be a real directory")
    records: list[dict[str, Any]] = []
    total_bytes = 0
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    def read_at(
        directory_fd: int, name: str, display: str
    ) -> tuple[bytes, os.stat_result]:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
                raise QualificationError(
                    f"engine input is not a bounded regular file: {display}"
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            payload = b"".join(chunks)
            if before_identity != after_identity or len(payload) != before.st_size:
                raise QualificationError(
                    f"engine input changed while reading: {display}"
                )
            return payload, before
        finally:
            os.close(descriptor)

    def walk(directory_fd: int, prefix: PurePosixPath) -> None:
        nonlocal total_bytes
        for name in sorted(os.listdir(directory_fd)):
            relative = prefix / name
            if _excluded(relative):
                continue
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise QualificationError(
                    f"linked engine input is forbidden: {relative}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                child = os.open(name, directory_flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (
                        metadata.st_dev,
                        metadata.st_ino,
                    ):
                        raise QualificationError(
                            f"engine directory changed while opening: {relative}"
                        )
                    walk(child, relative)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise QualificationError(
                    f"special engine input is forbidden: {relative}"
                )
            payload, opened = read_at(directory_fd, name, relative.as_posix())
            if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ):
                raise QualificationError(
                    f"engine input changed while opening: {relative}"
                )
            records.append(
                {
                    "path": relative.as_posix(),
                    "bytes": len(payload),
                    "sha256": "sha256:" + sha256(payload),
                }
            )
            total_bytes += len(payload)
            if len(records) > MAX_ENGINE_FILES or total_bytes > MAX_ENGINE_TOTAL_BYTES:
                raise QualificationError(
                    "engine qualification inventory exceeds bounded limits"
                )

    root_fd = os.open(engine_root, directory_flags)
    try:
        opened_root = os.fstat(root_fd)
        pathname_root = os.stat(engine_root, follow_symlinks=False)
        if (opened_root.st_dev, opened_root.st_ino) != (
            pathname_root.st_dev,
            pathname_root.st_ino,
        ):
            raise QualificationError("engine root changed while opening")
        walk(root_fd, PurePosixPath())
        pathname_after = os.stat(engine_root, follow_symlinks=False)
        if (opened_root.st_dev, opened_root.st_ino) != (
            pathname_after.st_dev,
            pathname_after.st_ino,
        ):
            raise QualificationError("engine root changed during inventory")
    finally:
        os.close(root_fd)
    if not records or not any(
        row["path"] == "src/elmos_proof_harness/delta.py" for row in records
    ):
        raise QualificationError("delta runtime is absent from engine inventory")
    return records


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    if path == Path(".") or os.fspath(path) in {"", "."}:
        raise QualificationError("qualification output cannot be the current directory")
    if not isinstance(payload, bytes) or len(payload) > MAX_COMMAND_OUTPUT_BYTES:
        raise QualificationError("qualification output is not bounded bytes")
    if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o777:
        raise QualificationError("qualification output mode is unsafe")
    absolute = Path(os.path.abspath(os.fspath(path)))
    parts = absolute.parts
    if len(parts) < 2:
        raise QualificationError("qualification output path is unsafe")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_fd = os.open(parts[0], directory_flags)
    temporary: str | None = None
    try:
        for component in parts[1:-1]:
            created = False
            try:
                metadata = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                os.mkdir(component, 0o700, dir_fd=parent_fd)
                created = True
                os.fsync(parent_fd)
                metadata = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise QualificationError(
                    f"qualification output directory is unsafe: {component}"
                )
            child = os.open(component, directory_flags, dir_fd=parent_fd)
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                os.close(child)
                raise QualificationError(
                    f"qualification output directory changed: {component}"
                )
            if created:
                os.fsync(child)
            os.close(parent_fd)
            parent_fd = child
        parent_metadata = os.fstat(parent_fd)
        name = parts[-1]
        try:
            existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise QualificationError(f"qualification output target is unsafe: {path}")
        temporary = f".{name}.{uuid.uuid4().hex}"
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise QualificationError(
                        f"short qualification output write: {path}"
                    )
                view = view[written:]
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
        os.fsync(parent_fd)
        current_parent = os.stat(absolute.parent, follow_symlinks=False)
        if not stat.S_ISDIR(current_parent.st_mode) or (
            current_parent.st_dev,
            current_parent.st_ino,
        ) != (parent_metadata.st_dev, parent_metadata.st_ino):
            raise QualificationError(
                f"qualification output parent changed during publication: {path}"
            )
        published = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(published.st_mode)
            or published.st_uid != os.geteuid()
            or published.st_nlink != 1
            or stat.S_IMODE(published.st_mode) != mode
            or published.st_size != len(payload)
        ):
            raise QualificationError(
                f"qualification output publication changed: {path}"
            )
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _environment(repo_root: Path) -> dict[str, str]:
    engine_source = repo_root / ENGINE_RELATIVE / "src"
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": os.pathsep.join((str(engine_source), str(repo_root))),
        "UV_OFFLINE": "1",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost",
    }


def _run(
    repo_root: Path, name: str, argv: Sequence[str]
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    started = time.monotonic_ns()
    completed = subprocess.run(
        list(argv),
        cwd=repo_root,
        env=_environment(repo_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
        check=False,
    )
    if (
        len(completed.stdout.encode("utf-8")) + len(completed.stderr.encode("utf-8"))
        > MAX_COMMAND_OUTPUT_BYTES
    ):
        raise QualificationError(f"{name} command output exceeds the byte limit")
    parsed: Mapping[str, Any] | None = None
    try:
        candidate = _strict_json_text(completed.stdout)
        if isinstance(candidate, Mapping):
            parsed = candidate
    except QualificationError:
        pass
    raw = {
        "schema_version": "1.0.0",
        "name": name,
        "argv": list(argv),
        "cwd": ".",
        "returncode": completed.returncode,
        "timed_out": False,
        "wall_clock_milliseconds": max(0, (time.monotonic_ns() - started) // 1_000_000),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "execution_environment": {
            "python": {
                "implementation": platform.python_implementation(),
                "version": platform.python_version(),
                "executable": sys.executable,
            },
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "network": "LOOPBACK_PROXY_DENY",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }
    return raw, parsed


def _assert_structured(
    name: str,
    raw: Mapping[str, Any],
    parsed: Mapping[str, Any] | None,
    *,
    start_directory: str,
    pattern: str,
    expected_sources: Mapping[str, str],
) -> Mapping[str, int]:
    expected_result_keys = {
        "schema_version",
        "kind",
        "status",
        "discovery",
        "totals",
        "outcomes",
        "runner_output",
        "captured_stdout",
        "captured_stderr",
        "evidence_boundary",
    }
    if (
        raw.get("returncode") != 0
        or parsed is None
        or set(parsed) != expected_result_keys
        or parsed.get("schema_version") != "1.0.0"
        or parsed.get("kind") != "elmos.proof-harness.structured-unittest-results"
        or parsed.get("status") != "PASS"
        or parsed.get("discovery")
        != {"start_directory": start_directory, "pattern": pattern}
        or parsed.get("evidence_boundary")
        != {
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        or not isinstance(parsed.get("runner_output"), str)
        or not isinstance(parsed.get("captured_stdout"), str)
        or not isinstance(parsed.get("captured_stderr"), str)
    ):
        raise QualificationError(f"{name} failed")
    totals = parsed.get("totals")
    if not isinstance(totals, Mapping) or set(totals) != set(TEST_TOTAL_KEYS):
        raise QualificationError(f"{name} omitted structured totals")
    expected: dict[str, int] = {}
    for key in TEST_TOTAL_KEYS:
        item = totals[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise QualificationError(f"{name} has invalid structured total: {key}")
        expected[key] = item
    if (
        expected["selected"] < 1
        or expected["selected"] != expected["passed"]
        or any(
            expected[key] != 0
            for key in (
                "failed",
                "errors",
                "skipped",
                "expected_failures",
                "unexpected_successes",
            )
        )
    ):
        raise QualificationError(f"{name} has non-passing outcomes")
    if not expected_sources or any(
        not isinstance(source, str)
        or not source
        or not isinstance(digest, str)
        or len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
        for source, digest in expected_sources.items()
    ):
        raise QualificationError(f"{name} has an invalid expected source inventory")
    outcomes = parsed.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != expected["selected"]:
        raise QualificationError(f"{name} omitted exact source-bound outcomes")
    observed: set[str] = set()
    selectors: set[str] = set()
    expected_outcome_keys = {
        "selector",
        "source_path",
        "source_sha256",
        "selector_source_binding_sha256",
        "status",
        "duration_milliseconds",
    }
    for outcome in outcomes:
        if not isinstance(outcome, Mapping) or set(outcome) != expected_outcome_keys:
            raise QualificationError(f"{name} has an invalid outcome")
        selector = outcome.get("selector")
        source_path = outcome.get("source_path")
        source_digest = outcome.get("source_sha256")
        binding_digest = outcome.get("selector_source_binding_sha256")
        duration = outcome.get("duration_milliseconds")
        if (
            not isinstance(selector, str)
            or not selector
            or selector in selectors
            or not isinstance(source_path, str)
            or source_path not in expected_sources
            or source_digest != expected_sources[source_path]
            or outcome.get("status") != "PASSED"
            or not isinstance(binding_digest, str)
            or isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration < 0
        ):
            raise QualificationError(f"{name} outcome source binding drifted")
        binding = {
            "selector": selector,
            "source_path": source_path,
            "source_sha256": source_digest,
        }
        if binding_digest != "sha256:" + sha256(canonical_bytes(binding)):
            raise QualificationError(f"{name} outcome binding digest drifted")
        selectors.add(selector)
        observed.add(source_path)
    if observed != set(expected_sources):
        raise QualificationError(f"{name} did not execute every fixed test source")
    return expected


def _assert_installation_check(
    raw: Mapping[str, Any], parsed: Mapping[str, Any] | None
) -> None:
    archive = parsed.get("archive") if parsed is not None else None
    installation = parsed.get("installation") if parsed is not None else None
    if (
        isinstance(raw.get("returncode"), bool)
        or raw.get("returncode") != 0
        or parsed is None
        or parsed.get("schema_version") != "1.0.0"
        or parsed.get("package") != f"{PACKAGE_NAME}@{PACKAGE_VERSION}"
        or not isinstance(archive, Mapping)
        or archive.get("sha256") != ARCHIVE_SHA256
        or archive.get("bytes") != ARCHIVE_BYTES
        or parsed.get("action") != "check"
        or not isinstance(installation, Mapping)
        or installation.get("status") != "PASS"
        or parsed.get("implementation_status")
        not in {
            "DECLARED_RUNTIME_UNQUALIFIED",
            "LOCAL_EXECUTED_SELF_ATTESTED",
        }
        or parsed.get("external_runtime_status") != "NOT_RUN"
        or parsed.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise QualificationError("delta installation check failed")


def qualify(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    archive, _ = _safe_repo_bytes(repo_root, ARCHIVE_RELATIVE, limit=ARCHIVE_BYTES)
    if len(archive) != ARCHIVE_BYTES or sha256(archive) != ARCHIVE_SHA256:
        raise QualificationError("delta source archive identity drifted")
    before = engine_inventory(repo_root / ENGINE_RELATIVE)
    fixed_input_paths = qualification_inputs(before)
    fixed_inputs: dict[str, dict[str, Any]] = {}
    for relative in fixed_input_paths:
        payload, _ = _safe_repo_bytes(repo_root, relative)
        fixed_inputs[relative.as_posix()] = {
            "bytes": len(payload),
            "sha256": "sha256:" + sha256(payload),
        }
    binding_payload, _ = _safe_repo_bytes(
        repo_root,
        ACCEPTANCE_BINDINGS_RELATIVE,
        limit=2 * 1024 * 1024,
    )
    acceptance_bindings = _load_acceptance_bindings(binding_payload, archive)

    commands = (
        (
            "delta-engine-tests",
            (
                sys.executable,
                RUNNER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--start-directory",
                (ENGINE_RELATIVE / "tests").as_posix(),
                "--pattern",
                ENGINE_DELTA_TEST_PATTERN,
            ),
            "delta-engine-tests.json",
        ),
        (
            "delta-importer-tests",
            (
                sys.executable,
                RUNNER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--start-directory",
                "tests/proof-driven-harness-v3",
                "--pattern",
                "test_delta_integration.py",
            ),
            "delta-importer-tests.json",
        ),
        (
            "delta-installation-check",
            (
                sys.executable,
                IMPORTER_RELATIVE.as_posix(),
                "--repo-root",
                ".",
                "--check",
            ),
            "delta-installation-check.json",
        ),
    )
    raw_directory = repo_root / RAW_RELATIVE
    raw_records: list[dict[str, Any]] = []
    raw_payloads: dict[str, bytes] = {}
    totals: list[Mapping[str, int]] = []
    engine_outcomes: list[Mapping[str, Any]] = []
    installation_check = "NOT_RUN"
    for name, argv, filename in commands:
        raw, parsed = _run(repo_root, name, argv)
        payload = json_bytes(raw)
        _atomic_write(raw_directory / filename, payload)
        raw_payloads[filename] = payload
        raw_records.append(
            {
                "name": name,
                "path": (Path("qualification/delta-v3.1/raw") / filename).as_posix(),
                "sha256": "sha256:" + sha256(payload),
                "returncode": raw["returncode"],
            }
        )
        if name.endswith("tests"):
            if name == "delta-engine-tests":
                expected_sources = {
                    relative.as_posix(): str(
                        fixed_inputs[relative.as_posix()]["sha256"]
                    )
                    for relative in fixed_input_paths
                    if relative in REQUIRED_ENGINE_DELTA_TESTS
                    or relative in OPTIONAL_ENGINE_DELTA_TESTS
                }
            else:
                expected_sources = {
                    IMPORTER_TEST_RELATIVE.as_posix(): str(
                        fixed_inputs[IMPORTER_TEST_RELATIVE.as_posix()]["sha256"]
                    )
                }
            totals.append(
                _assert_structured(
                    name,
                    raw,
                    parsed,
                    start_directory=(
                        (ENGINE_RELATIVE / "tests").as_posix()
                        if name == "delta-engine-tests"
                        else "tests/proof-driven-harness-v3"
                    ),
                    pattern=(
                        ENGINE_DELTA_TEST_PATTERN
                        if name == "delta-engine-tests"
                        else "test_delta_integration.py"
                    ),
                    expected_sources=expected_sources,
                )
            )
            if name == "delta-engine-tests":
                assert parsed is not None
                engine_outcomes = list(parsed["outcomes"])
        else:
            _assert_installation_check(raw, parsed)
            installation_check = "PASS"
    aggregate = {key: sum(item[key] for item in totals) for key in totals[0]}
    if aggregate["passed"] < 25:
        raise QualificationError(
            "delta qualification requires at least 25 exact local tests"
        )
    acceptance_results = _assert_acceptance_results(
        acceptance_bindings,
        engine_outcomes,
    )
    transport_results = [
        case
        for case in acceptance_results["case_results"]
        if case["skill"] == "elmos-harness-transport-version-negotiation"
    ]
    adapter_profile_negotiation = (
        "PASS"
        if len(transport_results) == EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL
        and all(item["local_result"] == "PASSED" for item in transport_results)
        else "NOT_RUN"
    )
    if adapter_profile_negotiation != "PASS":
        raise QualificationError("adapter profile negotiation coverage is incomplete")
    # The commands run without the promotion lock because installation-check
    # invokes the importer.  Publication then shares the importer's exclusive
    # lock and repeats every engine, input, and raw-log binding before the PASS
    # receipt becomes visible.
    with _exclusive_lock(repo_root):
        archive_after, _ = _safe_repo_bytes(
            repo_root,
            ARCHIVE_RELATIVE,
            limit=ARCHIVE_BYTES,
        )
        if archive_after != archive:
            raise QualificationError(
                "delta source archive changed during qualification"
            )
        after = engine_inventory(repo_root / ENGINE_RELATIVE)
        if before != after:
            raise QualificationError("engine tree changed during delta qualification")
        if qualification_inputs(after) != fixed_input_paths:
            raise QualificationError("delta qualification input inventory changed")
        for relative in fixed_input_paths:
            payload, _ = _safe_repo_bytes(repo_root, relative)
            if fixed_inputs[relative.as_posix()] != {
                "bytes": len(payload),
                "sha256": "sha256:" + sha256(payload),
            }:
                raise QualificationError(
                    f"delta qualification input changed during execution: {relative}"
                )
        binding_after, _ = _safe_repo_bytes(
            repo_root,
            ACCEPTANCE_BINDINGS_RELATIVE,
            limit=2 * 1024 * 1024,
        )
        if _load_acceptance_bindings(binding_after, archive_after) != (
            acceptance_bindings
        ):
            raise QualificationError("acceptance binding changed during qualification")
        for filename, expected_payload in raw_payloads.items():
            payload, _ = _safe_repo_bytes(
                repo_root,
                RAW_RELATIVE / filename,
                limit=MAX_COMMAND_OUTPUT_BYTES,
            )
            if payload != expected_payload:
                raise QualificationError(
                    f"delta qualification raw log changed during execution: {filename}"
                )

        receipt = {
            "schema_version": "1.0.0",
            "kind": "elmos.harness-runtime-assurance-delta.local-qualification",
            "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
            "base_package_version": "3.0.0",
            "composite_version": PACKAGE_VERSION,
            "archive_sha256": ARCHIVE_SHA256,
            "archive_bytes": ARCHIVE_BYTES,
            "engine": {
                "files": len(after),
                "tree_sha256": "sha256:" + sha256(canonical_bytes(after)),
                "inventory": after,
            },
            "inputs": fixed_inputs,
            "raw_logs": raw_records,
            "tests": aggregate,
            "acceptance": acceptance_results,
            "install_roundtrip": installation_check,
            "adapter_profile_negotiation": adapter_profile_negotiation,
            "postgresql17": "NOT_RUN",
            "opa": "NOT_RUN",
            "provider_runtime": "NOT_RUN",
            "remote_executor": "NOT_RUN",
            "target_environment_conformance": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "implementation_status": "LOCAL_EXECUTED_SELF_ATTESTED",
            "status": "PASS",
        }
        receipt_payload = json_bytes(receipt)
        _atomic_write(repo_root / RECEIPT_RELATIVE, receipt_payload)
        published, _ = _safe_repo_bytes(
            repo_root,
            RECEIPT_RELATIVE,
            limit=MAX_COMMAND_OUTPUT_BYTES,
        )
        if published != receipt_payload:
            raise QualificationError("delta qualification receipt publication drifted")
        return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        receipt = qualify(args.repo_root)
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "implementation_status": receipt["implementation_status"],
                    "tests": receipt["tests"],
                    "acceptance_cases": receipt["acceptance"]["local_cases"],
                    "adapter_profile_negotiation": receipt[
                        "adapter_profile_negotiation"
                    ],
                    "external_runtime": "NOT_RUN",
                    "certification": "NOT_CERTIFIED",
                },
                sort_keys=True,
            )
        )
        return 0
    except (QualificationError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc), "certification": "NOT_CERTIFIED"},
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
