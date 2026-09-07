#!/usr/bin/env python3
"""Emit one fail-closed receipt for the complete active route toolchain tuple.

The central runtime doctor probes individual commands.  That is useful for
installation diagnostics, but it cannot prove that those commands are the
same content-addressed roots consumed by the route engine.  This receipt calls
the engine's exact selectors for every active language and reports their
resolved identities without executing any translation route.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "batch29"))

from route_runtime_metadata import (  # noqa: E402
    EXACT_TOOLCHAIN_ACTIVE_LANGUAGES,
    EXACT_TOOLCHAIN_CONTRACT_SHA256,
    EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES,
    EXACT_TOOLCHAIN_PROFILE_OVERRIDES,
    EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION,
    EXACT_TOOLCHAIN_RECORD_SHA256,
    EXACT_TOOLCHAIN_VERSIONS,
    exact_toolchain_contract_sha256,
    exact_toolchain_record_sha256,
)

from elmos_polyglot_route.models import (  # noqa: E402
    DEPRECATED_LANGUAGES,
    ROUTED_LANGUAGES,
    RouteError,
)
from elmos_polyglot_route.toolchains import (  # noqa: E402
    configured_polyglot_toolchain_root,
    exact_toolchain,
    verify_flutter_build_toolchain,
)

SCHEMA_VERSION = EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION
KIND = "elmos.polyglot-route-exact-toolchain-receipt"
EXPECTED_ACTIVE_LANGUAGES = EXACT_TOOLCHAIN_ACTIVE_LANGUAGES
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


_PORTABLE_ROOT_MARKER = "<polyglot-toolchain-root>"
_PORTABLE_JAVA_HOME_MARKER = "<java21-home>"


def _portable_toolchain_value(value: str, root: Path) -> str:
    """Tokenize the governed install root while preserving all content facts."""

    root_text = os.fspath(root)
    if value == root_text:
        return _PORTABLE_ROOT_MARKER
    prefix = root_text + os.sep
    return value.replace(prefix, _PORTABLE_ROOT_MARKER + "/")


def _portable_toolchain_record(language: str) -> dict[str, Any]:
    toolchain = exact_toolchain(language)  # type: ignore[arg-type]
    if toolchain.language != language:
        raise RouteError(f"EXACT_TOOLCHAIN_LANGUAGE_DRIFT:{language}")
    value = asdict(toolchain)
    value["profile"] = list(toolchain.profile)
    root = configured_polyglot_toolchain_root()
    for field in ("executable", "auxiliary"):
        raw = value.get(field)
        if isinstance(raw, str):
            value[field] = _portable_toolchain_value(raw, root)
    value["profile"] = [
        _portable_toolchain_value(item, root)
        for item in value["profile"]
    ]
    if language == "kotlin":
        if "kotlin-jvm-distribution=temurin" in value["profile"]:
            jvm_homes = [
                item.removeprefix("kotlin-jvm-home=")
                for item in value["profile"]
                if item.startswith("kotlin-jvm-home=")
            ]
            if len(jvm_homes) != 1 or not jvm_homes[0].startswith("/"):
                raise RouteError("EXACT_TOOLCHAIN_KOTLIN_JVM_HOME_INVALID")
            value["profile"] = [
                f"kotlin-jvm-home={_PORTABLE_JAVA_HOME_MARKER}"
                if item == f"kotlin-jvm-home={jvm_homes[0]}"
                else item
                for item in value["profile"]
            ]
    return value


def _expected_toolchain_identity(
    language: str,
    profile: list[str],
) -> tuple[str | None, str | None]:
    expected_version = EXACT_TOOLCHAIN_VERSIONS.get(language)
    expected_record_sha256 = EXACT_TOOLCHAIN_RECORD_SHA256.get(language)
    if language != "kotlin":
        return expected_version, expected_record_sha256
    distributions = [
        item for item in profile if item.startswith("kotlin-jvm-distribution=")
    ]
    if len(distributions) != 1:
        raise RouteError("EXACT_TOOLCHAIN_KOTLIN_JVM_DISTRIBUTION_AMBIGUOUS")
    selector = distributions[0]
    if selector == "kotlin-jvm-distribution=homebrew":
        return expected_version, expected_record_sha256
    override = EXACT_TOOLCHAIN_PROFILE_OVERRIDES.get("kotlin", {}).get(selector)
    if override is None:
        raise RouteError(
            f"EXACT_TOOLCHAIN_KOTLIN_JVM_DISTRIBUTION_UNSUPPORTED:{selector}"
        )
    return override.get("version"), override.get("record_sha256")


def _portable_toolchain(language: str) -> dict[str, Any]:
    value = _portable_toolchain_record(language)
    expected_version, expected_record_sha256 = _expected_toolchain_identity(
        language,
        value["profile"],
    )
    if value.get("version") != expected_version:
        raise RouteError(
            f"EXACT_TOOLCHAIN_VERSION_CONTRACT_MISMATCH:{language}:"
            f"expected={expected_version}:observed={value.get('version')}"
        )
    for field in ("executable_sha256", "auxiliary_sha256"):
        digest = value.get(field)
        if digest is not None and (
            not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None
        ):
            raise RouteError(f"EXACT_TOOLCHAIN_DIGEST_INVALID:{language}:{field}")
    observed_record_sha256 = exact_toolchain_record_sha256(value)
    if (
        not isinstance(expected_record_sha256, str)
        or SHA256_PATTERN.fullmatch(expected_record_sha256) is None
        or observed_record_sha256 != expected_record_sha256
    ):
        raise RouteError(
            f"EXACT_TOOLCHAIN_RECORD_CONTRACT_MISMATCH:{language}:"
            f"expected={expected_record_sha256}:observed={observed_record_sha256}"
        )
    return value


def _validate_exact_toolchain_contract() -> None:
    if (
        EXACT_TOOLCHAIN_RECEIPT_SCHEMA_VERSION != "1.1.0"
        or tuple(EXACT_TOOLCHAIN_VERSIONS) != EXPECTED_ACTIVE_LANGUAGES
        or tuple(EXACT_TOOLCHAIN_RECORD_SHA256) != EXPECTED_ACTIVE_LANGUAGES
        or set(EXACT_TOOLCHAIN_PROFILE_OVERRIDES) != {"kotlin"}
        or EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES != ("javascript",)
        or not isinstance(EXACT_TOOLCHAIN_CONTRACT_SHA256, str)
        or SHA256_PATTERN.fullmatch(EXACT_TOOLCHAIN_CONTRACT_SHA256) is None
        or exact_toolchain_contract_sha256() != EXACT_TOOLCHAIN_CONTRACT_SHA256
    ):
        raise RouteError("EXACT_TOOLCHAIN_CONTRACT_DIGEST_MISMATCH")


def build_receipt() -> dict[str, Any]:
    _validate_exact_toolchain_contract()
    active = tuple(ROUTED_LANGUAGES)
    if active != EXPECTED_ACTIVE_LANGUAGES:
        raise RouteError("ACTIVE_ROUTE_LANGUAGE_SET_DRIFT")
    if tuple(DEPRECATED_LANGUAGES) != EXACT_TOOLCHAIN_DEPRECATED_LANGUAGES:
        raise RouteError("DEPRECATED_ROUTE_LANGUAGE_SET_DRIFT")

    toolchains = [_portable_toolchain(language) for language in active]
    from elmos_polyglot_route.react_analyzer import verify_react_runtime_import

    react_toolchain = exact_toolchain("react")
    react_runtime_receipt = verify_react_runtime_import(react_toolchain)
    flutter_toolchain = exact_toolchain("flutter")
    flutter_build_toolchain_receipt = verify_flutter_build_toolchain(
        flutter_toolchain
    )
    bound_payload = {
        "toolchain_contract_sha256": EXACT_TOOLCHAIN_CONTRACT_SHA256,
        "active_languages": list(active),
        "deprecated_languages": list(DEPRECATED_LANGUAGES),
        "toolchains": toolchains,
        "react_runtime_receipt": react_runtime_receipt,
        "flutter_build_toolchain_receipt": flutter_build_toolchain_receipt,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": "READY",
        "claim_ceiling": "TOOLCHAIN_READY",
        "route_execution_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        **bound_payload,
        "receipt_sha256": _canonical_sha256(bound_payload),
    }


def main() -> int:
    try:
        receipt = build_receipt()
    except (OSError, RouteError, ValueError) as error:
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": "BLOCKED",
            "claim_ceiling": "NOT_RUN",
            "route_execution_status": "NOT_RUN",
            "independent_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "blocking_reason": str(error),
        }
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
