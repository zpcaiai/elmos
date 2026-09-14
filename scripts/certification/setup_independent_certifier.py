#!/usr/bin/env python3
"""Disabled fail-closed entrypoint for repository-side certifier keys."""

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
                "reason": "repository-side certifier key generation is prohibited after ELMOS-CERT-KEY-2026-09-13-01",
                "required_action": "Ethan must retain the replacement private key outside the repository, replay exact-SHA evidence independently, and return only a signed request plus authenticated public-key fingerprint",
            },
            indent=2,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
