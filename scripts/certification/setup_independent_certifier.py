#!/usr/bin/env python3
"""Disabled fail-closed entrypoint: repository-side certifier key generation."""

from __future__ import annotations

import json


def main() -> int:
    print(
        json.dumps(
            {
                "status": "BLOCKED",
                "decision": "NOT_CERTIFIED",
                "external_execution": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "reason": "repository-side certifier key generation is prohibited inside the repository after ELMOS-CERT-KEY-2026-09-13-01",
                "required_action": "Ethan must hold the replacement private key outside the repository, independently replay exact-SHA evidence, and return only the signed request plus authenticated public-key fingerprint",
            },
            indent=2,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
