#!/usr/bin/env python3
"""Collect fail-closed GitHub App webhook redelivery evidence.

The command intentionally supports only GitHub.com's versioned REST API and
GitHub App JWT authentication.  It never writes the private key, JWT, webhook
request or response payloads, headers, signatures, or database credentials to
the evidence artifact.  A redelivery is a production side effect, so the
operator must explicitly supply both ``--redeliver`` and a change ticket.

The resulting receipt is local, self-attested engineering evidence and always
remains ``NOT_CERTIFIED``.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"
ACCEPT = "application/vnd.github+json"
USER_AGENT = "elmos-github-app-webhook-evidence/1"
MAX_RESPONSE_BYTES = 1_048_576
MAX_PSQL_OUTPUT_BYTES = 16_384
MAX_KEY_BYTES = 65_536
JWT_LIFETIME_SECONDS = 600
MAX_SERVER_CLOCK_SKEW = dt.timedelta(minutes=5)

EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
PGSERVICE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CHANGE_TICKET_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")
PROCESSING_STATUS_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


class EvidenceError(RuntimeError):
    """A deliberately message-free, persistable failure code."""

    def __init__(self, code: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", code):
            raise ValueError("invalid evidence error code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class Configuration:
    app_id: int
    private_key_file: Path
    delivery_id: int
    delivery_guid: str
    event: str
    action: str | None
    installation_id: int
    repository_id: int
    webhook_url: str
    expected_status_code: int
    change_ticket: str
    pgservice: str
    tenant_id: str
    expected_duplicate_count: int
    expected_outbox_count: int
    expected_processing_status: str
    output: Path
    http_timeout_seconds: float
    poll_timeout_seconds: float
    poll_interval_seconds: float
    database_timeout_seconds: float
    redeliver: bool


@dataclasses.dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class DatabaseVerifier(Protocol):
    def query(self, configuration: Configuration) -> Mapping[str, Any]: ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        raise EvidenceError("GITHUB_REDIRECT_REJECTED")


class UrlLibTransport:
    """HTTPS transport with redirects and ambient proxy configuration disabled."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RejectRedirects(),
        )

    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        request = urllib.request.Request(
            url,
            data=b"" if method == "POST" else None,
            headers=dict(headers),
            method=method,
        )
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError as error:
                        raise EvidenceError("GITHUB_CONTENT_LENGTH_INVALID") from error
                    if declared_length < 0 or declared_length > MAX_RESPONSE_BYTES:
                        raise EvidenceError("GITHUB_RESPONSE_TOO_LARGE")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise EvidenceError("GITHUB_RESPONSE_TOO_LARGE")
                return HttpResponse(
                    status=int(response.status),
                    headers={str(key): str(value) for key, value in response.headers.items()},
                    body=body,
                    final_url=str(response.geturl()),
                )
        except EvidenceError:
            raise
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise EvidenceError("GITHUB_REDIRECT_REJECTED") from error
            raise EvidenceError(f"GITHUB_HTTP_{error.code}") from error
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise EvidenceError("GITHUB_NETWORK_ERROR") from error


