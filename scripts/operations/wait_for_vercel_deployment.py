#!/usr/bin/env python3
"""Resolve the newest Vercel deployment for one exact Git commit.

The deployment smoke must not probe a mutable alias or fall back to an older
successful deployment while the newest deployment for the commit is pending or
failed. This helper only reads GitHub deployment records; it performs no
deployment or provider mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any


API_ROOT = "https://api.github.com"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_GITHUB_ENV_BYTES = 1024 * 1024
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERCEL_HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.vercel\.app$")
TERMINAL_FAILURES = frozenset({"error", "failure", "inactive"})


class DeploymentResolutionError(RuntimeError):
    """A stable, non-secret deployment resolution failure."""


def _record_order(record: dict[str, Any]) -> tuple[str, int]:
    created_at = record.get("created_at")
    identifier = record.get("id")
    return (
        created_at if isinstance(created_at, str) else "",
        identifier if type(identifier) is int else -1,
    )


def _deployment_url(value: object) -> str:
    if not isinstance(value, str):
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_MISSING")
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_UNTRUSTED") from error
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or VERCEL_HOST_PATTERN.fullmatch(hostname) is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_URL_UNTRUSTED")
    return value.rstrip("/")


def _latest_status(statuses: object) -> dict[str, Any] | None:
    if not isinstance(statuses, list):
        raise DeploymentResolutionError("GITHUB_DEPLOYMENT_STATUSES_INVALID")
    records = [
        item
        for item in statuses
        if isinstance(item, dict)
        and isinstance(item.get("creator"), dict)
        and item["creator"].get("login") == "vercel[bot]"
    ]
    return max(records, key=_record_order) if records else None


def _newest_exact_vercel_deployment(deployments: object, sha: str) -> dict[str, Any] | None:
    if not isinstance(deployments, list):
        raise DeploymentResolutionError("GITHUB_DEPLOYMENTS_INVALID")
    records = [
        item
        for item in deployments
        if isinstance(item, dict)
        and item.get("sha") == sha
        and item.get("task") == "deploy"
        and isinstance(item.get("creator"), dict)
        and item["creator"].get("login") == "vercel[bot]"
        and type(item.get("id")) is int
    ]
    return max(records, key=_record_order) if records else None


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
    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise DeploymentResolutionError("GITHUB_REPOSITORY_INVALID")
    if COMMIT_PATTERN.fullmatch(sha) is None:
        raise DeploymentResolutionError("GITHUB_SHA_INVALID")
    if not 0 < timeout_seconds <= 1_800 or not 0 < poll_seconds <= 60:
        raise DeploymentResolutionError("DEPLOYMENT_WAIT_INTERVAL_INVALID")

    deadline = monotonic() + timeout_seconds
    encoded_sha = urllib.parse.quote(sha, safe="")
    while True:
        deployment = _newest_exact_vercel_deployment(
            fetch_json(f"/repos/{repository}/deployments?sha={encoded_sha}&per_page=100"),
            sha,
        )
        if deployment is not None:
            deployment_id = int(deployment["id"])
            status = _latest_status(
                fetch_json(f"/repos/{repository}/deployments/{deployment_id}/statuses?per_page=100")
            )
            if status is not None:
                state = status.get("state")
                if state == "success":
                    return _deployment_url(status.get("environment_url"))
                if state in TERMINAL_FAILURES:
                    raise DeploymentResolutionError(
                        f"VERCEL_DEPLOYMENT_{str(state).upper()}"
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
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, urllib.error.URLError) as error:
            raise DeploymentResolutionError("GITHUB_DEPLOYMENT_API_FAILED") from error
        if len(payload) > MAX_RESPONSE_BYTES:
            raise DeploymentResolutionError("GITHUB_DEPLOYMENT_API_RESPONSE_TOO_LARGE")
        try:
            return json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DeploymentResolutionError("GITHUB_DEPLOYMENT_API_RESPONSE_INVALID") from error

    return fetch


def _append_github_environment(path: Path, url: str) -> None:
    if not path.is_absolute():
        raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE")
    try:
        before = path.lstat()
    except OSError as error:
        raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_GITHUB_ENV_BYTES
    ):
        raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE")
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE") from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_size > MAX_GITHUB_ENV_BYTES
        ):
            raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE")
        payload = f"ELMOS_E2E_BASE_URL={url}\n".encode("utf-8")
        if opened.st_size + len(payload) > MAX_GITHUB_ENV_BYTES:
            raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE")
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise DeploymentResolutionError("GITHUB_ENV_FILE_WRITE_INCOMPLETE")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise DeploymentResolutionError("GITHUB_ENV_FILE_UNSAFE")
    finally:
        os.close(descriptor)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--github-env", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=10)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise DeploymentResolutionError("GITHUB_TOKEN_MISSING")
    url = wait_for_deployment(
        args.repository,
        args.sha,
        fetch_json=_github_fetcher(token),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    _append_github_environment(args.github_env, url)
    print(f"Resolved exact Vercel deployment for {args.sha}: {url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeploymentResolutionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
