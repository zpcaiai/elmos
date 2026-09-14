#!/usr/bin/env python3
"""Wait for the exact commit's successful Vercel deployment.

The deployment smoke must never probe a mutable production alias while the
commit under test is still building. GitHub's deployment record first binds
the probe to the requested SHA. Once that exact production deployment is
successful, the smoke uses the public production domain because Vercel's
generated production deployment URL remains protected under Standard
Protection.
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
DEFAULT_TIMEOUT_SECONDS = 1_800
MAXIMUM_EQUIVALENT_ANCESTORS = 32


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


def _tree_entry(tree: object, path: str, object_type: str) -> str:
    if not isinstance(tree, dict) or not isinstance(tree.get("tree"), list):
        raise DeploymentResolutionError("GITHUB_GIT_TREE_INVALID")
    matches = [
        item
        for item in tree["tree"]
        if isinstance(item, dict)
        and item.get("path") == path
        and item.get("type") == object_type
        and isinstance(item.get("sha"), str)
        and COMMIT_SHA.fullmatch(item["sha"])
    ]
    if len(matches) != 1:
        raise DeploymentResolutionError("VERCEL_DEPLOYMENT_SURFACE_INVALID")
    return str(matches[0]["sha"])


def _deployment_surface_identity(
    repository: str,
    sha: str,
    fetch_json: Callable[[str], Any],
) -> tuple[str, str]:
    encoded_sha = urllib.parse.quote(sha, safe="")
    root_tree = fetch_json(f"/repos/{repository}/git/trees/{encoded_sha}")
    ignore_sha = _tree_entry(root_tree, ".vercelignore", "blob")
    apps_sha = _tree_entry(root_tree, "apps", "tree")
    apps_tree = fetch_json(f"/repos/{repository}/git/trees/{apps_sha}")
    web_console_sha = _tree_entry(apps_tree, "web-console", "tree")
    return web_console_sha, ignore_sha


def _vercel_commit_status_succeeded(
    repository: str,
    sha: str,
    fetch_json: Callable[[str], Any],
) -> bool:
    encoded_sha = urllib.parse.quote(sha, safe="")
    combined = fetch_json(f"/repos/{repository}/commits/{encoded_sha}/status")
    if not isinstance(combined, dict) or not isinstance(combined.get("statuses"), list):
        raise DeploymentResolutionError("GITHUB_COMMIT_STATUS_INVALID")
    statuses = [
        item
        for item in combined["statuses"]
        if isinstance(item, dict) and item.get("context") == "Vercel"
    ]
    if not statuses:
        return False
    latest = max(statuses, key=lambda item: str(item.get("updated_at", "")))
    target = latest.get("target_url")
    if not isinstance(target, str):
        return False
    parsed = urllib.parse.urlsplit(target)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        latest.get("state") == "success"
        and parsed.scheme == "https"
        and parsed.hostname == "vercel.com"
        and not parsed.username
        and not parsed.password
        and port is None
        and not parsed.query
        and not parsed.fragment
        and len(tuple(part for part in parsed.path.split("/") if part)) >= 3
    )


def _commit_parents(
    repository: str,
    sha: str,
    fetch_json: Callable[[str], Any],
) -> tuple[str, ...]:
    encoded_sha = urllib.parse.quote(sha, safe="")
    commit = fetch_json(f"/repos/{repository}/commits/{encoded_sha}")
    if not isinstance(commit, dict) or not isinstance(commit.get("parents"), list):
        raise DeploymentResolutionError("GITHUB_COMMIT_INVALID")
    parents = tuple(
        str(item["sha"])
        for item in commit["parents"]
        if isinstance(item, dict)
        and isinstance(item.get("sha"), str)
        and COMMIT_SHA.fullmatch(item["sha"])
    )
    if len(parents) != len(commit["parents"]):
        raise DeploymentResolutionError("GITHUB_COMMIT_PARENTS_INVALID")
    return parents


def _matching_vercel_deployments(
    deployments: object,
    required_environment: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(deployments, list):
        raise DeploymentResolutionError("GITHUB_DEPLOYMENTS_INVALID")
    return sorted(
        (
            item
            for item in deployments
            if isinstance(item, dict)
            and item.get("task") == "deploy"
            and isinstance(item.get("creator"), dict)
            and item["creator"].get("login") == "vercel[bot]"
            and (
                required_environment is None
                or (
                    isinstance(item.get("environment"), str)
                    and item["environment"].casefold()
                    == required_environment.casefold()
                )
            )
        ),
        key=lambda item: str(item.get("created_at", "")),
        reverse=True,
    )


def _equivalent_ancestor_deployment_url(
    repository: str,
    sha: str,
    *,
    fetch_json: Callable[[str], Any],
    required_environment: str | None,
    production_url: str | None,
) -> str | None:
    """Reuse only an ancestor deployment with byte-identical Vercel inputs."""

    current_surface = _deployment_surface_identity(repository, sha, fetch_json)
    queue = list(_commit_parents(repository, sha, fetch_json))
    visited = {sha}
    examined = 0
    while queue and examined < MAXIMUM_EQUIVALENT_ANCESTORS:
        candidate_sha = queue.pop(0)
        if candidate_sha in visited:
            continue
        visited.add(candidate_sha)
        examined += 1
        if (
            _deployment_surface_identity(repository, candidate_sha, fetch_json)
            == current_surface
        ):
            encoded_candidate = urllib.parse.quote(candidate_sha, safe="")
            deployments = _matching_vercel_deployments(
                fetch_json(
                    f"/repos/{repository}/deployments?sha={encoded_candidate}&per_page=100"
                ),
                required_environment,
            )
            for deployment in deployments:
                deployment_id = deployment.get("id")
                if type(deployment_id) is not int:
                    continue
                status = _latest_status(
                    fetch_json(
                        f"/repos/{repository}/deployments/{deployment_id}/statuses"
                    )
                )
                if status is not None and status.get("state") == "success":
                    exact_url = _deployment_url(status.get("environment_url"))
                    if deployment.get("environment") == "Production" and production_url:
                        return _deployment_url(production_url)
                    return exact_url
        queue.extend(_commit_parents(repository, candidate_sha, fetch_json))
    return None


def wait_for_deployment(
    repository: str,
    sha: str,
    *,
    fetch_json: Callable[[str], Any],
    timeout_seconds: float,
    poll_seconds: float,
    production_url: str | None = None,
    required_environment: str | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = monotonic() + timeout_seconds
    encoded_sha = urllib.parse.quote(sha, safe="")
    equivalent_ancestor_checked = False
    while True:
        deployments = fetch_json(
            f"/repos/{repository}/deployments?sha={encoded_sha}&per_page=100"
        )
        records = _matching_vercel_deployments(
            deployments,
            required_environment,
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
                exact_url = _deployment_url(status.get("environment_url"))
                if deployment.get("environment") == "Production" and production_url:
                    return _deployment_url(production_url)
                return exact_url
            if state in TERMINAL_FAILURES:
                description = (
                    str(status.get("description", "deployment failed"))
                    .replace("\r", " ")
                    .replace("\n", " ")[:240]
                )
                raise DeploymentResolutionError(
                    f"VERCEL_DEPLOYMENT_{str(state).upper()}:{description}"
                )
        if (
            records
            and not equivalent_ancestor_checked
            and _vercel_commit_status_succeeded(repository, sha, fetch_json)
        ):
            equivalent_ancestor_checked = True
            equivalent_url = _equivalent_ancestor_deployment_url(
                repository,
                sha,
                fetch_json=fetch_json,
                required_environment=required_environment,
                production_url=production_url,
            )
            if equivalent_url is not None:
                return equivalent_url
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
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="bounded wait for an exact-SHA deployment (default: 1800 seconds)",
    )
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--production-url")
    parser.add_argument(
        "--required-environment",
        choices=("Production", "Preview"),
        help="accept only the exact SHA's Vercel Production or Preview deployment",
    )
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
        production_url=args.production_url,
        required_environment=args.required_environment,
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
