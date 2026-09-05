#!/usr/bin/env python3
"""Wait for the exact commit's successful Vercel deployment.

The deployment smoke must never probe a mutable production alias while the
commit under test is still building. GitHub's deployment record binds the
probe to the Vercel URL that actually corresponds to the requested SHA.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any


API_ROOT = "https://api.github.com"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
TERMINAL_FAILURES = frozenset({"error", "failure", "inactive"})


class DeploymentResolutionError(RuntimeError):
    pass


def _deployment_url(value: object) -> str:
    if not isinstance(value, str):
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_MISSING")
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_UNTRUSTED") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not parsed.hostname.endswith(".vercel.app")
    ):
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_UNTRUSTED")
    return value.rstrip("/")


def _latest_status(statuses: object) -> dict[str, Any] | None:
    if not isinstance(statuses, list):
        raise DeploymentResolutionError("GITHUB_DEPLOYMENT_STATUSES_INVALID")
    records = [item for item in statuses if isinstance(item, dict)]
    if not records:
        return None
    return max(records, key=lambda item: str(item.get("created_at", "")))


def wait_for_deployment(
    repository: str,
    sha: str,
    *,
    fetch_json: Callable[[str], Any],
    timeout_seconds: float,
    poll_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = monotonic() + timeout_seconds
    encoded_sha = urllib.parse.quote(sha, safe="")
    while True:
        deployments = fetch_json(
            f"/repos/{repository}/deployments?sha={encoded_sha}&per_page=100"
        )
        if not isinstance(deployments, list):
            raise DeploymentResolutionError("GITHUB_DEPLOYMENTS_INVALID")
        records = sorted(
            (
                item
                for item in deployments
                if isinstance(item, dict)
                and item.get("task") == "deploy"
                and isinstance(item.get("creator"), dict)
                and item["creator"].get("login") == "vercel[bot]"
            ),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
        for deployment in records:
            deployment_id = deployment.get("id")
            if type(deployment_id) is not int:
                continue
            status = _latest_status(
                fetch_json(f"/repos/{repository}/deployments/{deployment_id}/statuses")
            )
            if status is None:
                continue
            state = status.get("state")
            if state == "success":
                return _deployment_url(status.get("environment_url"))
            if state in TERMINAL_FAILURES:
                description = (
                    str(status.get("description", "deployment failed"))
                    .replace("\r", " ")
                    .replace("\n", " ")[:240]
                )
                raise DeploymentResolutionError(
                    f"VERCEL_DEPLOYMENT_{str(state).upper()}:{description}"
                )
        if monotonic() >= deadline:
            raise DeploymentResolutionError("VERCEL_DEPLOYMENT_TIMEOUT")
        sleep(poll_seconds)


def _github_fetcher(token: str) -> Callable[[str], Any]:
    def fetch(path: str) -> Any:
        request = urllib.request.Request(
            API_ROOT + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "elmos-vercel-deployment-smoke",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            return json.load(response)

    return fetch


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=10)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise DeploymentResolutionError("GITHUB_TOKEN_MISSING")
    if not REPOSITORY.fullmatch(args.repository):
        raise DeploymentResolutionError("GITHUB_REPOSITORY_INVALID")
    if not COMMIT_SHA.fullmatch(args.sha):
        raise DeploymentResolutionError("GITHUB_SHA_INVALID")
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        raise DeploymentResolutionError("DEPLOYMENT_WAIT_INTERVAL_INVALID")

    url = wait_for_deployment(
        args.repository,
        args.sha,
        fetch_json=_github_fetcher(token),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    with args.github_env.open("a", encoding="utf-8") as output:
        output.write(f"ELMOS_E2E_BASE_URL={url}\n")
    print(f"Resolved exact Vercel deployment for {args.sha}: {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeploymentResolutionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
