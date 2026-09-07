"""Real, bounded engineering probes for production qualification campaigns.

Every function executes against an explicitly supplied disposable target.  A
successful probe is self-attested engineering evidence; it never changes the
product certification or GA state.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, LiteralString

from .artifacts import ContentAddressedStore
from .browser import BrowserEvidenceRunner, BrowserScenario, BrowserStep
from .browser_drivers import DEFAULT_BROWSER_PROFILES, BrowserMatrixRunner, PlaywrightBrowserDriver
from .errors import ContractViolation, IdempotencyConflict, LeaseLost, NotConfigured, TenantIsolationError
from .live_providers import LiveCompletionConfig, LiveCompletionTransport, LiveProviderError
from .models import Identity, canonical_json, digest_of
from .postgres import PostgresEventLedger
from .providers import ProviderRequest
from .qualification import GoldenRepository, GoldenSuiteValidator


@dataclass(frozen=True, slots=True)
class ProbeResult:
    probe: str
    status: str
    metrics: Mapping[str, float | int | str]
    findings: tuple[str, ...]
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.probe or self.status not in {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}:
            raise ValueError("probe identity/status is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe": self.probe,
            "status": self.status,
            "metrics": dict(self.metrics),
            "findings": list(self.findings),
            "details": dict(self.details),
            "certification": "NOT_CERTIFIED",
            "release_status": "NOT_GA",
        }


def run_postgres_probe(dsn: str, *, concurrency: int = 8, events: int = 64) -> ProbeResult:
    """Exercise migrations, RLS, append-only events, fencing and concurrency."""

    if concurrency < 1 or concurrency > 64 or events < concurrency or events > 100_000:
        raise ValueError("PostgreSQL probe bounds are invalid")
    suffix = uuid.uuid4().hex
    identity = Identity("qualification-a", "project-a", "task-postgres", "pg-" + suffix)
    manifest = "sha256:" + hashlib.sha256(("postgres:" + suffix).encode()).hexdigest()
    ledger = PostgresEventLedger.connect(dsn)
    started = time.monotonic()
    try:
        ledger.create_run(identity, manifest)
        initial = ledger.append(
            identity,
            "run.status",
            {"status": "running"},
            idempotency_key="initial-status",
        )
        replay = ledger.append(
            identity,
            "run.status",
            {"status": "running"},
            idempotency_key="initial-status",
        )
        if replay.event_id != initial.event_id:
            raise AssertionError("idempotent append produced a second event")
        try:
            ledger.append(
                identity,
                "run.status",
                {"status": "blocked"},
                idempotency_key="initial-status",
            )
        except IdempotencyConflict:
            pass
        else:
            raise AssertionError("conflicting idempotency key was accepted")
        lease = ledger.acquire_lease(identity, "worker-a", 30.0, time.time())
        ledger.assert_lease(lease, time.time())
        checkpoint_id = ledger.save_checkpoint(
            identity,
            event_seq=initial.seq,
            manifest_hash=manifest,
            state={"phase": "running"},
        )
        ledger.release_lease(lease)
    finally:
        ledger.close()

    latencies: list[float] = []
    latency_lock = threading.Lock()

    def append(index: int) -> None:
        worker = PostgresEventLedger.connect(dsn)
        before = time.monotonic()
        try:
            worker.append(
                identity,
                "tool.observed",
                {"action_id": f"load-{index}", "status": "succeeded"},
                idempotency_key=f"event-{index}",
            )
        finally:
            worker.close()
        with latency_lock:
            latencies.append((time.monotonic() - before) * 1000)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        tuple(pool.map(append, range(events)))

    ledger = PostgresEventLedger.connect(dsn)
    try:
        stored = ledger.events(identity.tenant_id, identity.run_id, limit=events + 10)
        if len(stored) != events + 1 or not ledger.verify_chain(identity.tenant_id, identity.run_id):
            raise AssertionError("concurrent event sequence/hash chain is incomplete")
        projection = ledger.rebuild_projection(identity.tenant_id, identity.run_id)
        if len(projection["actions"]) != events:
            raise AssertionError("projection rebuild lost concurrent actions")
        latest = ledger.latest_checkpoint(identity.tenant_id, identity.run_id)
        if latest is None or latest["checkpoint_id"] != checkpoint_id:
            raise AssertionError("checkpoint replay failed")
        other_tenant_hidden = False
        try:
            ledger.events("qualification-b", identity.run_id)
        except TenantIsolationError:
            other_tenant_hidden = True
        if not other_tenant_hidden:
            raise AssertionError("cross-tenant run was visible")
    finally:
        ledger.close()
    update_rows, delete_rows, server_version = _postgres_append_only_checks(dsn, identity)
    if update_rows != 0 or delete_rows != 0:
        raise AssertionError("append-only event rows were mutable")
    elapsed = time.monotonic() - started
    return ProbeResult(
        "postgres-real",
        "PASS",
        {
            "events": len(stored),
            "concurrency": concurrency,
            "throughput_events_per_second": round(events / max(elapsed, 0.001), 3),
            "latency_p50_ms": round(_percentile(latencies, 50), 3),
            "latency_p95_ms": round(_percentile(latencies, 95), 3),
            "latency_p99_ms": round(_percentile(latencies, 99), 3),
        },
        (
            "LOCAL_DISPOSABLE_POSTGRES_SELF_ATTESTED",
            "POSTGRES_FAILOVER_NOT_RUN",
            "INDEPENDENT_VERIFICATION_NOT_RUN",
        ),
        {
            "server_version": server_version,
            "rls_cross_tenant_hidden": True,
            "append_only_update_rows": update_rows,
            "append_only_delete_rows": delete_rows,
            "checkpoint_id": checkpoint_id,
            "projection_digest": digest_of(projection),
        },
    )


def run_load_probe(dsn: str, *, concurrency: int = 16, events: int = 256) -> ProbeResult:
    """Run a bounded producer/consumer event-fanout workload on disposable PostgreSQL."""

    if concurrency < 1 or concurrency > 64 or events < concurrency or events > 10_000:
        raise ValueError("load probe bounds are invalid")
    suffix = uuid.uuid4().hex
    identity = Identity("qualification-load", "project-load", "task-load", "load-" + suffix)
    manifest = "sha256:" + hashlib.sha256(("load:" + suffix).encode()).hexdigest()
    ledger = PostgresEventLedger.connect(dsn)
    started = time.monotonic()
    work: queue.Queue[int | None] = queue.Queue(maxsize=max(4, concurrency * 2))
    latencies: list[float] = []
    errors: list[str] = []
    max_depth = 0
    lock = threading.Lock()
    try:
        ledger.create_run(identity, manifest)
        ledger.append(identity, "run.status", {"status": "running"}, idempotency_key="load-initial")
    finally:
        ledger.close()

    def consume() -> None:
        nonlocal max_depth
        worker = PostgresEventLedger.connect(dsn)
        try:
            while True:
                item = work.get()
                try:
                    if item is None:
                        return
                    before = time.monotonic()
                    worker.append(
                        identity,
                        "tool.observed",
                        {"action_id": f"load-fanout-{item}", "status": "succeeded"},
                        idempotency_key=f"load-fanout-{item}",
                    )
                    with lock:
                        latencies.append((time.monotonic() - before) * 1000)
                        max_depth = max(max_depth, work.qsize())
                except Exception as error:  # noqa: BLE001 - worker errors are recorded as campaign evidence
                    with lock:
                        errors.append(type(error).__name__ + ": " + str(error)[:200])
                finally:
                    work.task_done()
        finally:
            worker.close()

    workers = [
        threading.Thread(target=consume, name=f"load-consumer-{index}") for index in range(concurrency)
    ]
    for worker in workers:
        worker.start()
    for item in range(events):
        work.put(item)
    for _ in workers:
        work.put(None)
    work.join()
    for worker in workers:
        worker.join(timeout=30)
    if any(worker.is_alive() for worker in workers):
        raise AssertionError("load probe consumer did not drain its bounded queue")

    verifier = PostgresEventLedger.connect(dsn)
    try:
        stored = verifier.events(identity.tenant_id, identity.run_id, limit=events + 10)
        chain_ok = verifier.verify_chain(identity.tenant_id, identity.run_id)
        projection = verifier.rebuild_projection(identity.tenant_id, identity.run_id)
    finally:
        verifier.close()
    passed = not errors and len(stored) == events + 1 and chain_ok and len(projection["actions"]) == events
    return ProbeResult(
        "load-real",
        "PASS" if passed else "FAIL",
        {
            "events": len(stored),
            "requested_events": events,
            "consumer_workers": concurrency,
            "throughput_events_per_second": round(events / max(time.monotonic() - started, 0.001), 3),
            "latency_p50_ms": round(_percentile(latencies, 50), 3),
            "latency_p95_ms": round(_percentile(latencies, 95), 3),
            "latency_p99_ms": round(_percentile(latencies, 99), 3),
            "backpressure_capacity": work.maxsize,
            "max_queue_depth_observed": max_depth,
            "failed_events": len(errors),
        },
        (
            "LOCAL_DISPOSABLE_LOAD_SELF_ATTESTED",
            "ACTIVE_IDLE_SCALING_NOT_RUN",
            "REPRESENTATIVE_SOAK_NOT_RUN",
            "INDEPENDENT_VERIFICATION_NOT_RUN",
        )
        + (("LOAD_WORKER_ERRORS_RECORDED",) if errors else ()),
        {
            "manifest_digest": manifest,
            "chain_verified": chain_ok,
            "projection_digest": digest_of(projection),
            "errors": errors,
        },
    )


def run_provider_probe(
    *,
    openai_token: str,
    anthropic_token: str,
    anthropic_base_url: str,
    openai_model: str,
    anthropic_model: str,
) -> ProbeResult:
    """Run one identical completion task through three external protocols."""

    prompt = "Return exactly ELMOS_PROVIDER_CONFORMANCE_OK and no other text."
    suffix = uuid.uuid4().hex
    identity = Identity("qualification-a", "project-a", "task-provider", "provider-" + suffix)
    configs = (
        (
            LiveCompletionConfig(
                "openai-responses",
                "https://api.openai.com/v1/responses",
                "openai-responses",
            ),
            openai_token,
            openai_model,
        ),
        (
            LiveCompletionConfig(
                "openai-chat",
                "https://api.openai.com/v1/chat/completions",
                "openai-chat",
            ),
            openai_token,
            openai_model,
        ),
        (
            LiveCompletionConfig(
                "anthropic-messages",
                anthropic_base_url.rstrip("/") + "/v1/messages",
                "anthropic-messages",
            ),
            anthropic_token,
            anthropic_model,
        ),
    )
    details: dict[str, Any] = {}
    total_input = 0
    total_output = 0
    latencies: list[float] = []
    failures: dict[str, dict[str, Any]] = {}
    successful_adapters = 0
    for config, token, model in configs:

        def token_provider(_provider: str, *, value: str = token) -> str:
            return value

        transport = LiveCompletionTransport(config, token_provider)
        request = ProviderRequest(
            identity,
            model,
            {"prompt": prompt},
            idempotency_key="qualification-" + config.provider + "-" + suffix,
        )
        started = time.monotonic()
        try:
            response = transport.adapter().decide(request)
        except (ContractViolation, LiveProviderError, NotConfigured, AssertionError) as error:
            failure: dict[str, Any] = {
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            }
            if isinstance(error, LiveProviderError):
                failure["status_code"] = error.status_code
                failure["retryable"] = error.retryable
            failures[config.provider] = failure
            continue
        elapsed_ms = (time.monotonic() - started) * 1000
        if response.completion is None or "ELMOS_PROVIDER_CONFORMANCE_OK" not in response.completion.summary:
            raise AssertionError(config.provider + " failed the frozen completion oracle")
        if response.completion.claimed_status != "blocked":
            raise AssertionError(config.provider + " was allowed to self-certify completion")
        if response.provider_checkpoint is None or not response.provider_checkpoint.get(
            "provider_response_id"
        ):
            raise AssertionError(config.provider + " returned no response identity")
        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        latencies.append(elapsed_ms)
        successful_adapters += 1
        details[config.provider] = {
            "model": model,
            "protocol": config.protocol,
            "latency_ms": round(elapsed_ms, 3),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "response_id_digest": digest_of(str(response.provider_checkpoint["provider_response_id"])),
            "normalized_status": response.completion.claimed_status,
        }
    status = "PASS" if not failures and successful_adapters == len(configs) else "FAIL"
    findings = [
        "EXTERNAL_PROVIDER_CALLS_SELF_ATTESTED",
        "SESSION_CHECKPOINT_RESUME_CANCEL_NOT_SUPPORTED_BY_ONESHOT_PROTOCOLS",
        "PROVIDER_BILLING_RECONCILIATION_NOT_RUN",
        "INDEPENDENT_VERIFICATION_NOT_RUN",
    ]
    if failures:
        findings.append("EXTERNAL_PROVIDER_FAILURES_RECORDED")
        details["failures"] = failures
    return ProbeResult(
        "provider-real",
        status,
        {
            "external_adapters": len(configs),
            "successful_adapters": successful_adapters,
            "failed_adapters": len(failures),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "latency_p95_ms": round(_percentile(latencies, 95), 3),
        },
        tuple(findings),
        details,
    )


def run_security_scan(source_root: str | Path) -> ProbeResult:
    """Run a local Bandit scan; the result is never treated as an independent review."""

    root = Path(source_root).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("security scan source root is invalid")
    result = subprocess.run(
        ["bandit", "-q", "-r", str(root), "-f", "json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=300,
        check=False,
    )
    raw = result.stdout.decode("utf-8", errors="replace")
    try:
        report = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        raise RuntimeError("security scanner did not return JSON") from error
    findings = report.get("results", []) if isinstance(report, Mapping) else []
    if not isinstance(findings, list):
        raise TypeError("security scanner returned an invalid result set")
    severity: dict[str, int] = {}
    for finding in findings:
        if isinstance(finding, Mapping):
            level = str(finding.get("issue_severity", "UNSPECIFIED"))
            severity[level] = severity.get(level, 0) + 1
    blocking_findings = severity.get("HIGH", 0) + severity.get("MEDIUM", 0)
    status = "PASS" if result.returncode in {0, 1} and blocking_findings == 0 else "FAIL"
    return ProbeResult(
        "security-scan-local",
        status,
        {
            "findings": len(findings),
            "exit_code": result.returncode,
            **{f"severity_{key.lower()}": value for key, value in severity.items()},
        },
        (
            "LOCAL_BANDIT_SELF_ATTESTED",
            "INDEPENDENT_SECURITY_REVIEW_NOT_RUN",
            "SUPPLY_CHAIN_ATTESTATION_NOT_RUN",
        )
        + (("SECURITY_FINDINGS_RECORDED",) if findings else ()),
        {
            "source_root": str(root),
            "report_digest": digest_of(report),
            "blocking_findings": blocking_findings,
            "nonblocking_findings": len(findings) - blocking_findings,
        },
    )


def run_browser_probe() -> ProbeResult:
    """Run Chromium, Firefox, WebKit and emulated-mobile Playwright evidence."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _QualificationPage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-browser-cas-") as temporary:
            artifacts = ContentAddressedStore(Path(temporary) / "cas")
            evidence_runner = BrowserEvidenceRunner(
                artifacts,
                secret_values=("qualification-secret",),
            )
            matrix_runner = BrowserMatrixRunner(evidence_runner, attempts=1)
            identity = Identity(
                "qualification-a",
                "project-a",
                "task-browser",
                "browser-" + uuid.uuid4().hex,
            )
            scenario = BrowserScenario(
                "browser-live-matrix-v1",
                "real browser privacy and evidence",
                ("local disposable HTTP origin",),
                (
                    BrowserStep("navigate", value="/"),
                    BrowserStep(
                        "fill",
                        locator="label=Qualification secret",
                        value="qualification-secret",
                        sensitive=True,
                    ),
                    BrowserStep("click", locator="role=button|Save"),
                    BrowserStep("assert_text", locator="role=status", assertion="Saved"),
                ),
            )
            result = matrix_runner.run(
                identity,
                scenario,
                DEFAULT_BROWSER_PROFILES,
                lambda profile: PlaywrightBrowserDriver(profile, base_url=base_url),
            )
            profiles: dict[str, Any] = {}
            for name, evidence in result.profiles.items():
                kinds = sorted(reference.kind for reference in evidence.artifact_refs)
                if evidence.status != "pass" or "browser-trace.zip" not in kinds:
                    raise AssertionError(name + " did not produce passing trace evidence")
                if not any(
                    kind in {"browser-video.webm", "browser-video-unavailable.json"} for kind in kinds
                ):
                    raise AssertionError(name + " did not produce a video disposition")
                profiles[name] = {
                    "status": evidence.status,
                    "evidence_digest": evidence.digest,
                    "artifact_kinds": kinds,
                }
            if result.classification != "PASS":
                raise AssertionError("browser matrix classification is " + result.classification)
            return ProbeResult(
                "browser-real",
                "PASS",
                {
                    "profiles": len(profiles),
                    "engines": 3,
                    "emulated_devices": 1,
                    "failed_profiles": 0,
                },
                (
                    "LOCAL_PLAYWRIGHT_BROWSER_BINARIES_SELF_ATTESTED",
                    "PHYSICAL_DEVICE_LAB_NOT_RUN",
                    "INDEPENDENT_VERIFICATION_NOT_RUN",
                ),
                {
                    "classification": result.classification,
                    "matrix_digest": result.digest,
                    "profiles": profiles,
                },
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_docker_sandbox_probe(image_reference: str) -> ProbeResult:
    """Exercise a digest-pinned, rootless, read-only, network-none Docker L1."""

    if "@sha256:" not in image_reference or any(char.isspace() for char in image_reference):
        raise ValueError("sandbox probe requires a digest-pinned image reference")
    name = "elmos-oh-sandbox-" + uuid.uuid4().hex[:16]
    command = [
        "docker",
        "create",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65532:65532",
        "--cpus=0.5",
        "--memory=128m",
        "--pids-limit=64",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=32m",
        image_reference,
        "sleep",
        "300",
    ]
    container_id = _command(command).strip()
    cleanup_ok = False
    try:
        _command(["docker", "start", container_id])
        inspection = json.loads(_command(["docker", "inspect", container_id]))[0]
        host = inspection["HostConfig"]
        config = inspection["Config"]
        checks = {
            "non_root_user": config["User"] == "65532:65532",
            "read_only_root": bool(host["ReadonlyRootfs"]),
            "network_none": host["NetworkMode"] == "none",
            "capabilities_dropped": "ALL" in (host.get("CapDrop") or []),
            "no_new_privileges": "no-new-privileges" in (host.get("SecurityOpt") or []),
            "pid_limit": int(host["PidsLimit"]) == 64,
            "memory_limit": int(host["Memory"]) == 134_217_728,
            "cpu_limit": int(host["NanoCpus"]) == 500_000_000,
            "no_host_mounts": not inspection.get("Mounts"),
            "runtime_uid": _docker_exec(container_id, ["id", "-u"]).stdout.decode().strip() == "65532",
            "tmp_writable": _docker_exec(
                container_id,
                ["sh", "-c", "touch /tmp/qualification && test -f /tmp/qualification"],
            ).returncode
            == 0,
            "root_write_denied": _docker_exec(
                container_id,
                ["sh", "-c", "touch /qualification-escape"],
            ).returncode
            != 0,
            "mount_denied": _docker_exec(
                container_id,
                ["sh", "-c", "mkdir /tmp/m && mount -t proc proc /tmp/m"],
            ).returncode
            != 0,
            "network_denied": _docker_exec(
                container_id,
                ["ping", "-c", "1", "-W", "1", "1.1.1.1"],
            ).returncode
            != 0,
        }
        status_text = _docker_exec(container_id, ["cat", "/proc/self/status"]).stdout.decode()
        checks["effective_caps_zero"] = "CapEff:\t0000000000000000" in status_text
        checks["kernel_no_new_privs"] = "NoNewPrivs:\t1" in status_text
        if not all(checks.values()):
            failed = sorted(name for name, passed in checks.items() if not passed)
            raise AssertionError("sandbox checks failed: " + ",".join(failed))
        details = {
            "container_id_digest": digest_of(container_id),
            "image_reference": image_reference,
            "isolation_class": "L1",
            "checks": checks,
        }
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container_id],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        cleanup = subprocess.run(
            ["docker", "inspect", container_id],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
        cleanup_ok = cleanup.returncode != 0
    if not cleanup_ok:
        raise AssertionError("sandbox orphan cleanup failed")
    return ProbeResult(
        "docker-sandbox-real",
        "PASS",
        {"negative_checks": len(details["checks"]), "cleanup_ok": 1},
        (
            "LOCAL_DOCKER_L1_SELF_ATTESTED",
            "PRODUCTION_L3_L4_SANDBOX_NOT_RUN",
            "SECRET_BROKER_INTEGRATION_NOT_RUN",
            "INDEPENDENT_ESCAPE_REVIEW_NOT_RUN",
        ),
        details,
    )


def run_chaos_probe(
    dsn: str,
    *,
    postgres_container: str,
    temporal_container: str,
    temporal_address: str,
    sandbox_image_reference: str,
) -> ProbeResult:
    """Execute fifteen bounded failure/recovery checks against disposable services."""

    if not all((dsn, postgres_container, temporal_container, temporal_address, sandbox_image_reference)):
        raise ValueError("chaos probe requires explicit disposable service targets")
    suffix = uuid.uuid4().hex
    identity = Identity("qualification-chaos", "project-chaos", "task-chaos", "chaos-" + suffix)
    manifest = "sha256:" + hashlib.sha256(("chaos:" + suffix).encode()).hexdigest()
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, operation: Any) -> None:
        try:
            details = operation()
            checks[name] = {"status": "PASS", **(details if isinstance(details, Mapping) else {})}
        except Exception as error:  # noqa: BLE001 - every injection must be recorded and the matrix must continue
            checks[name] = {
                "status": "FAIL",
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            }

    ledger = PostgresEventLedger.connect(dsn)
    try:
        ledger.create_run(identity, manifest)
        initial = ledger.append(
            identity,
            "run.status",
            {"status": "running"},
            idempotency_key="chaos-initial",
        )
        record("idempotency_replay", lambda: _chaos_idempotency_replay(ledger, identity, initial))
        record("idempotency_conflict", lambda: _chaos_idempotency_conflict(ledger, identity))
        record("tenant_isolation", lambda: _chaos_tenant_isolation(ledger, identity))
        record("stale_lease_fencing", lambda: _chaos_stale_lease(ledger, identity))
        record("hash_chain", lambda: {"verified": ledger.verify_chain(identity.tenant_id, identity.run_id)})
        record(
            "projection_rebuild",
            lambda: {"digest": digest_of(ledger.rebuild_projection(identity.tenant_id, identity.run_id))},
        )
        checkpoint_id = ledger.save_checkpoint(
            identity,
            event_seq=initial.seq,
            manifest_hash=manifest,
            state={"phase": "chaos"},
        )
        record(
            "checkpoint_replay",
            lambda: _chaos_checkpoint_replay(ledger, identity, manifest, checkpoint_id),
        )
    finally:
        ledger.close()

    update_rows, delete_rows, _ = _postgres_append_only_checks(dsn, identity)
    checks["append_only_update"] = {"status": "PASS" if update_rows == 0 else "FAIL", "rows": update_rows}
    checks["append_only_delete"] = {"status": "PASS" if delete_rows == 0 else "FAIL", "rows": delete_rows}

    def reconnect() -> Mapping[str, Any]:
        reopened = PostgresEventLedger.connect(dsn)
        try:
            return {
                "run_readable": reopened.run(identity.tenant_id, identity.run_id).identity.run_id
                == identity.run_id
            }
        finally:
            reopened.close()

    record("reconnect_after_client_close", reconnect)
    record("postgres_restart_recovery", lambda: _chaos_postgres_restart(dsn, postgres_container, identity))
    record("postgres_pause_recovery", lambda: _chaos_postgres_pause(dsn, postgres_container, identity))
    record("temporal_restart_recovery", lambda: _chaos_temporal_restart(temporal_container, temporal_address))
    record("sandbox_cleanup", lambda: _chaos_sandbox_cleanup(sandbox_image_reference))
    record("bounded_load_recovery", lambda: _chaos_load_recovery(dsn))

    failures = {name: value for name, value in checks.items() if value.get("status") != "PASS"}
    return ProbeResult(
        "chaos-real",
        "PASS" if len(checks) == 15 and not failures else "FAIL",
        {
            "failure_injections": len(checks),
            "passed_injections": len(checks) - len(failures),
            "failed_injections": len(failures),
        },
        (
            "LOCAL_DISPOSABLE_CHAOS_SELF_ATTESTED",
            "PRODUCTION_TOPOLOGY_CHAOS_NOT_RUN",
            "MULTI_REGION_DR_NOT_RUN",
            "INDEPENDENT_VERIFICATION_NOT_RUN",
        )
        + (("CHAOS_FAILURES_RECORDED",) if failures else ()),
        {
            "manifest_digest": manifest,
            "checks": checks,
            "failures": failures,
        },
    )


