#!/usr/bin/env python3
"""Fixed production launcher for the Spring evidence and launch Make targets.

The launcher accepts one allowlisted target and no Make arguments. It verifies
the independently approved immutable bundle before executing root-owned make
with one exact makefile, so caller flags, MAKEFLAGS and extra ``-f`` inputs can
never expand the production parser surface.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_VALIDATOR = (
    ROOT / "deploy/production/runner/validate_spring_runner_topology.py"
)
TRUSTED_MAKE = Path("/usr/bin/make")
BASE_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
COMMON_INPUTS = frozenset(
    {
        "SPRING_EXPECTED_REVISION",
        "SPRING_OBSERVER_BUNDLE_DIGEST",
    }
)
TARGET_INPUTS = {
    "spring-launch-gate": COMMON_INPUTS
    | {
        "SPRING_EXTERNAL_EVIDENCE",
        "SPRING_ENV_FILE",
        "ELMOS_ENV_FILE",
        "ELMOS_WEB_ENV_FILE",
        "SPRING_TRUST_STORE",
        "SPRING_TRUST_STORE_DIGEST",
        "SPRING_EVIDENCE_ROOT",
        "SPRING_ENVIRONMENT_ID",
        "SPRING_DEPLOYMENT_ID",
        "SPRING_PROVIDER",
        "SPRING_REGION",
        "SPRING_ENVIRONMENT_CLASS",
        "SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST",
    },
    "spring-web-runtime-attestation": COMMON_INPUTS
    | {
        "SPRING_WEB_CONTAINER",
        "SPRING_WEB_IMAGE_DIGEST",
        "SPRING_WORKER_CONTAINER",
        "SPRING_WORKER_IMAGE_DIGEST",
        "SPRING_WEB_COLLECTOR_ID",
        "SPRING_WEB_RUNTIME_ATTESTATION_OUTPUT",
    },
}
SAFE_VALUE = re.compile(r"[A-Za-z0-9._~:/@,+%=?&-]+")


class ProductionGateLauncherError(ValueError):
    """The fixed production launch contract was not satisfied."""


def _load_topology_validator() -> types.ModuleType:
    expected = TOPOLOGY_VALIDATOR.resolve(strict=True)
    name = "_elmos_spring_production_topology_validator"
    specification = importlib.util.spec_from_file_location(name, expected)
    if specification is None or specification.loader is None:
        raise ProductionGateLauncherError(
            "immutable topology validator could not be loaded"
        )
    module = importlib.util.module_from_spec(specification)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    origin = Path(str(getattr(module, "__file__", ""))).resolve(strict=True)
    if origin != expected:
        raise ProductionGateLauncherError("topology validator origin drift")
    return module


def _controlled_environment(
    target: str, environment: Mapping[str, str]
) -> dict[str, str]:
    required = TARGET_INPUTS.get(target)
    if required is None:
        raise ProductionGateLauncherError("unsupported production Spring target")
    allowed = required | BASE_ENVIRONMENT.keys()
    unknown = sorted(set(environment) - set(allowed))
    if unknown:
        raise ProductionGateLauncherError(
            "production launcher environment contains unknown keys: "
            + ", ".join(unknown)
        )
    for name, expected in BASE_ENVIRONMENT.items():
        if environment.get(name) != expected:
            raise ProductionGateLauncherError(
                f"production launcher requires exact {name}={expected}"
            )
    values: dict[str, str] = dict(BASE_ENVIRONMENT)
    for name in sorted(required):
        value = environment.get(name)
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or SAFE_VALUE.fullmatch(value) is None
        ):
            raise ProductionGateLauncherError(
                f"production launcher requires one safe non-empty {name} value"
            )
        values[name] = value
    return values


def launch(target: str, environment: Mapping[str, str]) -> None:
    controlled = _controlled_environment(target, environment)
    topology = _load_topology_validator()
    errors = topology.validate_observer_execution(
        revision=controlled["SPRING_EXPECTED_REVISION"],
        expected_digest=controlled["SPRING_OBSERVER_BUNDLE_DIGEST"],
    )
    if errors:
        raise ProductionGateLauncherError(
            "immutable production bundle rejected: " + "; ".join(errors)
        )
    topology.validate_trusted_system_executable(
        TRUSTED_MAKE, label="production GNU make"
    )
    os.execve(
        str(TRUSTED_MAKE),
        [
            str(TRUSTED_MAKE),
            "--no-print-directory",
            "-C",
            str(ROOT),
            "-f",
            "Makefile.batch30",
            target,
        ],
        controlled,
    )
    raise ProductionGateLauncherError("production GNU make unexpectedly returned")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or arguments[0] not in TARGET_INPUTS:
        print(
            "ERROR: provide exactly one supported production Spring target and no Make flags",
            file=sys.stderr,
        )
        return 2
    try:
        launch(arguments[0], os.environ)
    except (OSError, RuntimeError, ProductionGateLauncherError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
