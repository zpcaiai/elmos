"""Digest-bound, no-shell execution for externally authorized campaigns.

The source repository never grants itself permission to run a qualification.
An operator must supply an exact manifest digest and an authorization reference.
The resulting evidence is self-attested unless a distinct verifier later signs it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ContractViolation
from .models import canonical_json
from .qualification import CampaignOutput, CampaignType, QualificationTarget

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_SECRET_ENV_NAME = re.compile(r"(?:KEY|TOKEN|PASSWORD|SECRET|CREDENTIAL|DSN)$")
_REDACTION = re.compile(
    r"(?i)((?:authorization|api[_-]?key|access[_-]?token|password|secret|dsn)\s*[:=]\s*)[^\s,;]+"
)


@dataclass(frozen=True, slots=True)
class CommandCampaignSpec:
    campaign_type: CampaignType
    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: float
    max_output_bytes: int
    allowed_env: tuple[str, ...]
    executable_digest: str
    input_digests: Mapping[str, str]

    @classmethod
    def from_mapping(cls, campaign_type: CampaignType, value: Mapping[str, Any]) -> CommandCampaignSpec:
        allowed = {
            "argv",
            "cwd",
            "timeout_seconds",
            "max_output_bytes",
            "allowed_env",
            "executable_digest",
            "input_digests",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ContractViolation("campaign command contains unknown fields: " + ",".join(sorted(unknown)))
        raw_argv = value.get("argv")
        if (
            not isinstance(raw_argv, list)
            or not raw_argv
            or any(not isinstance(item, str) or not item for item in raw_argv)
        ):
            raise ContractViolation("campaign command requires a non-empty string argv")
        cwd = str(value.get("cwd", "."))
        timeout = float(value.get("timeout_seconds", 900.0))
        maximum = int(value.get("max_output_bytes", 10_485_760))
        raw_env = value.get("allowed_env", [])
        if not isinstance(raw_env, list) or any(
            not isinstance(item, str) or not _SAFE_ENV_NAME.fullmatch(item) for item in raw_env
        ):
            raise ContractViolation("campaign environment allowlist is invalid")
        raw_digests = value.get("input_digests", {})
        if not isinstance(raw_digests, Mapping):
            raise ContractViolation("campaign input digests must be an object")
        digests = {str(path): str(digest) for path, digest in raw_digests.items()}
        if any(not path or not _DIGEST.fullmatch(digest) for path, digest in digests.items()):
            raise ContractViolation("campaign input digest binding is invalid")
        executable_digest = str(value.get("executable_digest", ""))
        if not _DIGEST.fullmatch(executable_digest):
            raise ContractViolation("campaign executable digest is required")
        if timeout <= 0 or timeout > 86_400 or maximum < 1024 or maximum > 134_217_728:
            raise ContractViolation("campaign timeout/output bounds are invalid")
        return cls(
            campaign_type, tuple(raw_argv), cwd, timeout, maximum, tuple(raw_env), executable_digest, digests
        )


@dataclass(frozen=True, slots=True)
class CommandCampaignManifest:
    executor_id: str
    manifest_digest: str
    workspace_root: Path
    campaigns: Mapping[CampaignType, CommandCampaignSpec]

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_digest: str,
        workspace_root: str | Path,
    ) -> CommandCampaignManifest:
        manifest_path = Path(path).resolve(strict=True)
        if manifest_path.is_symlink() or not _DIGEST.fullmatch(expected_digest):
            raise ContractViolation("qualification manifest path/digest is invalid")
        raw = manifest_path.read_bytes()
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != expected_digest:
            raise ContractViolation("qualification manifest digest mismatch")
        value = json.loads(raw)
        if not isinstance(value, Mapping) or set(value) != {"schema_version", "executor_id", "campaigns"}:
            raise ContractViolation("qualification manifest shape is invalid")
        if value.get("schema_version") != "1.0" or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", str(value.get("executor_id", ""))
        ):
            raise ContractViolation("qualification manifest identity/version is invalid")
        raw_campaigns = value.get("campaigns")
        if not isinstance(raw_campaigns, Mapping) or not raw_campaigns:
            raise ContractViolation("qualification manifest has no campaigns")
        campaigns: dict[CampaignType, CommandCampaignSpec] = {}
        for key, raw_spec in raw_campaigns.items():
            try:
                kind = CampaignType(str(key))
            except ValueError as error:
                raise ContractViolation("qualification manifest names an unknown campaign") from error
            if not isinstance(raw_spec, Mapping):
                raise ContractViolation("qualification campaign must be an object")
            campaigns[kind] = CommandCampaignSpec.from_mapping(kind, raw_spec)
        root = Path(workspace_root).resolve(strict=True)
        if root.is_symlink() or not root.is_dir():
            raise ContractViolation("qualification workspace root is invalid")
        return cls(str(value["executor_id"]), actual, root, campaigns)


class CommandCampaignExecutor:
    """Executes only the exact digest-bound argv selected by an operator."""

    independent = False

    def __init__(self, manifest: CommandCampaignManifest) -> None:
        self.manifest = manifest
        self.executor_id = manifest.executor_id

    def execute(
        self,
        campaign_type: CampaignType,
        target: QualificationTarget,
        authorization_ref: str,
    ) -> CampaignOutput:
        if not authorization_ref.strip():
            raise ContractViolation("campaign execution requires an authorization reference")
        spec = self.manifest.campaigns.get(campaign_type)
        if spec is None:
            raise ContractViolation("campaign is not authorized by the exact manifest")
        cwd = _workspace_path(self.manifest.workspace_root, spec.cwd)
        argv = tuple(_expand_workspace(value, self.manifest.workspace_root) for value in spec.argv)
        if not Path(argv[0]).is_absolute():
            raise ContractViolation("campaign executable path must be absolute")
        executable = Path(argv[0]).resolve(strict=True)
        if (
            executable.is_symlink()
            or not executable.is_file()
            or file_digest(executable) != spec.executable_digest
        ):
            raise ContractViolation("campaign executable must resolve to a regular non-symlink file")
        _verify_inputs(self.manifest.workspace_root, spec.input_digests)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C", "LC_ALL": "C"}
        secrets: list[str] = []
        for name in spec.allowed_env:
            value = os.environ.get(name)
            if value is None:
                raise ContractViolation("required campaign environment variable is unavailable: " + name)
            env[name] = value
            if _SECRET_ENV_NAME.search(name):
                secrets.append(value)
        started = time.monotonic()
        exit_code, stdout, stderr, timed_out, overflow = _run_bounded(
            argv, cwd=cwd, env=env, timeout=spec.timeout_seconds, maximum=spec.max_output_bytes
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = _redact(stdout, secrets)
        stderr = _redact(stderr, secrets)
        parsed = _last_json_object(stdout)
        declared = str(parsed.get("status", "")) if parsed is not None else ""
        status = (
            "PASS" if exit_code == 0 and not timed_out and not overflow and declared == "PASS" else "FAIL"
        )
        findings = ["SELF_ATTESTED_EXECUTION_REQUIRES_INDEPENDENT_VERIFICATION"]
        if timed_out:
            findings.append("COMMAND_TIMEOUT")
        if overflow:
            findings.append("COMMAND_OUTPUT_LIMIT_EXCEEDED")
        if exit_code != 0:
            findings.append("COMMAND_EXIT_NONZERO")
        if declared != "PASS":
            findings.append("COMMAND_DID_NOT_DECLARE_PASS")
        command_record = {
            "schema_version": "1.0",
            "campaign_type": campaign_type.value,
            "argv": list(argv),
            "cwd": str(cwd),
            "allowed_env_names": list(spec.allowed_env),
            "secret_env_names": [name for name in spec.allowed_env if _SECRET_ENV_NAME.search(name)],
            "executable_digest": spec.executable_digest,
            "input_digests": dict(spec.input_digests),
            "manifest_digest": self.manifest.manifest_digest,
            "target_digest": target.target_digest,
            "environment_digest": target.environment_digest,
            "authorization_ref": authorization_ref,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "output_overflow": overflow,
        }
        metrics: dict[str, Any] = {"duration_ms": duration_ms, "exit_code": exit_code}
        if parsed is not None and isinstance(parsed.get("metrics"), Mapping):
            metrics.update(dict(parsed["metrics"]))
        return CampaignOutput(
            status=status,
            raw_evidence={
                "command.json": canonical_json(command_record).encode(),
                "stdout.log": stdout,
                "stderr.log": stderr,
            },
            metrics=metrics,
            findings=tuple(findings),
        )


def file_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _workspace_path(root: Path, value: str) -> Path:
    candidate = (
        (root / value).resolve(strict=True)
        if not Path(value).is_absolute()
        else Path(value).resolve(strict=True)
    )
    if not candidate.is_relative_to(root) or candidate.is_symlink():
        raise ContractViolation("campaign path escapes the authorized workspace")
    return candidate


def _expand_workspace(value: str, root: Path) -> str:
    prefix = "${WORKSPACE}/"
    if value == "${WORKSPACE}":
        return str(root)
    if value.startswith(prefix):
        return str(_workspace_path(root, value[len(prefix) :]))
    if "${" in value:
        raise ContractViolation("campaign argv contains an unsupported expansion")
    return value


def _verify_inputs(root: Path, values: Mapping[str, str]) -> None:
    for relative, expected in values.items():
        path = _workspace_path(root, relative)
        if not path.is_file() or file_digest(path) != expected:
            raise ContractViolation("campaign input drift detected: " + relative)


def _run_bounded(
    argv: tuple[str, ...], *, cwd: Path, env: Mapping[str, str], timeout: float, maximum: int
) -> tuple[int, bytes, bytes, bool, bool]:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            shell=False,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        timed_out = False
        overflow = False
        while process.poll() is None:
            if time.monotonic() >= deadline:
                timed_out = True
                _terminate(process)
                break
            if stdout_file.tell() + stderr_file.tell() > maximum:
                overflow = True
                _terminate(process)
                break
            time.sleep(0.05)
        try:
            exit_code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill(process)
            exit_code = process.wait(timeout=5)
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(maximum + 1)
        stderr = stderr_file.read(maximum + 1)
        if len(stdout) + len(stderr) > maximum:
            overflow = True
            remaining = max(0, maximum - len(stdout))
            stderr = stderr[:remaining]
            stdout = stdout[:maximum]
        return exit_code, stdout, stderr, timed_out, overflow


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _redact(value: bytes, secrets: list[str]) -> bytes:
    text = value.decode("utf-8", errors="replace")
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return _REDACTION.sub(r"\1[REDACTED]", text).encode()


def _last_json_object(value: bytes) -> Mapping[str, Any] | None:
    for line in reversed(value.decode("utf-8", errors="replace").splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return parsed
    return None