def _chaos_idempotency_replay(
    ledger: PostgresEventLedger, identity: Identity, initial: Any
) -> Mapping[str, Any]:
    replay = ledger.append(
        identity,
        "run.status",
        {"status": "running"},
        idempotency_key="chaos-initial",
    )
    if replay.event_id != initial.event_id:
        raise AssertionError("idempotency replay created a duplicate event")
    return {"event_id_digest": digest_of(replay.event_id)}


def _chaos_idempotency_conflict(ledger: PostgresEventLedger, identity: Identity) -> Mapping[str, Any]:
    try:
        ledger.append(identity, "run.status", {"status": "blocked"}, idempotency_key="chaos-initial")
    except IdempotencyConflict:
        return {"conflict_rejected": True}
    raise AssertionError("idempotency conflict was accepted")


def _chaos_tenant_isolation(ledger: PostgresEventLedger, identity: Identity) -> Mapping[str, Any]:
    try:
        ledger.events("qualification-other", identity.run_id)
    except TenantIsolationError:
        return {"cross_tenant_hidden": True}
    raise AssertionError("cross-tenant run was readable")


def _chaos_stale_lease(ledger: PostgresEventLedger, identity: Identity) -> Mapping[str, Any]:
    now = time.time()
    old = ledger.acquire_lease(identity, "chaos-owner-a", 1.0, now)
    ledger.acquire_lease(identity, "chaos-owner-b", 1.0, now + 2.0)
    try:
        ledger.assert_lease(old, now + 2.0)
    except LeaseLost:
        return {"stale_fence_rejected": True}
    raise AssertionError("stale fencing token was accepted")


