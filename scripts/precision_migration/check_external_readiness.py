#!/usr/bin/env python3
"""Fail-closed preflight for independent, HSM, customer, canary, and production evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


REQUIREMENTS = {
    "independent_verifier_trust_store": "ELMOS_PRECISION_INDEPENDENT_TRUST_STORE",
    "hsm_provider": "ELMOS_PRECISION_HSM_PROVIDER",
    "hsm_key_reference": "ELMOS_PRECISION_HSM_KEY_REFERENCE",
    "customer_workload_manifest": "ELMOS_PRECISION_CUSTOMER_WORKLOAD_MANIFEST",
    "canary_plan": "ELMOS_PRECISION_CANARY_PLAN",
    "rollback_plan": "ELMOS_PRECISION_ROLLBACK_PLAN",
    "production_authorization": "ELMOS_PRECISION_PRODUCTION_AUTHORIZATION",
}
PATH_REQUIREMENTS = {
    "independent_verifier_trust_store",
    "customer_workload_manifest",
    "canary_plan",
    "rollback_plan",
    "production_authorization",
}


def file_observation(value: str) -> dict[str, Any]:
    supplied = Path(value).expanduser()
    if supplied.is_symlink():
        return {"state": "BLOCKED", "reason": "symlink is forbidden"}
    try:
        resolved = supplied.resolve(strict=True)
    except OSError:
        return {"state": "NOT_RUN", "reason": "configured file is unavailable"}
    if not resolved.is_file():
        return {"state": "BLOCKED", "reason": "configured path is not a regular file"}
    content = resolved.read_bytes()
    return {
        "state": "AVAILABLE_NOT_EXECUTED",
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks: dict[str, Any] = {}
    for name, variable in REQUIREMENTS.items():
        value = os.environ.get(variable, "").strip()
        if not value:
            checks[name] = {"state": "NOT_RUN", "reason": f"{variable} is not configured"}
        elif name in PATH_REQUIREMENTS:
            checks[name] = file_observation(value)
        else:
            checks[name] = {"state": "CONFIGURED_NOT_EXECUTED", "secret_value_recorded": False}
    ready = all(item["state"] in {"AVAILABLE_NOT_EXECUTED", "CONFIGURED_NOT_EXECUTED"} for item in checks.values())
    result = {
        "schema_version": 1,
        "status": "READY_FOR_AUTHORIZED_EXTERNAL_EXECUTION" if ready else "BLOCKED",
        "checks": checks,
        "external_operations_executed": False,
        "independent_verification": "NOT_RUN",
        "hsm_signing": "NOT_RUN",
        "customer_workload": "NOT_RUN",
        "canary": "NOT_RUN",
        "rollback": "NOT_RUN",
        "production_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