class GitHubAppApi:
    """A bounded client for the three GitHub App webhook delivery endpoints."""

    def __init__(
        self,
        jwt: str,
        timeout_seconds: float,
        transport: Transport | None = None,
    ) -> None:
        if not jwt or any(character.isspace() for character in jwt):
            raise EvidenceError("GITHUB_JWT_INVALID")
        self._jwt = jwt
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrlLibTransport()

    def get_delivery(self, delivery_id: int) -> Mapping[str, Any]:
        return self._json("GET", f"/app/hook/deliveries/{delivery_id}", 200)

    def list_deliveries(self) -> Sequence[Mapping[str, Any]]:
        payload = self._json("GET", "/app/hook/deliveries?per_page=100", 200)
        if not isinstance(payload, list):
            raise EvidenceError("GITHUB_DELIVERY_LIST_INVALID")
        if len(payload) > 100:
            raise EvidenceError("GITHUB_DELIVERY_LIST_INVALID")
        if not all(isinstance(item, dict) for item in payload):
            raise EvidenceError("GITHUB_DELIVERY_LIST_INVALID")
        return payload

    def redeliver(self, delivery_id: int) -> None:
        self._request("POST", f"/app/hook/deliveries/{delivery_id}/attempts", 202)

    def _json(self, method: str, path: str, expected_status: int) -> Any:
        response = self._request(method, path, expected_status)
        content_type = _header(response.headers, "Content-Type").split(";", 1)[0].strip()
        if content_type not in {"application/json", "application/vnd.github+json"}:
            raise EvidenceError("GITHUB_CONTENT_TYPE_INVALID")
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceError("GITHUB_JSON_INVALID") from error

    def _request(self, method: str, path: str, expected_status: int) -> HttpResponse:
        if method not in {"GET", "POST"}:
            raise EvidenceError("GITHUB_METHOD_INVALID")
        if not path.startswith("/app/hook/deliveries") or "#" in path:
            raise EvidenceError("GITHUB_PATH_INVALID")
        url = API_BASE + path
        response = self._transport(
            method,
            url,
            {
                "Accept": ACCEPT,
                "Authorization": f"Bearer {self._jwt}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": USER_AGENT,
            },
            self._timeout_seconds,
        )
        if response.final_url != url:
            raise EvidenceError("GITHUB_FINAL_URL_MISMATCH")
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise EvidenceError("GITHUB_RESPONSE_TOO_LARGE")
        if response.status != expected_status:
            if 300 <= response.status < 400:
                raise EvidenceError("GITHUB_REDIRECT_REJECTED")
            raise EvidenceError(f"GITHUB_HTTP_{response.status}")
        return response


PSQL_QUERY = r"""
\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL app.organization_id = :'tenant_id';
WITH selected_delivery AS MATERIALIZED (
    SELECT webhook_delivery_id,
           event_type,
           action,
           installation_external_id,
           repository_external_id,
           signature_valid,
           processing_status,
           duplicate_count,
           payload_sha256
      FROM github_webhook_deliveries
     WHERE organization_id = :'tenant_id'
       AND github_delivery_id = :'delivery_guid'
), delivery_summary AS (
    SELECT count(*) AS delivery_count,
           max(event_type) AS event_type,
           max(action) AS action,
           max(installation_external_id) AS installation_external_id,
           max(repository_external_id) AS repository_external_id,
           bool_and(signature_valid) AS signature_valid,
           max(processing_status) AS processing_status,
           max(duplicate_count) AS duplicate_count,
           bool_and(payload_sha256 ~ '^[0-9a-f]{64}$') AS payload_digest_format_valid
      FROM selected_delivery
), outbox_summary AS (
    SELECT count(*) AS outbox_count
      FROM outbox_events outbox
      JOIN selected_delivery delivery
        ON outbox.organization_id = :'tenant_id'
       AND outbox.aggregate_type = 'GITHUB_WEBHOOK'
       AND outbox.aggregate_id = delivery.webhook_delivery_id
), role_summary AS (
    SELECT rolbypassrls AS role_bypass_rls,
           current_setting('row_security') <> 'off' AS row_security_on
      FROM pg_roles
     WHERE rolname = current_user
)
SELECT json_build_object(
    'delivery_count', delivery_summary.delivery_count,
    'event_type', delivery_summary.event_type,
    'action', delivery_summary.action,
    'installation_external_id', delivery_summary.installation_external_id,
    'repository_external_id', delivery_summary.repository_external_id,
    'signature_valid', delivery_summary.signature_valid,
    'processing_status', delivery_summary.processing_status,
    'duplicate_count', delivery_summary.duplicate_count,
    'payload_digest_format_valid', delivery_summary.payload_digest_format_valid,
    'outbox_count', outbox_summary.outbox_count,
    'role_bypass_rls', role_summary.role_bypass_rls,
    'row_security_on', role_summary.row_security_on
)::text
  FROM delivery_summary, outbox_summary, role_summary;
ROLLBACK;
""".strip()