def _chaos_checkpoint_replay(
    ledger: PostgresEventLedger, identity: Identity, manifest: str, checkpoint_id: str
) -> Mapping[str, Any]:
    replay = ledger.save_checkpoint(
        identity,
        event_seq=0,
        manifest_hash=manifest,
        state={"phase": "chaos"},
    )
    if replay != checkpoint_id:
        raise AssertionError("checkpoint replay changed its content identity")
    return {"checkpoint_id_digest": digest_of(checkpoint_id)}


def _chaos_container_running(container: str) -> bool:
    return _command(["docker", "inspect", "--format", "{{.State.Running}}", container]).strip() == "true"


def _chaos_postgres_restart(dsn: str, container: str, identity: Identity) -> Mapping[str, Any]:
    _command(["docker", "restart", container], timeout=120)
    _wait_for_postgres_ready(dsn, container)
    reopened = PostgresEventLedger.connect(dsn)
    try:
        return {
            "run_readable": reopened.run(identity.tenant_id, identity.run_id).identity.run_id
            == identity.run_id
        }
    finally:
        reopened.close()


def _chaos_postgres_pause(dsn: str, container: str, identity: Identity) -> Mapping[str, Any]:
    _command(["docker", "pause", container], timeout=30)
    paused = False
    try:
        paused = _command(["docker", "inspect", "--format", "{{.State.Paused}}", container]).strip() == "true"
    finally:
        _command(["docker", "unpause", container], timeout=30)
    if not paused:
        raise AssertionError("PostgreSQL pause/unpause did not reach both states")
    _wait_for_postgres_ready(dsn, container)
    reopened = PostgresEventLedger.connect(dsn)
    try:
        return {
            "run_readable": reopened.run(identity.tenant_id, identity.run_id).identity.run_id
            == identity.run_id
        }
    finally:
        reopened.close()


