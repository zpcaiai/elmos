"""Production-ready GitLab API Client & Webhook Ingestor for PR Self-Healing.

Supports:
- Webhook secret token verification via X-Gitlab-Token
- REST endpoints for Projects, Branches, Commits, Merge Requests, Discussions, Notes, Pipelines
- Dual transport: Live HTTP via urllib.request (zero dependencies) and hermetic Mock/Replay transport for air-gapped CI
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import logging
import os
import re
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .scm_models import (
    CIEventKind,
    InlineComment,
    MergeRequestInfo,
    SCMProvider,
    WebhookEvent,
    WebhookSignatureValidationResult,
)

logger = logging.getLogger("elmos.autonomous_qa.gitlab")


class GitLabAPIError(Exception):
    """Raised when GitLab API request fails."""

    def __init__(self, message: str, status_code: int = 500, response_data: Any = None) -> None:
        super().__init__(f"GitLab API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.response_data = response_data


class GitLabTransport:
    """Pluggable transport interface for GitLab API requests."""

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        data: bytes | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        raise NotImplementedError


class LiveGitLabHTTPTransport(GitLabTransport):
    """Standard live HTTP transport using urllib.request."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        data: bytes | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        req = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, resp_headers, resp.read()
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, resp_headers, exc.read()
        except Exception as exc:
            raise GitLabAPIError(f"Network transport error: {exc}", status_code=502) from exc