class PsqlDatabaseVerifier:
    """Read-only, RLS-bound verification through a named libpq service."""

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self._runner = runner

    def query(self, configuration: Configuration) -> Mapping[str, Any]:
        if os.environ.get("PGPASSWORD") or os.environ.get("DATABASE_URL"):
            raise EvidenceError("DATABASE_AMBIENT_PASSWORD_REJECTED")
        child_environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "LC_ALL": "C",
            "PGSERVICE": configuration.pgservice,
            "PGAPPNAME": "elmos-github-webhook-evidence",
        }
        command = [
            "psql",
            "-X",
            "-qAt",
            "--set",
            "ON_ERROR_STOP=1",
            "--set",
            f"tenant_id={configuration.tenant_id}",
            "--set",
            f"delivery_guid={configuration.delivery_guid}",
            "--command",
            PSQL_QUERY,
        ]
        try:
            completed = self._runner(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_environment,
                timeout=configuration.database_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise EvidenceError("DATABASE_QUERY_FAILED") from error
        if completed.returncode != 0:
            raise EvidenceError("DATABASE_QUERY_FAILED")
        if len(completed.stdout) > MAX_PSQL_OUTPUT_BYTES:
            raise EvidenceError("DATABASE_RESPONSE_TOO_LARGE")
        try:
            lines = [
                line
                for line in completed.stdout.decode("utf-8", "strict").splitlines()
                if line
            ]
        except UnicodeDecodeError as error:
            raise EvidenceError("DATABASE_RESPONSE_INVALID") from error
        if len(lines) != 1:
            raise EvidenceError("DATABASE_RESPONSE_INVALID")
        try:
            value = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise EvidenceError("DATABASE_RESPONSE_INVALID") from error
        if not isinstance(value, dict):
            raise EvidenceError("DATABASE_RESPONSE_INVALID")
        return value


def _header(headers: Mapping[str, str], requested: str) -> str:
    for key, value in headers.items():
        if key.lower() == requested.lower():
            return value
    return ""


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_private_key_path(path: Path) -> os.stat_result:
    if not path.is_absolute():
        raise EvidenceError("PRIVATE_KEY_PATH_NOT_ABSOLUTE")
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise EvidenceError("PRIVATE_KEY_UNAVAILABLE") from error
    if not stat.S_ISREG(path_stat.st_mode) or path.is_symlink():
        raise EvidenceError("PRIVATE_KEY_NOT_REGULAR")
    if path_stat.st_uid != os.geteuid():
        raise EvidenceError("PRIVATE_KEY_OWNER_INVALID")
    if path_stat.st_mode & 0o077:
        raise EvidenceError("PRIVATE_KEY_PERMISSIONS_TOO_BROAD")
    if path_stat.st_size < 256 or path_stat.st_size > MAX_KEY_BYTES:
        raise EvidenceError("PRIVATE_KEY_SIZE_INVALID")
    try:
        if path.resolve(strict=True) != path:
            raise EvidenceError("PRIVATE_KEY_PATH_NOT_CANONICAL")
    except OSError as error:
        raise EvidenceError("PRIVATE_KEY_UNAVAILABLE") from error
    return path_stat


def build_github_app_jwt(
    app_id: int,
    private_key_file: Path,
    now_epoch_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> str:
    expected_stat = _validate_private_key_path(private_key_file)
    header = _b64url(_canonical_json({"alg": "RS256", "typ": "JWT"}))
    issued_at = now_epoch_seconds - 60
    payload = _b64url(
        _canonical_json(
            {
                "exp": issued_at + JWT_LIFETIME_SECONDS,
                "iat": issued_at,
                "iss": str(app_id),
            }
        )
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(private_key_file, flags)
    except OSError as error:
        raise EvidenceError("PRIVATE_KEY_UNAVAILABLE") from error
    try:
        opened_stat = os.fstat(descriptor)
        if (opened_stat.st_dev, opened_stat.st_ino) != (expected_stat.st_dev, expected_stat.st_ino):
            raise EvidenceError("PRIVATE_KEY_CHANGED_DURING_OPEN")
        if (
            opened_stat.st_uid != os.geteuid()
            or opened_stat.st_mode & 0o077
            or not stat.S_ISREG(opened_stat.st_mode)
            or not 256 <= opened_stat.st_size <= MAX_KEY_BYTES
        ):
            raise EvidenceError("PRIVATE_KEY_CHANGED_DURING_OPEN")
        completed = runner(
            ["openssl", "dgst", "-sha256", "-sign", f"/dev/fd/{descriptor}"],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(descriptor,),
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError("JWT_SIGNING_FAILED") from error
    finally:
        os.close(descriptor)
    if completed.returncode != 0 or not 64 <= len(completed.stdout) <= 1024:
        raise EvidenceError("JWT_SIGNING_FAILED")
    return f"{header}.{payload}.{_b64url(completed.stdout)}"


def _validate_delivery(
    payload: Mapping[str, Any],
    configuration: Configuration,
    *,
    expected_id: int | None,
    require_url: bool,
    require_redelivery: bool | None,
) -> None:
    required = {
        "id": expected_id,
        "guid": configuration.delivery_guid,
        "event": configuration.event,
        "action": configuration.action,
        "installation_id": configuration.installation_id,
        "repository_id": configuration.repository_id,
    }
    for key, expected in required.items():
        if key not in payload:
            raise EvidenceError("GITHUB_DELIVERY_BINDING_INCOMPLETE")
        if expected is not None and payload[key] != expected:
            raise EvidenceError("GITHUB_DELIVERY_BINDING_MISMATCH")
        if key == "action" and expected is None and payload[key] is not None:
            raise EvidenceError("GITHUB_DELIVERY_BINDING_MISMATCH")
    if type(payload["id"]) is not int or payload["id"] <= 0:
        raise EvidenceError("GITHUB_DELIVERY_BINDING_INVALID")
    if type(payload["installation_id"]) is not int or type(payload["repository_id"]) is not int:
        raise EvidenceError("GITHUB_DELIVERY_BINDING_INVALID")
    if not isinstance(payload["guid"], str) or not isinstance(payload["event"], str):
        raise EvidenceError("GITHUB_DELIVERY_BINDING_INVALID")
    if payload["action"] is not None and not isinstance(payload["action"], str):
        raise EvidenceError("GITHUB_DELIVERY_BINDING_INVALID")
    if require_url and payload.get("url") != configuration.webhook_url:
        raise EvidenceError("GITHUB_WEBHOOK_URL_MISMATCH")
    if require_redelivery is not None and payload.get("redelivery") is not require_redelivery:
        raise EvidenceError("GITHUB_REDELIVERY_STATE_MISMATCH")
    if type(payload.get("redelivery")) is not bool:
        raise EvidenceError("GITHUB_REDELIVERY_STATE_MISMATCH")
    if type(payload.get("status_code")) is not int or not 100 <= payload["status_code"] <= 599:
        raise EvidenceError("GITHUB_DELIVERY_STATUS_INVALID")
    status_value = payload.get("status")
    if not isinstance(status_value, str) or not 1 <= len(status_value) <= 64:
        raise EvidenceError("GITHUB_DELIVERY_STATUS_INVALID")
    delivered_at = payload.get("delivered_at")
    if not isinstance(delivered_at, str):
        raise EvidenceError("GITHUB_DELIVERY_TIMESTAMP_INVALID")
    _parse_timestamp(delivered_at)


def _parse_timestamp(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("GITHUB_DELIVERY_TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None:
        raise EvidenceError("GITHUB_DELIVERY_TIMESTAMP_INVALID")
    return parsed.astimezone(dt.timezone.utc)


def _validate_database_result(
    result: Mapping[str, Any], configuration: Configuration
) -> Mapping[str, Any]:
    expected_keys = {
        "delivery_count",
        "event_type",
        "action",
        "installation_external_id",
        "repository_external_id",
        "signature_valid",
        "processing_status",
        "duplicate_count",
        "payload_digest_format_valid",
        "outbox_count",
        "role_bypass_rls",
        "row_security_on",
    }
    if set(result) != expected_keys:
        raise EvidenceError("DATABASE_RESPONSE_INVALID")
    expected = {
        "delivery_count": 1,
        "event_type": configuration.event,
        "action": configuration.action,
        "installation_external_id": configuration.installation_id,
        "repository_external_id": configuration.repository_id,
        "signature_valid": True,
        "processing_status": configuration.expected_processing_status,
        "duplicate_count": configuration.expected_duplicate_count,
        "payload_digest_format_valid": True,
        "outbox_count": configuration.expected_outbox_count,
        "role_bypass_rls": False,
        "row_security_on": True,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise EvidenceError("DATABASE_BINDING_NOT_OBSERVED")
    return {key: result[key] for key in sorted(expected_keys)}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _format_timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def collect_evidence(
    configuration: Configuration,
    github: GitHubAppApi,
    database: DatabaseVerifier,
    *,
    wall_clock: Callable[[], dt.datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not configuration.redeliver:
        raise EvidenceError("REDELIVERY_EXPLICIT_FLAG_REQUIRED")
    started_at = wall_clock()
    before = github.get_delivery(configuration.delivery_id)
    if not isinstance(before, dict):
        raise EvidenceError("GITHUB_DELIVERY_DETAIL_INVALID")
    _validate_delivery(
        before,
        configuration,
        expected_id=configuration.delivery_id,
        require_url=True,
        require_redelivery=None,
    )

    # GitHub represents a retry as a new numeric delivery ID carrying the same
    # GUID. Freeze all currently visible IDs so a historical redelivery can
    # never satisfy this invocation's post-202 poll.
    known_delivery_ids: set[int] = {configuration.delivery_id}
    for existing in github.list_deliveries():
        if existing.get("guid") != configuration.delivery_guid:
            continue
        _validate_delivery(
            existing,
            configuration,
            expected_id=None,
            require_url=False,
            require_redelivery=None,
        )
        known_delivery_ids.add(existing["id"])

    if progress is not None:
        progress["redelivery_post_attempted"] = True
    github.redeliver(configuration.delivery_id)
    accepted_at = wall_clock()
    if progress is not None:
        progress["redelivery_post_accepted"] = True
    deadline = monotonic() + configuration.poll_timeout_seconds
    redelivery_summary: Mapping[str, Any] | None = None
    while monotonic() <= deadline:
        deliveries = github.list_deliveries()
        candidates: list[Mapping[str, Any]] = []
        for candidate in deliveries:
            if candidate.get("guid") != configuration.delivery_guid:
                continue
            if candidate.get("id") in known_delivery_ids:
                continue
            if candidate.get("redelivery") is not True:
                continue
            _validate_delivery(
                candidate,
                configuration,
                expected_id=None,
                require_url=False,
                require_redelivery=True,
            )
            if candidate.get("status_code") != configuration.expected_status_code:
                raise EvidenceError("GITHUB_REDELIVERY_STATUS_MISMATCH")
            delivered_at = _parse_timestamp(str(candidate["delivered_at"]))
            if delivered_at < accepted_at - MAX_SERVER_CLOCK_SKEW:
                raise EvidenceError("GITHUB_REDELIVERY_TIMESTAMP_STALE")
            candidates.append(candidate)
        if len(candidates) > 1:
            # The POST response carries no new delivery id. Multiple new attempts
            # therefore cannot be attributed to this invocation without guessing.
            raise EvidenceError("GITHUB_REDELIVERY_AMBIGUOUS")
        if candidates:
            redelivery_summary = candidates[0]
            break
        sleep(configuration.poll_interval_seconds)
    if redelivery_summary is None:
        raise EvidenceError("GITHUB_REDELIVERY_NOT_OBSERVED")

    redelivery_id = redelivery_summary["id"]
    redelivery_detail = github.get_delivery(redelivery_id)
    if not isinstance(redelivery_detail, dict):
        raise EvidenceError("GITHUB_DELIVERY_DETAIL_INVALID")
    _validate_delivery(
        redelivery_detail,
        configuration,
        expected_id=redelivery_id,
        require_url=True,
        require_redelivery=True,
    )
    if redelivery_detail.get("status_code") != configuration.expected_status_code:
        raise EvidenceError("GITHUB_REDELIVERY_STATUS_MISMATCH")

    database_deadline = monotonic() + configuration.poll_timeout_seconds
    database_result: Mapping[str, Any] | None = None
    while monotonic() <= database_deadline:
        observed = database.query(configuration)
        try:
            database_result = _validate_database_result(observed, configuration)
            break
        except EvidenceError as error:
            if error.code != "DATABASE_BINDING_NOT_OBSERVED":
                raise
        sleep(configuration.poll_interval_seconds)
    if database_result is None:
        raise EvidenceError("DATABASE_BINDING_NOT_OBSERVED")

    completed_at = wall_clock()
    return {
        "schema_version": 1,
        "evidence_type": "GITHUB_APP_WEBHOOK_REDELIVERY",
        "result": "PASS",
        "certification_status": "NOT_CERTIFIED",
        "verification_state": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_verification": "NOT_RUN",
        "api": {
            "base": API_BASE,
            "version": API_VERSION,
            "authentication": "GITHUB_APP_JWT",
            "jwt_lifetime_seconds": JWT_LIFETIME_SECONDS,
            "redirects_allowed": False,
            "maximum_response_bytes": MAX_RESPONSE_BYTES,
        },
        "authorization": {
            "redeliver_requested": True,
            "change_ticket_sha256": _sha256_text(configuration.change_ticket),
            "app_id_sha256": _sha256_text(str(configuration.app_id)),
        },
        "delivery_binding": {
            "original_delivery_id": configuration.delivery_id,
            "redelivery_id": redelivery_id,
            "guid": configuration.delivery_guid,
            "event": configuration.event,
            "action": configuration.action,
            "installation_id": configuration.installation_id,
            "repository_id": configuration.repository_id,
            "webhook_url_sha256": _sha256_text(configuration.webhook_url),
            "original_delivered_at": before["delivered_at"],
            "redelivery_delivered_at": redelivery_detail["delivered_at"],
            "redelivery_status": redelivery_detail.get("status"),
            "redelivery_status_code": redelivery_detail["status_code"],
        },
        "database_verification": {
            "tenant_id_sha256": _sha256_text(configuration.tenant_id),
            "pgservice_sha256": _sha256_text(configuration.pgservice),
            **database_result,
        },
        "started_at": _format_timestamp(started_at),
        "redelivery_accepted_at": _format_timestamp(accepted_at),
        "completed_at": _format_timestamp(completed_at),
        "residual_boundaries": [
            "LOCAL_SELF_ATTESTATION_IS_NOT_INDEPENDENT_VERIFICATION",
            "ONE_REDELIVERY_DOES_NOT_PROVE_PRODUCTION_RELIABILITY",
            "NOT_CERTIFIED",
        ],
    }


def _validate_webhook_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)  # type: ignore[attr-defined]
    except (TypeError, ValueError) as error:
        raise EvidenceError("WEBHOOK_URL_INVALID") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
        or parsed.port not in {None, 443}
        or parsed.hostname != parsed.hostname.lower()
    ):
        raise EvidenceError("WEBHOOK_URL_INVALID")
    return value


def _bounded_float(value: str, minimum: float, maximum: float, code: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(code) from error
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(code)
    return parsed


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> Configuration:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True, type=_positive_integer)
    parser.add_argument("--private-key-file", required=True, type=Path)
    parser.add_argument("--delivery-id", required=True, type=_positive_integer)
    parser.add_argument("--delivery-guid", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument(
        "--action",
        required=True,
        help="Exact GitHub action, or the literal NONE when the API value must be null.",
    )
    parser.add_argument("--installation-id", required=True, type=_positive_integer)
    parser.add_argument("--repository-id", required=True, type=_positive_integer)
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--expected-status-code", required=True, type=_positive_integer)
    parser.add_argument("--redeliver", action="store_true")
    parser.add_argument("--change-ticket", required=True)
    parser.add_argument("--pgservice", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--expected-duplicate-count", required=True, type=_nonnegative_integer)
    parser.add_argument("--expected-outbox-count", required=True, type=_nonnegative_integer)
    parser.add_argument("--expected-processing-status", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--http-timeout-seconds",
        default=10.0,
        type=lambda value: _bounded_float(value, 1.0, 30.0, "invalid HTTP timeout"),
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        default=60.0,
        type=lambda value: _bounded_float(value, 1.0, 300.0, "invalid poll timeout"),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        default=2.0,
        type=lambda value: _bounded_float(value, 0.1, 30.0, "invalid poll interval"),
    )
    parser.add_argument(
        "--database-timeout-seconds",
        default=10.0,
        type=lambda value: _bounded_float(value, 1.0, 30.0, "invalid database timeout"),
    )
    args = parser.parse_args(argv)

    try:
        parsed_guid = str(uuid.UUID(args.delivery_guid))
    except (ValueError, AttributeError) as error:
        raise EvidenceError("DELIVERY_GUID_INVALID") from error
    if parsed_guid != args.delivery_guid.lower():
        raise EvidenceError("DELIVERY_GUID_NOT_CANONICAL")
    if not EVENT_PATTERN.fullmatch(args.event):
        raise EvidenceError("EVENT_INVALID")
    action = None if args.action == "NONE" else args.action
    if action is not None and not ACTION_PATTERN.fullmatch(action):
        raise EvidenceError("ACTION_INVALID")
    if not CHANGE_TICKET_PATTERN.fullmatch(args.change_ticket):
        raise EvidenceError("CHANGE_TICKET_INVALID")
    if not PGSERVICE_PATTERN.fullmatch(args.pgservice):
        raise EvidenceError("PGSERVICE_INVALID")
    if not TENANT_PATTERN.fullmatch(args.tenant_id):
        raise EvidenceError("TENANT_ID_INVALID")
    if not PROCESSING_STATUS_PATTERN.fullmatch(args.expected_processing_status):
        raise EvidenceError("PROCESSING_STATUS_INVALID")
    if not 100 <= args.expected_status_code <= 599:
        raise EvidenceError("EXPECTED_STATUS_CODE_INVALID")
    if not args.redeliver:
        raise EvidenceError("REDELIVERY_EXPLICIT_FLAG_REQUIRED")
    webhook_url = _validate_webhook_url(args.webhook_url)
    output = args.output
    if not output.is_absolute():
        raise EvidenceError("OUTPUT_PATH_NOT_ABSOLUTE")
    try:
        if output.parent.resolve(strict=True) != output.parent:
            raise EvidenceError("OUTPUT_PARENT_NOT_CANONICAL")
    except OSError as error:
        raise EvidenceError("OUTPUT_PARENT_UNAVAILABLE") from error
    if output.exists() or output.is_symlink():
        raise EvidenceError("OUTPUT_ALREADY_EXISTS")
    _validate_private_key_path(args.private_key_file)

    return Configuration(
        app_id=args.app_id,
        private_key_file=args.private_key_file,
        delivery_id=args.delivery_id,
        delivery_guid=parsed_guid,
        event=args.event,
        action=action,
        installation_id=args.installation_id,
        repository_id=args.repository_id,
        webhook_url=webhook_url,
        expected_status_code=args.expected_status_code,
        change_ticket=args.change_ticket,
        pgservice=args.pgservice,
        tenant_id=args.tenant_id,
        expected_duplicate_count=args.expected_duplicate_count,
        expected_outbox_count=args.expected_outbox_count,
        expected_processing_status=args.expected_processing_status,
        output=output,
        http_timeout_seconds=args.http_timeout_seconds,
        poll_timeout_seconds=args.poll_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        database_timeout_seconds=args.database_timeout_seconds,
        redeliver=args.redeliver,
    )


def write_json_atomic_no_replace(destination: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    temporary = destination.parent / (
        f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as file_pointer:
            descriptor = -1
            file_pointer.write(encoded)
            file_pointer.flush()
            os.fsync(file_pointer.fileno())
        os.link(temporary, destination)
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except FileExistsError as error:
        raise EvidenceError("OUTPUT_ALREADY_EXISTS") from error
    except OSError as error:
        raise EvidenceError("OUTPUT_WRITE_FAILED") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def failure_evidence(
    configuration: Configuration,
    error_code: str,
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    post_attempted = progress.get("redelivery_post_attempted") is True
    post_accepted = progress.get("redelivery_post_accepted") is True
    return {
        "schema_version": 1,
        "evidence_type": "GITHUB_APP_WEBHOOK_REDELIVERY",
        "result": "FAIL",
        "error_code": error_code,
        "certification_status": "NOT_CERTIFIED",
        "verification_state": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_verification": "NOT_RUN",
        "api": {"base": API_BASE, "version": API_VERSION},
        "authorization": {
            "redeliver_requested": True,
            "change_ticket_sha256": _sha256_text(configuration.change_ticket),
            "app_id_sha256": _sha256_text(str(configuration.app_id)),
        },
        "delivery_binding": {
            "original_delivery_id": configuration.delivery_id,
            "guid": configuration.delivery_guid,
            "event": configuration.event,
            "action": configuration.action,
            "installation_id": configuration.installation_id,
            "repository_id": configuration.repository_id,
            "webhook_url_sha256": _sha256_text(configuration.webhook_url),
        },
        "database_binding": {
            "tenant_id_sha256": _sha256_text(configuration.tenant_id),
            "pgservice_sha256": _sha256_text(configuration.pgservice),
        },
        "redelivery_post_attempted": post_attempted,
        "redelivery_post_accepted": post_accepted,
        "side_effect_state": (
            "UNKNOWN_RECONCILIATION_REQUIRED"
            if post_attempted
            else "NOT_ATTEMPTED_BY_TOOL"
        ),
        "recorded_at": _format_timestamp(_utc_now()),
        "residual_boundaries": ["FAILURE_IS_NOT_CERTIFICATION", "NOT_CERTIFIED"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    configuration: Configuration | None = None
    progress: dict[str, Any] = {
        "redelivery_post_attempted": False,
        "redelivery_post_accepted": False,
    }
    try:
        configuration = parse_args(argv)
        jwt = build_github_app_jwt(
            configuration.app_id,
            configuration.private_key_file,
            int(time.time()),
        )
        github = GitHubAppApi(jwt, configuration.http_timeout_seconds)
        evidence = collect_evidence(
            configuration,
            github,
            PsqlDatabaseVerifier(),
            progress=progress,
        )
        write_json_atomic_no_replace(configuration.output, evidence)
        print("PASS: GitHub App webhook redelivery evidence written; NOT_CERTIFIED")
        return 0
    except EvidenceError as error:
        if configuration is not None and not configuration.output.exists():
            try:
                write_json_atomic_no_replace(
                    configuration.output,
                    failure_evidence(configuration, error.code, progress),
                )
            except EvidenceError:
                pass
        print(f"FAIL: {error.code}; NOT_CERTIFIED", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - the CLI must fail closed without leaking internals
        if configuration is not None and not configuration.output.exists():
            try:
                write_json_atomic_no_replace(
                    configuration.output,
                    failure_evidence(configuration, "INTERNAL_ERROR", progress),
                )
            except EvidenceError:
                pass
        print("FAIL: INTERNAL_ERROR; NOT_CERTIFIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