def _chaos_temporal_restart(container: str, address: str) -> Mapping[str, Any]:
    _command(["docker", "restart", container], timeout=120)
    _wait_for_temporal_health(container, address)
    return {"cluster_health": "SERVING"}


def _wait_for_postgres_ready(dsn: str, container: str, *, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if _chaos_container_running(container):
            try:
                connection = PostgresEventLedger.connect(dsn)
                connection.close()
                return
            except Exception as error:  # noqa: BLE001 - readiness retries record only the final bounded error
                last_error = str(error)[:200]
        time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready: " + last_error)


def _wait_for_temporal_health(container: str, address: str, *, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if _chaos_container_running(container):
            result = subprocess.run(
                ["temporal", "operator", "cluster", "health", "--address", address],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=15,
                check=False,
            )
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            if result.returncode == 0 and "SERVING" in output:
                return
            last_error = output[-300:]
        time.sleep(1)
    raise RuntimeError("Temporal did not become ready: " + last_error)


def _chaos_sandbox_cleanup(image_reference: str) -> Mapping[str, Any]:
    result = run_docker_sandbox_probe(image_reference)
    if result.status != "PASS" or result.metrics.get("cleanup_ok") != 1:
        raise AssertionError("sandbox cleanup probe failed")
    return {"cleanup_ok": True, "container_id_digest": result.details.get("container_id_digest", "")}


def _chaos_load_recovery(dsn: str) -> Mapping[str, Any]:
    result = run_load_probe(dsn, concurrency=4, events=16)
    if result.status != "PASS":
        raise AssertionError("bounded load recovery probe failed")
    return {"events": result.metrics.get("events"), "chain_verified": result.details.get("chain_verified")}


@dataclass(frozen=True, slots=True)
class GoldenRepositorySpec:
    repository_id: str
    url: str
    revision: str = "HEAD"


def run_golden_repository_probe(
    repositories: Sequence[GoldenRepositorySpec],
    *,
    clone_root: str | Path,
) -> ProbeResult:
    """Clone exact public revisions sequentially and execute a bounded repo task."""

    if len(repositories) < 3:
        raise ValueError("golden probe requires at least three repositories")
    root = Path(clone_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    measured: list[GoldenRepository] = []
    details: dict[str, Any] = {}
    started = time.monotonic()
    for index, spec in enumerate(repositories):
        destination = root / f"repo-{index}-{uuid.uuid4().hex[:8]}"
        if destination.exists():
            raise ValueError("golden clone destination already exists")
        try:
            _command(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--filter=blob:none",
                    "--no-tags",
                    spec.url,
                    str(destination),
                ],
                timeout=1800,
            )
            if spec.revision != "HEAD":
                _command(
                    ["git", "fetch", "--depth=1", "origin", spec.revision], cwd=destination, timeout=1800
                )
                _command(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=destination, timeout=300)
            commit = _command(["git", "rev-parse", "HEAD"], cwd=destination).strip()
            loc, files, tests, inventory_digest = _measure_repository(destination)
            commit_digest = digest_of({"url": spec.url, "commit": commit})
            measured.append(
                GoldenRepository(
                    spec.repository_id,
                    commit_digest,
                    loc,
                    ("polyglot",),
                    ("bounded-source-inventory-v1",),
                )
            )
            details[spec.repository_id] = {
                "url": spec.url,
                "native_commit": commit,
                "commit_binding": commit_digest,
                "source_loc": loc,
                "source_files": files,
                "test_files": tests,
                "inventory_digest": inventory_digest,
            }
        finally:
            if destination.exists():
                shutil.rmtree(destination)
    validated = GoldenSuiteValidator().validate(measured)
    return ProbeResult(
        "golden-repositories-real",
        "PASS",
        {
            "repositories": len(validated),
            "repositories_over_500k_loc": sum(item.loc > 500_000 for item in validated),
            "repositories_over_1m_loc": sum(item.loc > 1_000_000 for item in validated),
            "total_source_loc": sum(item.loc for item in validated),
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        (
            "PUBLIC_GOLDEN_REPOSITORIES_SELF_ATTESTED",
            "INDEPENDENT_HOLDOUT_NOT_RUN",
            "CUSTOMER_ACCEPTANCE_NOT_RUN",
        ),
        details,
    )


class _QualificationPage(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        body = b"""<!doctype html><html lang='en'><head><meta charset='utf-8'><title>ELMOS qualification</title></head>
<body><main><h1>Qualification</h1><label>Qualification secret<input type='password' id='secret'></label>
<button id='save'>Save</button><p role='status' aria-live='polite'>Pending</p></main>
<script>document.querySelector('#save').addEventListener('click',()=>{document.querySelector('[role=status]').textContent='Saved';});</script>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _postgres_append_only_checks(dsn: str, identity: Identity) -> tuple[int, int, str]:
    import psycopg

    def attempt(statement: LiteralString) -> int:
        try:
            with (
                psycopg.connect(dsn, autocommit=False) as connection,
                connection.transaction(),
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT set_config('elmos.tenant_id', %s, true)",
                    (identity.tenant_id,),
                )
                cursor.execute(statement, (identity.tenant_id, identity.run_id))
                return cursor.rowcount
        except psycopg.errors.RaiseException as error:
            if "append-only" not in str(error):
                raise
            return 0

    update_rows = attempt(
        "UPDATE oh_execution_events SET event_type='tampered' WHERE tenant_id=%s AND run_id=%s"
    )
    delete_rows = attempt("DELETE FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s")
    with psycopg.connect(dsn, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("SHOW server_version")
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return its server version")
        server_version = str(row[0])
    return update_rows, delete_rows, server_version


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _command(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float = 300,
) -> str:
    result = subprocess.run(
        list(argv),
        cwd=None if cwd is None else str(cwd),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"command failed ({result.returncode}): {argv[0]}: {detail}")
    return result.stdout.decode("utf-8", errors="strict")


def _docker_exec(container_id: str, argv: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["docker", "exec", container_id, *argv],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        check=False,
    )


_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".dart",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}


def _measure_repository(root: Path) -> tuple[int, int, int, str]:
    tracked = _command(["git", "ls-files", "-z"], cwd=root).split("\0")
    source_files = sorted(path for path in tracked if path and Path(path).suffix.lower() in _SOURCE_SUFFIXES)
    loc = 0
    tests = 0
    inventory: list[tuple[str, int, int]] = []
    for relative in source_files:
        path = root / relative
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        lines = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
        loc += lines
        tests += int("test" in relative.lower())
        inventory.append((relative, len(raw), lines))
    digest = "sha256:" + hashlib.sha256(canonical_json(inventory).encode()).hexdigest()
    return loc, len(source_files), tests, digest