class MockGitLabTransport(GitLabTransport):
    """Hermetic in-memory mock transport for deterministic tests and offline execution."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[str, Mapping[str, str], bytes | None], tuple[int, Mapping[str, str], bytes]]] = {}
        self.call_history: list[dict[str, Any]] = []
        self.storage: dict[str, Any] = {
            "merge_requests": {},
            "branches": {"main": "0000000000000000000000000000000000000001"},
            "notes": [],
            "discussions": [],
            "statuses": {},
        }

    def register(
        self,
        pattern: str,
        handler: Callable[[str, Mapping[str, str], bytes | None], tuple[int, Mapping[str, str], bytes]],
    ) -> None:
        self.handlers[pattern] = handler

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        data: bytes | None = None,
    ) -> tuple[int, Mapping[str, str], bytes]:
        self.call_history.append({
            "method": method,
            "url": url,
            "headers": dict(headers),
            "data": data,
        })
        for pattern, handler in self.handlers.items():
            if re.search(pattern, url):
                return handler(method, headers, data)

        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path

        # Merge requests: GET/POST /api/v4/projects/{id}/merge_requests
        if re.search(r"/api/v4/projects/[^/]+/merge_requests$", path):
            if method == "POST":
                payload = json.loads(data.decode("utf-8")) if data else {}
                mr_iid = len(self.storage["merge_requests"]) + 1
                mr_id = mr_iid + 5000
                mr_data = {
                    "id": mr_id,
                    "iid": mr_iid,
                    "title": payload.get("title", "Auto Fix MR"),
                    "description": payload.get("description", ""),
                    "web_url": f"https://gitlab.com/test-org/test-repo/-/merge_requests/{mr_iid}",
                    "source_branch": payload.get("source_branch", "fix-branch"),
                    "target_branch": payload.get("target_branch", "main"),
                    "state": "opened",
                    "labels": payload.get("labels", []),
                }
                self.storage["merge_requests"][mr_iid] = mr_data
                return 201, {"content-type": "application/json"}, json.dumps(mr_data).encode("utf-8")
            elif method == "GET":
                return 200, {"content-type": "application/json"}, json.dumps(list(self.storage["merge_requests"].values())).encode("utf-8")

        # Specific Merge Request: GET/PUT /api/v4/projects/{id}/merge_requests/{iid}
        mr_match = re.search(r"/api/v4/projects/[^/]+/merge_requests/(\d+)$", path)
        if mr_match:
            mr_iid = int(mr_match.group(1))
            if method == "GET":
                mr_data = self.storage["merge_requests"].get(mr_iid)
                if mr_data:
                    return 200, {"content-type": "application/json"}, json.dumps(mr_data).encode("utf-8")
                return 404, {"content-type": "application/json"}, b'{"message": "404 Not found"}'
            elif method == "PUT":
                payload = json.loads(data.decode("utf-8")) if data else {}
                mr_data = self.storage["merge_requests"].setdefault(mr_iid, {})
                mr_data.update(payload)
                return 200, {"content-type": "application/json"}, json.dumps(mr_data).encode("utf-8")

        # Branches: POST /api/v4/projects/{id}/repository/branches
        if re.search(r"/api/v4/projects/[^/]+/repository/branches$", path) and method == "POST":
            payload = json.loads(data.decode("utf-8")) if data else {}
            branch_name = payload.get("branch", "")
            ref = payload.get("ref", "")
            self.storage["branches"][branch_name] = ref
            res = {"name": branch_name, "commit": {"id": ref}}
            return 201, {"content-type": "application/json"}, json.dumps(res).encode("utf-8")

        # Discussions / Notes: POST /api/v4/projects/{id}/merge_requests/{iid}/discussions or /notes
        if re.search(r"/api/v4/projects/[^/]+/merge_requests/\d+/(?:discussions|notes)$", path) and method == "POST":
            payload = json.loads(data.decode("utf-8")) if data else {}
            note_id = len(self.storage["notes"]) + 1
            note_data = {
                "id": note_id,
                "body": payload.get("body", ""),
            }
            self.storage["notes"].append(note_data)
            return 201, {"content-type": "application/json"}, json.dumps(note_data).encode("utf-8")

        # Accept MR: PUT /api/v4/projects/{id}/merge_requests/{iid}/merge
        if re.search(r"/api/v4/projects/[^/]+/merge_requests/\d+/merge$", path) and method == "PUT":
            return 200, {"content-type": "application/json"}, b'{"state": "merged"}'

        return 200, {"content-type": "application/json"}, b'{"status": "ok"}'


class GitLabClient:
    """Industrial GitLab client executing MR self-healing operations."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://gitlab.com",
        transport: GitLabTransport | None = None,
    ) -> None:
        self.token = token or os.environ.get("GITLAB_TOKEN", "mock-gitlab-token")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or (LiveGitLabHTTPTransport() if token and not token.startswith("mock") else MockGitLabTransport())

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "ELMOS-Autonomous-QA-Engine/1.1.0",
        }
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def _send(self, method: str, path: str, payload: Any = None) -> Any:
        url = f"{self.base_url}/api/v4{path}" if not path.startswith("/api/v4") else f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"

        status, resp_headers, body = self.transport.request(method, url, headers, data)
        if status not in (200, 201, 202, 204):
            error_text = body.decode("utf-8", errors="replace")
            raise GitLabAPIError(f"HTTP {status}: {error_text}", status_code=status, response_data=error_text)

        if not body or status == 204:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise GitLabAPIError("Invalid JSON received from GitLab API", status_code=502) from exc

    # ------------------ Webhook Verification ------------------

    @staticmethod
    def verify_webhook_token(token_header: str | None, expected_secret_token: str) -> WebhookSignatureValidationResult:
        """Verify secret token from X-Gitlab-Token header."""
        if not token_header:
            return WebhookSignatureValidationResult(
                valid=False,
                provider=SCMProvider.GITLAB,
                reason="Missing X-Gitlab-Token header",
            )
        if hmac.compare_digest(token_header.strip(), expected_secret_token.strip()):
            return WebhookSignatureValidationResult(
                valid=True,
                provider=SCMProvider.GITLAB,
                reason="GitLab token validated successfully",
            )
        return WebhookSignatureValidationResult(
            valid=False,
            provider=SCMProvider.GITLAB,
            reason="GitLab token mismatch",
        )

    # ------------------ Webhook Ingestion ------------------

    @staticmethod
    def parse_webhook_event(event_type: str, payload: Mapping[str, Any]) -> WebhookEvent:
        """Normalize GitLab webhook payload into canonical WebhookEvent."""
        project = payload.get("project", {})
        repo_owner = project.get("namespace", "unknown")
        repo_name = project.get("name", "unknown")
        repo_url = project.get("web_url", f"https://gitlab.com/{repo_owner}/{repo_name}")
        sender = payload.get("user", {}).get("username", "unknown")

        object_kind = payload.get("object_kind", event_type)
        event_id = str(payload.get("checkout_sha") or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16])

        if object_kind == "merge_request":
            kind = CIEventKind.MERGE_REQUEST
            attrs = payload.get("object_attributes", {})
            mr_iid = attrs.get("iid")
            commit_sha = attrs.get("last_commit", {}).get("id", "")
            target_branch = attrs.get("target_branch", "main")
            source_branch = attrs.get("source_branch", "")
            ref = f"refs/merge-requests/{mr_iid}/head"
        elif object_kind == "pipeline":
            kind = CIEventKind.PIPELINE
            attrs = payload.get("object_attributes", {})
            commit_sha = attrs.get("sha", "")
            ref = attrs.get("ref", "refs/heads/main")
            target_branch = attrs.get("ref", "main")
            source_branch = attrs.get("ref", "")
            mr_iid = None
        else:
            kind = CIEventKind.PUSH
            commit_sha = payload.get("after", "")
            ref = payload.get("ref", "refs/heads/main")
            target_branch = "main"
            source_branch = ""
            mr_iid = None

        return WebhookEvent(
            event_id=event_id,
            provider=SCMProvider.GITLAB,
            event_kind=kind,
            repository_owner=repo_owner,
            repository_name=repo_name,
            repository_url=repo_url,
            ref=ref,
            commit_sha=commit_sha,
            sender=sender,
            raw_payload=payload,
            merge_request_iid=mr_iid,
            target_branch=target_branch,
            source_branch=source_branch,
        )

    # ------------------ SCM Operations ------------------

    def create_branch(self, project_id: str | int, branch_name: str, base_ref: str) -> dict[str, Any]:
        """Create a new branch in repository."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/repository/branches"
        payload = {"branch": branch_name, "ref": base_ref}
        return self._send("POST", path, payload)

    def create_merge_request(
        self,
        project_id: str | int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        labels: Sequence[str] = (),
        remove_source_branch: bool = True,
    ) -> MergeRequestInfo:
        """Create a Merge Request on GitLab."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests"
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "labels": ",".join(labels) if labels else "",
            "remove_source_branch": remove_source_branch,
        }
        res = self._send("POST", path, payload)
        return MergeRequestInfo(
            iid=res.get("iid", 0),
            id=res.get("id", 0),
            title=res.get("title", title),
            description=res.get("description", description),
            web_url=res.get("web_url", ""),
            source_branch=source_branch,
            target_branch=target_branch,
            state=res.get("state", "opened"),
            labels=res.get("labels", list(labels)),
        )

    def get_merge_request(self, project_id: str | int, mr_iid: int) -> MergeRequestInfo:
        """Fetch details of an existing Merge Request."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests/{mr_iid}"
        res = self._send("GET", path)
        return MergeRequestInfo(
            iid=res.get("iid", mr_iid),
            id=res.get("id", mr_iid),
            title=res.get("title", ""),
            description=res.get("description", ""),
            web_url=res.get("web_url", ""),
            source_branch=res.get("source_branch", ""),
            target_branch=res.get("target_branch", ""),
            state=res.get("state", "opened"),
            labels=res.get("labels", []),
        )

    def post_mr_note(self, project_id: str | int, mr_iid: int, body: str) -> dict[str, Any]:
        """Post a comment/note to GitLab MR timeline."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests/{mr_iid}/notes"
        return self._send("POST", path, {"body": body})

    def accept_merge_request(self, project_id: str | int, mr_iid: int) -> dict[str, Any]:
        """Accept and merge the given merge request."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests/{mr_iid}/merge"
        return self._send("PUT", path)

    def set_commit_status(
        self,
        project_id: str | int,
        sha: str,
        state: str,
        ref: str = "main",
        name: str = "default",
        description: str = "",
    ) -> dict[str, Any]:
        """Set build/commit status on GitLab."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/statuses/{sha}"
        payload = {
            "state": state,
            "ref": ref,
            "name": name,
            "description": description,
        }
        return self._send("POST", path, payload)

    def post_mr_discussion(
        self,
        project_id: str | int,
        mr_iid: int,
        body: str,
        file_path: str,
        new_line: int,
        base_sha: str = "",
        head_sha: str = "",
        start_sha: str = "",
    ) -> dict[str, Any]:
        """Post a diff discussion on a specific line of code in GitLab MR."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests/{mr_iid}/discussions"
        payload = {
            "body": body,
            "position": {
                "position_type": "text",
                "new_path": file_path,
                "new_line": new_line,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "start_sha": start_sha or base_sha,
            },
        }
        return self._send("POST", path, payload)

    def accept_merge_request(
        self,
        project_id: str | int,
        mr_iid: int,
        merge_when_pipeline_succeeds: bool = True,
    ) -> dict[str, Any]:
        """Merge the MR automatically when pipeline passes."""
        pid = urllib.parse.quote(str(project_id), safe="")
        path = f"/projects/{pid}/merge_requests/{mr_iid}/merge"
        payload = {
            "merge_when_pipeline_succeeds": merge_when_pipeline_succeeds,
            "should_remove_source_branch": True,
        }
        return self._send("PUT", path, payload)
