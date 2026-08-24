"""``elmos cache`` command line.

Implements the CLI contract. Two defaults that matter operationally:

* commands are **non-destructive and project-scoped by default** -- ``gc``
  plans, it does not delete, until an explicit ``--apply`` with a plan id;
* mutating commands require an explicit scope and, where the state can race,
  an ``--expected-version`` or ``--lease-epoch``, plus an idempotency key.

Output is JSON by default so it can be piped into evidence collection; ``--text``
prints a human summary of the same data.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .action_cache import ActionCache, HotIndex
from .atomic import atomic_write_bytes
from .cache_policy import PolicyName, create_policy
from .cache_simulator import ObjectiveProfile, benchmark, recommended_capacity
from .cache_trace import (
    GENERATORS,
    Split,
    TraceCorpus,
    assert_privacy,
    detect_drift,
    detect_leakage,
    sufficient_sample,
    workload_features,
)
from .canonical import digest_of, normalize_logical_path, require_digest, resolve_within, sha256_bytes
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .config import CacheConfig, default_config, load_config
from .context_compaction import (
    CompactionPolicy,
    ContextCheckpoint,
    ContextCheckpointSections,
    ContextCompactionService,
    Ed25519ContextWarmTrustVerifier,
    SourceLinkedItem,
)
from .context_ledger import RepositoryContextLedger
from .db import MetadataStore, RunRecord, StagedFileRecord, open_store
from .enums import RunStatus, StagedFileStatus, TrustNamespace
from .environment_cache import (
    EnvironmentKeyInputs,
    PlatformIdentity,
    RestoreAction,
    RestoreEstimate,
    build_environment_snapshot_key,
)
from .environment_service import (
    EnvironmentLayerPayload,
    EnvironmentLayerType,
    EnvironmentSnapshotService,
    RestoreCostPolicy,
)
from .errors import ConflictError, ContractViolation, ElmosCacheError, NotFound, SecretDetected
from .gc import GarbageCollector, RetentionPolicy, explain_retention
from .journal import LeaseManager, RunCoordinator, RunJournal
from .parity_api import (
    compile_prompt_prefix_payload,
    evaluate_cache_parity_payload,
)
from .parity_evidence import CasParityEvidenceVerifier
from .parity_runtime import ParityRuntime
from .parity_store import ParityMetadataRepository
from .policy_certification import (
    CertificationContext,
    RolloutPlan,
    benchmark_matrix,
    certify_policy,
)
from .policy_orchestrator import RuleSelector, configuration_digest
from .policy_plane import PolicyPlane
from .prompt_tools import first_prefix_difference
from .security import MAX_SCAN_BYTES, Ed25519ProvenanceSigner, SecretScanner, open_no_follow
from .staging import Workspace

SCHEMA_VERSION = "1.0.0"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNHEALTHY = 2


@dataclass
class Context:
    config: CacheConfig
    base: Path
    tenant_id: str
    project_id: str | None
    store: MetadataStore
    cas: ContentAddressableStore
    clock: Clock = SYSTEM_CLOCK

    @property
    def action_cache(self) -> ActionCache:
        return ActionCache(
            self.store,
            self.cas,
            self.clock,
            hot_index=HotIndex.from_config(self.config.policy),
        )

    def collector(self) -> GarbageCollector:
        retention = self.config.retention
        return GarbageCollector(
            self.store,
            self.cas,
            self.tenant_id,
            RetentionPolicy(
                successful_run_days=retention.successful_run_days,
                failed_run_days=retention.failed_run_days,
                quarantine_days=retention.quarantine_days,
                grace_hours=retention.gc_grace_hours,
                protect_published=retention.protect_published,
                protect_checkpoints=retention.protect_checkpoints,
                protect_certificates=retention.protect_certificates,
                quota_bytes=self.config.local.max_size_gb * 1024**3,
            ),
            self.clock,
            replacement=(
                create_policy(self.config.policy.l2_policy, self.config.local.max_size_gb * 1024**3)
                if self.config.policy.enabled
                else None
            ),
        )

    def owned_run(self, run_id: str) -> RunRecord:
        """Resolve a global run id only through the authenticated CLI scope."""

        if self.project_id is None:
            row = self.store.query_one(
                "SELECT run_id FROM runs WHERE run_id=? AND tenant_id=?",
                (run_id, self.tenant_id),
            )
        else:
            row = self.store.query_one(
                "SELECT run_id FROM runs WHERE run_id=? AND tenant_id=? AND project_id=?",
                (run_id, self.tenant_id, self.project_id),
            )
        if row is None:
            raise NotFound("run does not exist in this scope")
        run = self.store.get_run(str(row[0]))
        if run.tenant_id != self.tenant_id or (self.project_id is not None and run.project_id != self.project_id):
            raise NotFound("run does not exist in this scope")
        return run

    def owned_staged_file(self, run_id: str, staged_file_id: str) -> StagedFileRecord:
        """Resolve a staged-file id without revealing cross-scope existence."""

        run = self.owned_run(run_id)
        row = self.store.query_one(
            "SELECT staged_file_id FROM staged_files WHERE staged_file_id=? AND run_id=?"
            " AND tenant_id=? AND project_id=?",
            (staged_file_id, run_id, self.tenant_id, run.project_id),
        )
        if row is None:
            raise NotFound("staged file does not exist in this scope")
        record = self.store.get_staged_file(str(row[0]))
        if record.tenant_id != self.tenant_id or record.project_id != run.project_id or record.run_id != run_id:
            raise NotFound("staged file does not exist in this scope")
        return record

    def workspace(self, run_id: str) -> Workspace:
        run = self.owned_run(run_id)
        return Workspace(
            self.base / self.config.workspace.root,
            self.tenant_id,
            run.project_id,
            run_id,
            self.store,
            self.cas,
            config=self.config.workspace,
            clock=self.clock,
        )

    def coordinator(self, run_id: str) -> RunCoordinator:
        workspace = self.workspace(run_id)
        journal = RunJournal(workspace.root / "control" / "journal.ndjson", run_id, self.clock)
        return RunCoordinator(self.store, journal, LeaseManager(self.store, self.clock), clock=self.clock)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos cache", description=__doc__)
    parser.add_argument("--config", type=Path, help="path to elmos-cache.yaml")
    parser.add_argument("--base", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--tenant",
        help="tenant scope (defaults to 'default'; context operations require it explicitly)",
    )
    parser.add_argument("--project", help="project scope")
    parser.add_argument("--text", action="store_true", help="human-readable output")
    subparsers = parser.add_subparsers(dest="group", required=True)

    cache = subparsers.add_parser("cache", help="cache inspection and maintenance").add_subparsers(
        dest="command", required=True
    )
    cache.add_parser("status", help="summary of local cache health")
    inspect = cache.add_parser("inspect", help="inspect one ActionKey")
    inspect.add_argument("action_key")
    explain = cache.add_parser("explain-miss", help="explain why a node missed")
    explain.add_argument("run_id")
    explain.add_argument("node_id")
    explain_v12 = cache.add_parser("explain", help="explain all v1.2 layer outcomes for one request")
    explain_v12.add_argument("request_id")
    verify = cache.add_parser("verify", help="verify stored objects")
    verify.add_argument("--deep", action="store_true", help="rehash every object")
    pin = cache.add_parser("pin", help="protect an artifact or tree from GC")
    pin.add_argument("subject")
    pin.add_argument("--kind", default="artifact", choices=["artifact", "file_tree", "checkpoint"])
    pin.add_argument("--reason", required=True)
    pin.add_argument("--expires-in-hours", type=float)
    unpin = cache.add_parser("unpin", help="remove a pin")
    unpin.add_argument("pin_id")
    gc = cache.add_parser("gc", help="garbage collection (dry-run by default)")
    gc.add_argument("--dry-run", action="store_true", default=True)
    gc.add_argument("--apply", dest="apply_plan", metavar="PLAN_ID")
    gc.add_argument("--idempotency-key", help="required with --apply")
    explain_pin = cache.add_parser("explain-retention", help="why an artifact was kept or dropped")
    explain_pin.add_argument("digest")

    workspace = subparsers.add_parser("workspace", help="workspace inspection and recovery").add_subparsers(
        dest="command", required=True
    )
    workspace.add_parser("list", help="list workspaces")
    inspect_ws = workspace.add_parser("inspect", help="inspect one run workspace")
    inspect_ws.add_argument("run_id")
    recover = workspace.add_parser("recover", help="run the recovery plan for a workspace")
    recover.add_argument("run_id")
    recover.add_argument("--plan-only", action="store_true")
    quarantine = workspace.add_parser("quarantine", help="quarantine a staged file")
    quarantine.add_argument("run_id")
    quarantine.add_argument("staged_file_id")
    quarantine.add_argument("--reason", required=True)

    run = subparsers.add_parser("run", help="run lifecycle").add_subparsers(dest="command", required=True)
    for name, help_text in (("resume", "resume a run"), ("pause", "pause a run"), ("cancel", "cancel a run")):
        sub = run.add_parser(name, help=help_text)
        sub.add_argument("run_id")
        sub.add_argument("--expected-version", type=int, required=name != "resume")
        sub.add_argument("--idempotency-key", required=True)
        if name == "cancel":
            sub.add_argument("--reason", required=True)

    artifact = subparsers.add_parser("artifact", help="artifact operations").add_subparsers(
        dest="command", required=True
    )
    materialize = artifact.add_parser("materialize", help="write an artifact to a path")
    materialize.add_argument("digest")
    materialize.add_argument("destination", type=Path)

    policy = subparsers.add_parser(
        "policy", help="cache replacement policy: benchmark, select, certify"
    ).add_subparsers(dest="command", required=True)

    def _corpus_arguments(sub: argparse.ArgumentParser) -> None:
        source = sub.add_mutually_exclusive_group(required=True)
        source.add_argument("--workload", choices=sorted(GENERATORS), help="a built-in workload")
        source.add_argument("--trace", type=Path, help="a captured trace in JSONL form")

    policy.add_parser("show", help="the configured policy for each tier")

    policy_benchmark = policy.add_parser("benchmark", help="replay every candidate on one trace")
    _corpus_arguments(policy_benchmark)
    policy_benchmark.add_argument("--capacity-fraction", type=float, default=0.2)
    policy_benchmark.add_argument("--capacity-bytes", type=int)
    policy_benchmark.add_argument("--objective", default=None)
    policy_benchmark.add_argument("--baseline", default="LRU")
    policy_benchmark.add_argument("--candidate", action="append", dest="candidates")
    policy_benchmark.add_argument("--split", default=None, help="restrict to one split")

    policy_matrix = policy.add_parser("matrix", help="every workload against every capacity")
    policy_matrix.add_argument("--capacity-fraction", type=float, action="append", dest="fractions")
    policy_matrix.add_argument("--objective", default=None)

    policy_select = policy.add_parser("select", help="what the rule selector recommends")
    _corpus_arguments(policy_select)

    policy_certify = policy.add_parser("certify", help="certify a candidate on the test window")
    _corpus_arguments(policy_certify)
    policy_certify.add_argument("--candidate", required=True)
    policy_certify.add_argument("--objective", default=None)
    policy_certify.add_argument("--capacity-fraction", type=float, default=0.2)
    policy_certify.add_argument("--elmos-commit", required=True)
    policy_certify.add_argument("--hardware-profile", default="unspecified")
    policy_certify.add_argument(
        "--signing-key",
        type=Path,
        help="hex-encoded ed25519 seed; without it an ephemeral key is used and said so",
    )
    for evidence in ("shadow", "canary", "rollback"):
        policy_certify.add_argument(
            f"--{evidence}-evidence",
            type=Path,
            help=f"JSON file recording the {evidence} stage of the rollout ladder",
        )
    policy_certify.add_argument("--issued-at", default="1970-01-01T00:00:00+00:00")

    trace = subparsers.add_parser("trace", help="cache trace capture and inspection").add_subparsers(
        dest="command", required=True
    )
    trace_generate = trace.add_parser("generate", help="write a built-in workload to JSONL")
    trace_generate.add_argument("--workload", choices=sorted(GENERATORS), required=True)
    trace_generate.add_argument("--out", type=Path, required=True)
    trace_verify = trace.add_parser("verify", help="privacy, leakage, drift and sample checks")
    trace_verify.add_argument("--trace", type=Path, required=True)
    trace.add_parser("workloads", help="list the built-in workloads")

    prompt = subparsers.add_parser("prompt", help="canonical prompt-prefix compilation and diagnostics").add_subparsers(
        dest="command", required=True
    )
    prompt_compile = prompt.add_parser("compile", help="compile a content-free prefix manifest")
    prompt_compile.add_argument("--input", type=Path, required=True)
    prompt_compile.add_argument("--persist", action="store_true")
    prompt_compile.add_argument("--idempotency-key")
    prompt_diff = prompt.add_parser("diff", help="first content-free prefix difference")
    prompt_diff.add_argument("--previous", type=Path, required=True)
    prompt_diff.add_argument("--current", type=Path, required=True)

    environment = subparsers.add_parser("environment", help="environment snapshot inspection").add_subparsers(
        dest="command", required=True
    )
    environment_inspect = environment.add_parser(
        "inspect", help="verify immutable manifest, layers, trust and restore economics"
    )
    environment_inspect.add_argument("snapshot_key")
    environment_inspect.add_argument("--trust-namespace", required=True)
    environment_inspect.add_argument("--transfer-ms", type=float, required=True)
    environment_inspect.add_argument("--decompression-ms", type=float, required=True)
    environment_inspect.add_argument("--verification-ms", type=float, required=True)
    environment_inspect.add_argument("--rebuild-ms", type=float, required=True)
    environment_inspect.add_argument("--minimum-savings-ms", type=float, required=True)
    environment_inspect.add_argument("--maximum-restore-ratio", type=float, required=True)
    environment_seal = environment.add_parser("seal", help="seal bounded, secret-scanned repository-local layer files")
    environment_seal.add_argument("--input", type=Path, required=True, help="digest-only key inputs")
    environment_seal.add_argument(
        "--layer",
        action="append",
        required=True,
        help="typed repository-local layer in TYPE=relative/path form",
    )
    environment_seal.add_argument("--trust-namespace", required=True)
    environment_seal.add_argument("--expires-at", type=float)
    environment_seal.add_argument("--idempotency-key", required=True)
    environment_restore = environment.add_parser(
        "restore", help="restore verified layers into a new repository-local directory"
    )
    environment_restore.add_argument("--input", type=Path, required=True, help="digest-only key inputs")
    environment_restore.add_argument("--trust-namespace", required=True)
    environment_restore.add_argument("--output-dir", required=True)
    environment_restore.add_argument("--rebuild-ms", type=float, required=True)
    environment_restore.add_argument("--transfer-bytes-per-ms", type=float, required=True)
    environment_restore.add_argument("--decompression-bytes-per-ms", type=float, required=True)
    environment_restore.add_argument("--verification-bytes-per-ms", type=float, required=True)
    environment_restore.add_argument("--minimum-savings-ms", type=float, required=True)
    environment_restore.add_argument("--maximum-restore-ratio", type=float, required=True)
    environment_restore.add_argument("--idempotency-key", required=True)

    affinity = subparsers.add_parser("affinity", help="cache-locality routing decisions").add_subparsers(
        dest="command", required=True
    )
    affinity_decide = affinity.add_parser("decide", help="rank compatible targets")
    affinity_decide.add_argument("--input", type=Path, required=True)
    affinity_decide.add_argument("--persist", action="store_true")
    affinity_decide.add_argument("--idempotency-key")

    parity = subparsers.add_parser("parity", help="measured-only v1.2 parity evaluation").add_subparsers(
        dest="command", required=True
    )
    parity.add_parser("status", help="parity feature flags and durable record counts")
    parity_evaluate = parity.add_parser("evaluate", help="evaluate supplied measurements without executing providers")
    parity_evaluate.add_argument("--input", type=Path, required=True)
    parity_evaluate.add_argument("--persist", action="store_true")
    parity_evaluate.add_argument("--idempotency-key")
    parity_report = parity.add_parser("report", help="read one immutable parity report")
    parity_report.add_argument("report_id")

    context_commands = subparsers.add_parser(
        "context", help="durable context compaction planning and checkpoint operations"
    ).add_subparsers(dest="command", required=True)

    def _context_scope_arguments(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--stream", required=True, help="exact durable context stream id")
        sub.add_argument("--branch-lineage", required=True, help="exact branch lineage binding")
        sub.add_argument("--snapshot", required=True, help="exact repository snapshot digest")
        sub.add_argument(
            "--compatibility-group",
            required=True,
            help="exact provider/model compatibility group",
        )

    context_plan = context_commands.add_parser(
        "plan", help="assess compaction pressure against an existing bound stream"
    )
    _context_scope_arguments(context_plan)
    context_plan.add_argument("--current-tokens", type=int, required=True)
    context_plan.add_argument("--predicted-next-turn-tokens", type=int, default=0)
    context_plan.add_argument("--soft-limit-tokens", type=int, required=True)
    context_plan.add_argument("--hard-limit-tokens", type=int, required=True)
    context_plan.add_argument("--reserved-future-tokens", type=int, required=True)

    context_prepare = context_commands.add_parser("prepare", help="prepare a content-free, tenant-owned CAS checkpoint")
    _context_scope_arguments(context_prepare)
    context_prepare.add_argument("--input", type=Path, required=True)
    context_prepare.add_argument("--expected-sequence", type=int, required=True)
    context_prepare.add_argument("--idempotency-key", required=True)

    context_status = context_commands.add_parser(
        "status", help="inspect ledger/checkpoint status without creating state"
    )
    _context_scope_arguments(context_status)
    context_status.add_argument("--checkpoint-id")

    context_adopt = context_commands.add_parser(
        "adopt", help="adopt a pre-warmed checkpoint after Ed25519 evidence verification"
    )
    _context_scope_arguments(context_adopt)
    context_adopt.add_argument("checkpoint_id")
    context_adopt.add_argument(
        "--expected-active-checkpoint-id",
        required=True,
        help="exact predecessor checkpoint id, or NONE for the initial adoption",
    )
    context_adopt.add_argument("--trust-store", type=Path, required=True)
    context_adopt.add_argument("--idempotency-key", required=True)

    context_rollback = context_commands.add_parser(
        "rollback", help="restore the independently verified predecessor checkpoint"
    )
    _context_scope_arguments(context_rollback)
    context_rollback.add_argument("checkpoint_id")
    context_rollback.add_argument("--trust-store", type=Path, required=True)
    context_rollback.add_argument("--idempotency-key", required=True)

    doctor = subparsers.add_parser("doctor", help="diagnostics").add_subparsers(dest="command", required=True)
    doctor.add_parser("cache", help="check local cache health")
    return parser


def _context(args: argparse.Namespace) -> Context:
    config = load_config(args.config) if args.config else default_config()
    base = Path(args.base)
    paths = config.resolved(base)
    store = open_store(paths.metadata)
    try:
        cas = ContentAddressableStore(
            paths.cache_root,
            compression=config.local.compression,
            max_bytes=config.local.max_size_gb * 1024**3,
        )
        return Context(config, base, args.tenant or "default", args.project, store, cas)
    except BaseException:
        store.close()
        raise


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("input must be a readable JSON object", path=str(path)) from exc
    if not isinstance(loaded, dict):
        raise ContractViolation("input JSON must be an object", path=str(path))
    return loaded


def _digest_mapping(value: Any, field_name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not all(
        isinstance(name, str) and isinstance(digest, str) for name, digest in value.items()
    ):
        raise ContractViolation(f"{field_name} must be an object of named digests")
    return tuple((name, require_digest(digest)) for name, digest in value.items())


def _digest_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractViolation(f"{field_name} must be an array of digests")
    return tuple(require_digest(item) for item in value)


def _environment_key_inputs(payload: dict[str, Any]) -> EnvironmentKeyInputs:
    expected = {
        "schema_version",
        "base_image_digest",
        "setup_script_digests",
        "maintenance_script_digests",
        "lockfile_digests",
        "package_manager_digest",
        "toolchain_digests",
        "platform",
        "approved_environment_digests",
        "secret_reference_versions",
    }
    if set(payload) != expected:
        raise ContractViolation(
            "environment key input has an invalid digest-only closed shape",
            missing=sorted(expected - set(payload)),
            unknown=sorted(set(payload) - expected),
        )
    platform = payload["platform"]
    if not isinstance(platform, dict) or set(platform) != {
        "operating_system",
        "architecture",
        "libc",
        "runtime_digest",
    }:
        raise ContractViolation("environment platform identity has an invalid closed shape")
    if not all(isinstance(platform[name], str) for name in platform):
        raise ContractViolation("environment platform identity fields must be strings")
    secrets = payload["secret_reference_versions"]
    if not isinstance(secrets, list):
        raise ContractViolation("secret_reference_versions must be digest pairs")
    secret_pairs: list[tuple[str, str]] = []
    for pair in secrets:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) for item in pair):
            raise ContractViolation("secret_reference_versions must be digest pairs")
        secret_pairs.append((require_digest(pair[0]), require_digest(pair[1])))
    for scalar in ("schema_version", "base_image_digest", "package_manager_digest"):
        if not isinstance(payload[scalar], str):
            raise ContractViolation(f"{scalar} must be a string")
    return EnvironmentKeyInputs(
        base_image_digest=require_digest(payload["base_image_digest"]),
        setup_script_digests=_digest_list(payload["setup_script_digests"], "setup_script_digests"),
        maintenance_script_digests=_digest_list(payload["maintenance_script_digests"], "maintenance_script_digests"),
        lockfile_digests=_digest_mapping(payload["lockfile_digests"], "lockfile_digests"),
        package_manager_digest=require_digest(payload["package_manager_digest"]),
        toolchain_digests=_digest_mapping(payload["toolchain_digests"], "toolchain_digests"),
        platform=PlatformIdentity(
            platform["operating_system"],
            platform["architecture"],
            platform["libc"],
            platform["runtime_digest"],
        ),
        approved_environment_digests=_digest_mapping(
            payload["approved_environment_digests"],
            "approved_environment_digests",
        ),
        secret_reference_versions=tuple(secret_pairs),
        schema_version=payload["schema_version"],
    )


def _environment_layer_payloads(
    context: Context,
    specifications: Sequence[str],
) -> tuple[EnvironmentLayerPayload, ...]:
    scanner = SecretScanner(max_bytes=MAX_SCAN_BYTES)
    layers: list[EnvironmentLayerPayload] = []
    observed: set[EnvironmentLayerType] = set()
    for specification in specifications:
        if not isinstance(specification, str) or "=" not in specification:
            raise ContractViolation("--layer must use TYPE=relative/path form")
        raw_type, raw_path = specification.split("=", 1)
        try:
            layer_type = EnvironmentLayerType(raw_type)
        except ValueError as exc:
            raise ContractViolation("environment layer type is unsupported", layer_type=raw_type) from exc
        if layer_type in observed:
            raise ContractViolation("environment layer type is duplicated", layer_type=raw_type)
        relative = normalize_logical_path(raw_path)
        target = resolve_within(context.base, relative)
        try:
            descriptor = open_no_follow(target, os.O_RDONLY)
        except OSError as exc:
            raise ContractViolation("environment layer is not a readable local file", path=relative) from exc
        try:
            information = os.fstat(descriptor)
            if not stat.S_ISREG(information.st_mode):
                raise ContractViolation("environment layer must be a regular file", path=relative)
            if information.st_size <= 0 or information.st_size > MAX_SCAN_BYTES:
                raise ContractViolation(
                    "CLI environment layers must be non-empty and at most the full-scan limit",
                    path=relative,
                    max_bytes=MAX_SCAN_BYTES,
                )
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = -1
                content = handle.read(MAX_SCAN_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if len(content) != information.st_size:
            raise ContractViolation("environment layer changed while being read", path=relative)
        findings = scanner.scan_text(content.decode("utf-8", errors="ignore"), relative)
        if findings:
            raise SecretDetected(
                "environment layer failed the complete secret-pattern scan",
                path=relative,
                finding_digests=[finding.excerpt_digest for finding in findings],
            )
        layers.append(EnvironmentLayerPayload(layer_type, content))
        observed.add(layer_type)
    return tuple(layers)


def _require_project(context: Context) -> str:
    if not context.project_id:
        raise ContractViolation("this command requires an explicit --project scope")
    return context.project_id


def _assert_payload_scope(context: Context, payload: dict[str, Any]) -> str:
    project = payload.get("project_id")
    if not isinstance(project, str) or not project:
        raise ContractViolation("input requires project_id")
    if context.project_id is not None and project != context.project_id:
        raise ContractViolation(
            "input project_id does not match --project scope",
            expected=context.project_id,
            actual=project,
        )
    return project


def _source_linked_item(value: Any, field_name: str) -> SourceLinkedItem:
    if not isinstance(value, dict) or set(value) != {
        "statement",
        "source_event_ids",
        "artifact_refs",
        "freshness",
    }:
        raise ContractViolation(f"{field_name} item has an invalid closed shape")
    statement = value["statement"]
    event_ids = value["source_event_ids"]
    artifact_refs = value["artifact_refs"]
    freshness = value["freshness"]
    if not isinstance(statement, str):
        raise ContractViolation(f"{field_name} statement must be text")
    if not isinstance(event_ids, list) or not all(isinstance(item, str) for item in event_ids):
        raise ContractViolation(f"{field_name} source_event_ids must be strings")
    if not isinstance(artifact_refs, list) or not all(isinstance(item, str) for item in artifact_refs):
        raise ContractViolation(f"{field_name} artifact_refs must be digests")
    if not isinstance(freshness, str):
        raise ContractViolation(f"{field_name} freshness must be text")
    return SourceLinkedItem(
        statement,
        source_event_ids=tuple(event_ids),
        artifact_refs=tuple(artifact_refs),
        freshness=freshness,
    )


def _context_checkpoint_sections(payload: dict[str, Any]) -> ContextCheckpointSections:
    expected = {
        "task_contract",
        "repository_state",
        "decisions",
        "unresolved",
        "approvals",
        "dag_state",
        "staged_state",
        "build_test_state",
        "evidence_refs",
        "pending_side_effects",
        "safety_constraints",
    }
    if set(payload) != expected:
        raise ContractViolation(
            "context checkpoint input has an invalid closed shape",
            missing=sorted(expected - set(payload)),
            unknown=sorted(set(payload) - expected),
        )
    mapping_fields = (
        "task_contract",
        "repository_state",
        "dag_state",
        "staged_state",
        "build_test_state",
    )
    for field_name in mapping_fields:
        if not isinstance(payload[field_name], dict):
            raise ContractViolation(f"{field_name} must be an object")
    linked_fields = (
        "decisions",
        "unresolved",
        "approvals",
        "pending_side_effects",
        "safety_constraints",
    )
    linked: dict[str, tuple[SourceLinkedItem, ...]] = {}
    for field_name in linked_fields:
        items = payload[field_name]
        if not isinstance(items, list):
            raise ContractViolation(f"{field_name} must be an array")
        linked[field_name] = tuple(_source_linked_item(item, field_name) for item in items)
    evidence_refs = payload["evidence_refs"]
    if not isinstance(evidence_refs, list) or not all(isinstance(item, str) for item in evidence_refs):
        raise ContractViolation("evidence_refs must be an array of digests")
    return ContextCheckpointSections(
        task_contract=dict(payload["task_contract"]),
        repository_state=dict(payload["repository_state"]),
        decisions=linked["decisions"],
        unresolved=linked["unresolved"],
        approvals=linked["approvals"],
        dag_state=dict(payload["dag_state"]),
        staged_state=dict(payload["staged_state"]),
        build_test_state=dict(payload["build_test_state"]),
        evidence_refs=tuple(evidence_refs),
        pending_side_effects=linked["pending_side_effects"],
        safety_constraints=linked["safety_constraints"],
    )


def _context_trust_verifier(
    path: Path,
) -> tuple[Ed25519ContextWarmTrustVerifier, str]:
    target = Path(path)
    try:
        descriptor = open_no_follow(target, os.O_RDONLY)
    except OSError as exc:
        raise ContractViolation("context trust store is not readable", path=str(target)) from exc
    try:
        information = os.fstat(descriptor)
        if not stat.S_ISREG(information.st_mode) or information.st_size < 2 or information.st_size > 64 * 1024:
            raise ContractViolation("context trust store must be a bounded regular file")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            raw = handle.read(64 * 1024 + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) != information.st_size:
        raise ContractViolation("context trust store changed while being read")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractViolation("context trust store is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ContractViolation("context trust store must be a JSON object")
    if set(payload) != {"schema_version", "keys", "revoked_key_ids"}:
        raise ContractViolation("context trust store has an invalid closed shape")
    if payload["schema_version"] != "1.2.0":
        raise ContractViolation("context trust store version is unsupported")
    keys = payload["keys"]
    revoked = payload["revoked_key_ids"]
    if not isinstance(keys, list) or not keys:
        raise ContractViolation("context trust store requires at least one public key")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        raise ContractViolation("context revoked key ids must be strings")
    public_keys: dict[str, bytes] = {}
    identities: dict[str, str] = {}
    for item in keys:
        if not isinstance(item, dict) or set(item) != {
            "key_id",
            "verifier_identity",
            "public_key_hex",
        }:
            raise ContractViolation("context trust key has an invalid closed shape")
        key_id = item["key_id"]
        identity = item["verifier_identity"]
        encoded = item["public_key_hex"]
        if not all(isinstance(value, str) and value for value in (key_id, identity, encoded)):
            raise ContractViolation("context trust key fields must be non-empty strings")
        if key_id in public_keys:
            raise ContractViolation("context trust key id is duplicated", key_id=key_id)
        try:
            material = bytes.fromhex(encoded)
        except ValueError as exc:
            raise ContractViolation("context Ed25519 public key is not hex", key_id=key_id) from exc
        if len(material) != 32:
            raise ContractViolation("context Ed25519 public key must contain 32 bytes", key_id=key_id)
        public_keys[key_id] = material
        identities[key_id] = identity
    if len(set(revoked)) != len(revoked):
        raise ContractViolation("context revoked key ids contain duplicates")
    return (
        Ed25519ContextWarmTrustVerifier(
            Ed25519ProvenanceSigner.verifier(public_keys),
            identities,
            revoked_key_ids=frozenset(revoked),
        ),
        digest_of(payload),
    )


def _context_compaction_service(
    context: Context,
    args: argparse.Namespace,
    *,
    policy: CompactionPolicy | None = None,
    trust_verifier: Ed25519ContextWarmTrustVerifier | None = None,
    require_enabled: bool = False,
) -> ContextCompactionService:
    if args.tenant is None or not context.project_id:
        raise ContractViolation("context commands require explicit --tenant and --project scope")
    configured = context.config.parity.context_ledger
    if require_enabled and (not configured.enabled or not configured.compaction_enabled):
        raise ContractViolation("context compaction is disabled by configuration")
    ledger = RepositoryContextLedger(
        context.store,
        context.tenant_id,
        context.project_id,
        args.stream,
        args.branch_lineage,
        require_digest(args.snapshot if args.snapshot.startswith("sha256:") else f"sha256:{args.snapshot}"),
        create_if_missing=False,
    )
    return ContextCompactionService(
        ledger,
        policy or CompactionPolicy(soft_limit_tokens=1, hard_limit_tokens=2, reserved_future_tokens=0),
        cas=context.cas,
        ownership=context.store,
        warm_trust_verifier=trust_verifier,
    )


def _checkpoint_summary(checkpoint: ContextCheckpoint) -> dict[str, Any]:
    return {
        "checkpoint_id": checkpoint.checkpoint_id,
        "checkpoint_digest": checkpoint.checkpoint_digest,
        "ledger_sequence": checkpoint.ledger_sequence,
        "ledger_head_digest": checkpoint.ledger_head_digest,
        "repository_snapshot_digest": checkpoint.repository_snapshot_digest,
        "compatibility_group": checkpoint.compatibility_group,
        "source_sequence_range": [
            checkpoint.source_sequence_start,
            checkpoint.source_sequence_end,
        ],
        "status": str(checkpoint.status),
        "previous_checkpoint_id": checkpoint.previous_checkpoint_id,
        "warm_evidence_digest": checkpoint.warm_evidence_digest,
        "external_artifact_refs": list(checkpoint.external_artifact_refs),
        "retained_sections": sorted(checkpoint.sections),
        "created_at": checkpoint.created_at,
        "warmed_at": checkpoint.warmed_at,
        "adopted_at": checkpoint.adopted_at,
        "rolled_back_at": checkpoint.rolled_back_at,
        "content_policy": "typed_metadata_and_digests_only",
    }


def _persist_idempotent(
    context: Context,
    args: argparse.Namespace,
    operation: str,
    project_id: str,
    document: dict[str, Any],
    write: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    key = getattr(args, "idempotency_key", None)
    if not isinstance(key, str) or not key:
        raise ContractViolation("--persist requires --idempotency-key")
    if context.project_id is None or context.project_id != project_id:
        raise ContractViolation(
            "persistent parity commands require an exact explicit --project scope",
            project_id=project_id,
        )
    # Never store a raw compilation/benchmark input in the idempotency table.
    # The immutable, content-free document digest is sufficient to distinguish
    # exact replay from key reuse with drift.
    request = {
        "project_id": project_id,
        "document_digest": digest_of(document),
    }
    return _execute_idempotent(context, key, operation, request, write)


def _execute_idempotent(
    context: Context,
    key: str,
    operation: str,
    semantic_request: dict[str, Any],
    write: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Claim durably before a CLI side effect and publish a fenced response."""

    if not key:
        raise ContractViolation("mutating command requires --idempotency-key")
    request = {
        "scope_digest": digest_of(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
            }
        ),
        "semantic_request_digest": digest_of(semantic_request),
    }
    with context.store.transaction():
        claim = context.store.claim_idempotent(
            context.tenant_id,
            key,
            operation,
            request,
        )
    if claim.replayed:
        if not isinstance(claim.response, dict):
            raise ContractViolation("stored CLI idempotency response is not an object")
        return claim.response
    response = write()
    assert claim.owner_token is not None
    with context.store.transaction():
        remembered = context.store.complete_idempotent(
            context.tenant_id,
            key,
            operation,
            request,
            claim.owner_token,
            claim.fence,
            response,
        )
    if not isinstance(remembered, dict):
        raise ContractViolation("stored CLI idempotency response is not an object")
    return remembered


# --------------------------------------------------------------------------
# cache commands
# --------------------------------------------------------------------------
def cmd_cache_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "tenant_id": context.tenant_id,
        "cas": context.cas.accounting(),
        "action_cache": context.action_cache.statistics(context.tenant_id),
        "runs": {str(status): len(context.store.list_runs(context.tenant_id, [status])) for status in RunStatus},
        "config": {
            "mode": str(context.config.mode),
            "root": str(context.config.resolved(context.base).cache_root),
            "remote_enabled": context.config.remote.enabled,
        },
    }


def cmd_cache_inspect(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    action_key = require_digest(
        args.action_key if args.action_key.startswith("sha256:") else f"sha256:{args.action_key}"
    )
    found: list[dict[str, Any]] = []
    for namespace in TrustNamespace:
        entry = context.store.get_action_entry(context.tenant_id, namespace, action_key)
        if entry is None:
            continue
        result: dict[str, Any] = {
            "trust_namespace": str(namespace),
            "result_manifest_digest": entry.result_manifest_digest,
            "validation_level": str(entry.validation_level),
            "status": str(entry.status),
            "entry_kind": entry.entry_kind,
            "hit_count": entry.hit_count,
            "producer_identity": entry.producer_identity,
            "quarantine_reason": entry.quarantine_reason,
        }
        if context.cas.contains(entry.result_manifest_digest):
            result["result"] = context.cas.get_document(entry.result_manifest_digest)
        found.append(result)
    if not found:
        raise NotFound("no cache entry for this ActionKey", action_key=action_key)
    return {"action_key": action_key, "entries": found}


def cmd_cache_explain_miss(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    context.owned_run(args.run_id)
    events = [event for event in context.store.list_events(args.run_id) if event["node_id"] == args.node_id]
    attempts = context.store.latest_attempt(args.run_id, args.node_id)
    node = context.store.get_node(args.run_id, args.node_id, attempts) if attempts else None
    miss_events = [event for event in events if "miss" in event["event_type"].lower()]
    return {
        "run_id": args.run_id,
        "node_id": args.node_id,
        "action_key": node.action_key if node else None,
        "status": str(node.status) if node else None,
        "miss_events": miss_events,
        "journal_events": len(events),
        "hint": (
            "no recorded miss reasons; re-run with the planner attached to record fingerprint dimension comparisons"
            if not miss_events
            else ""
        ),
    }


def cmd_cache_explain(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    outcomes = ParityMetadataRepository(context.store).list_cache_outcomes(
        context.tenant_id,
        project_id,
        args.request_id,
    )
    if not outcomes:
        raise NotFound(
            "no v1.2 cache outcomes for this request",
            request_id=args.request_id,
            project_id=project_id,
        )
    reasons: dict[str, int] = {}
    for event in outcomes:
        reason = str(event["reason_code"])
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "schema_version": "1.2.0",
        "tenant_id": context.tenant_id,
        "project_id": project_id,
        "request_id": args.request_id,
        "outcomes": list(outcomes),
        "reason_counts": dict(sorted(reasons.items())),
        "content_policy": "digests_and_closed_taxonomy_only",
    }


def cmd_cache_verify(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    digests = list(context.cas.iter_digests())
    if args.deep:
        outcome = context.cas.scrub(digests)
    else:
        outcome = {
            "healthy": [digest for digest in digests if context.cas.contains(digest)],
            "corrupt": [digest for digest in digests if context.cas.is_quarantined(digest)],
        }
    collector = context.collector()
    return {
        "checked": len(digests),
        "healthy": len(outcome["healthy"]),
        "corrupt": outcome["corrupt"],
        "orphans": collector.reconcile_orphans(),
    }


def cmd_cache_pin(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    expires = context.clock.now() + args.expires_in_hours * 3600.0 if args.expires_in_hours else None
    with context.store.transaction():
        pin_id = context.store.add_pin(context.tenant_id, args.kind, args.subject, args.reason, expires)
    return {"pin_id": pin_id, "kind": args.kind, "subject": args.subject, "expires_at": expires}


def cmd_cache_unpin(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    with context.store.transaction():
        removed = context.store.remove_pin(args.pin_id)
    return {"pin_id": args.pin_id, "removed": removed}


def cmd_cache_gc(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    collector = context.collector()
    if args.apply_plan:
        if not args.idempotency_key:
            raise ContractViolation("--apply requires --idempotency-key")

        def write() -> dict[str, Any]:
            with context.store.transaction():
                collector.approve(args.apply_plan)
                outcome = collector.apply(args.apply_plan)
            return {"applied": True, **outcome}

        return _execute_idempotent(
            context,
            args.idempotency_key,
            "CLI cache gc apply",
            {"plan_id": args.apply_plan},
            write,
        )
    with context.store.transaction():
        plan = collector.plan()
    return {
        "dry_run": True,
        "plan_id": plan.plan_id,
        "candidates": len(plan.candidates),
        "reclaimable_bytes": plan.reclaimable_bytes,
        "protected": len(plan.protected),
        "top_candidates": [candidate.to_dict() for candidate in plan.candidates[:10]],
        "next": f"elmos cache gc --apply {plan.plan_id} --idempotency-key <key>",
    }


def cmd_cache_explain_retention(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    digest = require_digest(args.digest if args.digest.startswith("sha256:") else f"sha256:{args.digest}")
    return explain_retention(context.collector(), digest)


# --------------------------------------------------------------------------
# workspace commands
# --------------------------------------------------------------------------
def cmd_workspace_list(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    runs = context.store.list_runs(context.tenant_id)
    if context.project_id is not None:
        runs = [run for run in runs if run.project_id == context.project_id]
    root = context.base / context.config.workspace.root
    return {
        "workspace_root": str(root),
        "runs": [
            {
                "run_id": run.run_id,
                "project_id": run.project_id,
                "status": str(run.status),
                "staged_files": len(context.store.list_staged_files(run.run_id)),
                "published_tree": run.published_tree_digest,
            }
            for run in runs
        ],
    }


def cmd_workspace_inspect(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    workspace = context.workspace(args.run_id)
    summary = workspace.summary()
    summary["recovery_plan"] = [action.to_dict() for action in workspace.plan_recovery()]
    return summary


def cmd_workspace_recover(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    workspace = context.workspace(args.run_id)
    if args.plan_only:
        return {"run_id": args.run_id, "plan": [a.to_dict() for a in workspace.plan_recovery()]}
    with context.store.transaction():
        summary = workspace.recover()
    return {"run_id": args.run_id, "recovery": summary}


def cmd_workspace_quarantine(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    record = context.owned_staged_file(args.run_id, args.staged_file_id)
    workspace = context.workspace(args.run_id)
    with context.store.transaction():
        updated = workspace.quarantine(record, args.reason)
    return {
        "staged_file_id": updated.staged_file_id,
        "logical_path": updated.logical_path,
        "status": str(updated.status),
        "reason": updated.quarantine_reason,
    }


# --------------------------------------------------------------------------
# run commands
# --------------------------------------------------------------------------
def cmd_run_resume(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    # Authorization must precede the durable idempotency claim so a denied
    # cross-scope global id leaves no metadata, journal or filesystem trace.
    context.owned_run(args.run_id)

    def write() -> dict[str, Any]:
        workspace = context.workspace(args.run_id)
        coordinator = context.coordinator(args.run_id)
        with context.store.transaction():
            recovery = workspace.recover()
            expired = coordinator.recover_expired()
            run = context.owned_run(args.run_id)
            if run.status is not RunStatus.RUNNING:
                context.store.transition_run(args.run_id, RunStatus.RUNNING, run.version)
        return {"run_id": args.run_id, "recovery": recovery, "reclaimed_nodes": expired}

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI run resume",
        {"run_id": args.run_id},
        write,
    )


def cmd_run_pause(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    context.owned_run(args.run_id)

    def write() -> dict[str, Any]:
        run = context.owned_run(args.run_id)
        if run.version != args.expected_version:
            raise ElmosCacheError(f"run version conflict: expected {args.expected_version}, found {run.version}")
        with context.store.transaction():
            context.coordinator(args.run_id).pause_run(args.run_id)
        return {"run_id": args.run_id, "status": str(context.owned_run(args.run_id).status)}

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI run pause",
        {"run_id": args.run_id, "expected_version": args.expected_version},
        write,
    )


def cmd_run_cancel(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    context.owned_run(args.run_id)

    def write() -> dict[str, Any]:
        run = context.owned_run(args.run_id)
        if run.version != args.expected_version:
            raise ElmosCacheError(f"run version conflict: expected {args.expected_version}, found {run.version}")
        with context.store.transaction():
            context.coordinator(args.run_id).cancel_run(args.run_id, args.reason)
        staged = context.store.list_staged_files(args.run_id)
        return {
            "run_id": args.run_id,
            "status": str(context.owned_run(args.run_id).status),
            "evidence_preserved": {
                "staged_files": len(staged),
                "sealed": len(
                    [
                        record
                        for record in staged
                        if record.status
                        in (
                            StagedFileStatus.SEALED,
                            StagedFileStatus.CAS_PROMOTED,
                            StagedFileStatus.TREE_INCLUDED,
                            StagedFileStatus.PUBLISHED,
                        )
                    ]
                ),
                "checkpoints": len(context.store.list_checkpoints(args.run_id)),
                "journal_events": len(context.store.list_events(args.run_id)),
            },
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI run cancel",
        {
            "run_id": args.run_id,
            "expected_version": args.expected_version,
            "reason_digest": digest_of(args.reason),
        },
        write,
    )


# --------------------------------------------------------------------------
# artifact and doctor
# --------------------------------------------------------------------------
def cmd_artifact_materialize(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    digest = require_digest(args.digest if args.digest.startswith("sha256:") else f"sha256:{args.digest}")
    destination = context.cas.materialize(digest, Path(args.destination), verify=True)
    return {"digest": digest, "destination": str(destination), "size": destination.stat().st_size}


def cmd_doctor_cache(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    paths = context.config.resolved(context.base)
    check("cache-root-writable", paths.cache_root.exists(), str(paths.cache_root))
    check("metadata-present", paths.metadata.exists(), str(paths.metadata))

    accounting = context.cas.accounting()
    check(
        "no-quarantined-objects",
        accounting["quarantined_count"] == 0,
        f"{accounting['quarantined_count']} quarantined objects",
    )

    collector = context.collector()
    orphans = collector.reconcile_orphans()
    check(
        "no-orphan-metadata",
        not orphans["orphan_metadata"],
        f"{len(orphans['orphan_metadata'])} metadata rows without bytes",
    )
    check(
        "no-orphan-blobs",
        not orphans["orphan_blobs"],
        f"{len(orphans['orphan_blobs'])} blobs without metadata",
    )

    stuck = [
        run.run_id for run in context.store.list_runs(context.tenant_id, [RunStatus.RUNNING, RunStatus.RECOVERING])
    ]
    check("no-stuck-runs", not stuck, f"runs still marked running: {stuck[:5]}")

    quarantined_entries = [
        entry.action_key
        for entry in context.store.list_action_entries(context.tenant_id)
        if str(entry.status) == "QUARANTINED"
    ]
    check(
        "no-nondeterministic-stages",
        not quarantined_entries,
        f"{len(quarantined_entries)} quarantined cache entries",
    )

    if context.config.redis.enabled and context.config.redis.authoritative:
        check("redis-not-authoritative", False, "Redis is configured as authoritative truth")
    else:
        check("redis-not-authoritative", True, "Redis is advisory only")

    return {
        "healthy": all(item["passed"] for item in checks),
        "checks": checks,
        "accounting": accounting,
    }


# --------------------------------------------------------------------------
# policy and trace commands
#
# These read a trace and produce a report; none of them mutate the cache. The
# operator surface for a policy change is deliberately "show me the evidence",
# not "switch it now": a policy is promoted by editing the ``policy`` section
# of the configuration after a certificate exists, not by a CLI flag.
# --------------------------------------------------------------------------
def _load_corpus(args: argparse.Namespace) -> TraceCorpus:
    if getattr(args, "trace", None):
        corpus = TraceCorpus.read_jsonl(args.trace, label=args.trace.stem)
    else:
        corpus = GENERATORS[args.workload]()
    split = getattr(args, "split", None)
    if split:
        events = corpus.split(Split(split))
        if not events:
            raise NotFound(f"split {split} is empty", split=split)
        corpus = TraceCorpus(events, label=f"{corpus.label}:{split}")
    return corpus


def _objective(context: Context, args: argparse.Namespace) -> str:
    requested = getattr(args, "objective", None) or context.config.policy.objective_profile
    return ObjectiveProfile(requested).value


def _capacity(corpus: TraceCorpus, args: argparse.Namespace) -> int:
    explicit = getattr(args, "capacity_bytes", None)
    if explicit:
        return int(explicit)
    return recommended_capacity(corpus.events, getattr(args, "capacity_fraction", 0.2) or 0.2)


def cmd_policy_show(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    policy = context.config.policy
    return {
        "enabled": policy.enabled,
        "tiers": {"L0": policy.l0_policy, "L1": policy.l1_policy, "L2": policy.l2_policy},
        "fallback": policy.fallback,
        "objective_profile": policy.objective_profile,
        "adaptive_selection": policy.adaptive_selection,
        "learned_tuning": policy.learned_tuning,
        "learned_shadow_only": policy.learned_shadow_only,
        "admission_enabled": policy.admission_enabled,
        "trace_capture": policy.trace_capture,
        "prefetch_enabled": policy.prefetch_enabled,
        "available_policies": [name.value for name in PolicyName],
        "capabilities": PolicyPlane.from_config(policy, tenant_id=context.tenant_id).report()["capabilities"],
        "configuration_digest": configuration_digest(
            policy.l1_policy, context.config.local.max_size_gb * 1024**3, policy.objective_profile, {}
        ),
    }


def cmd_policy_benchmark(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    corpus = _load_corpus(args)
    candidates = tuple(args.candidates) if args.candidates else tuple(n.value for n in PolicyName)
    return benchmark(
        corpus,
        policies=candidates,
        capacity_bytes=_capacity(corpus, args),
        baseline=args.baseline,
        objective=_objective(context, args),
    )


def cmd_policy_matrix(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    fractions = tuple(args.fractions) if args.fractions else (0.05, 0.2, 0.5)
    return benchmark_matrix(capacity_fractions=fractions, objective=_objective(context, args))


def cmd_policy_select(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    corpus = _load_corpus(args)
    features = workload_features(corpus.events)
    selection = RuleSelector().select(features)
    payload = selection.to_dict()
    payload["features"] = features
    payload["configured"] = context.config.policy.l1_policy
    payload["agrees_with_configuration"] = selection.policy == context.config.policy.l1_policy
    return payload


def cmd_policy_certify(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    corpus = _load_corpus(args)
    if args.signing_key:
        seed = bytes.fromhex(args.signing_key.read_text(encoding="utf-8").strip())
        signer = Ed25519ProvenanceSigner({"elmos-policy-1": seed}, "elmos-policy-1")
        ephemeral = False
    else:
        signer = Ed25519ProvenanceSigner.generate("elmos-policy-ephemeral")
        ephemeral = True
    objective = _objective(context, args)
    capacity = _capacity(corpus, args)
    plan = RolloutPlan()

    def _evidence(path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ContractViolation("rollout evidence must be a JSON object", path=str(path))
        return loaded

    result = certify_policy(
        corpus,
        args.candidate,
        CertificationContext(
            elmos_commit=args.elmos_commit,
            policy_digest=configuration_digest(args.candidate, capacity, objective, {}),
            configuration_digest=configuration_digest(args.candidate, capacity, objective, {}),
            capacity_bytes=capacity,
            objective_profile=objective,
            protected_root_rules="active-runs,checkpoints,published,pins,legal-holds",
            hardware_profile=args.hardware_profile,
        ),
        signer,
        objective=objective,
        rollout=plan,
        shadow_evidence=_evidence(args.shadow_evidence),
        canary_evidence=_evidence(args.canary_evidence),
        rollback_evidence=_evidence(args.rollback_evidence),
        issued_at=args.issued_at,
    )
    payload = result.to_dict()
    payload["ephemeral_signing_key"] = ephemeral
    if ephemeral:
        payload["warning"] = (
            "signed with an ephemeral key; supply --signing-key for a certificate anyone else can verify"
        )
    return payload


def cmd_trace_generate(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    corpus = GENERATORS[args.workload]()
    path = corpus.write_jsonl(args.out)
    return {"workload": args.workload, "path": str(path), "manifest": corpus.manifest()}


def cmd_trace_verify(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    corpus = TraceCorpus.read_jsonl(args.trace, label=args.trace.stem)
    assert_privacy(corpus.events)
    leakage = [finding.to_dict() for finding in detect_leakage(corpus)]
    train = corpus.split(Split.TRAIN) if Split.TRAIN.value in corpus.splits else ()
    test = corpus.split(Split.TEST) if Split.TEST.value in corpus.splits else ()
    sufficient, detail = sufficient_sample(test or corpus.events)
    return {
        "path": str(args.trace),
        "manifest": corpus.manifest(),
        "privacy_clean": True,
        "leakage": leakage,
        "drift": detect_drift(train, test) if train and test else None,
        "sample_sufficient": sufficient,
        "sample_detail": detail,
        "usable_for_certification": sufficient and not leakage,
    }


def cmd_trace_workloads(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "workloads": [
            {"name": name, "features": workload_features(generator().events)}
            for name, generator in sorted(GENERATORS.items())
        ]
    }


# --------------------------------------------------------------------------
# v1.2 prompt, environment, affinity and parity commands
# --------------------------------------------------------------------------
def cmd_prompt_compile(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_json_object(args.input)
    project_id = _assert_payload_scope(context, payload)
    compilation = compile_prompt_prefix_payload(context.tenant_id, payload)
    response = {**compilation.response, "persisted": False}
    if not args.persist:
        return response

    repository = ParityMetadataRepository(context.store)

    def write() -> dict[str, Any]:
        stored = repository.put_prompt_manifest(
            context.tenant_id,
            project_id,
            str(compilation.manifest["manifest_id"]),
            compilation.manifest,
        )
        return {
            **compilation.response,
            "persisted": True,
            "persisted_manifest_digest": digest_of(stored),
        }

    return _persist_idempotent(
        context,
        args,
        "CLI prompt compile",
        project_id,
        compilation.manifest,
        write,
    )


def cmd_prompt_diff(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    previous_payload = _load_json_object(args.previous)
    current_payload = _load_json_object(args.current)
    previous_project = _assert_payload_scope(context, previous_payload)
    current_project = _assert_payload_scope(context, current_payload)
    if previous_project != current_project:
        raise ContractViolation("prefix diff inputs must use the same project scope")
    previous = compile_prompt_prefix_payload(context.tenant_id, previous_payload)
    current = compile_prompt_prefix_payload(context.tenant_id, current_payload)
    difference = first_prefix_difference(previous.compiled, current.compiled)
    return {
        "schema_version": "1.2.0",
        "project_id": previous_project,
        "changed": difference is not None,
        "first_difference": None if difference is None else difference.to_dict(),
        "previous_manifest_id": previous.manifest["manifest_id"],
        "current_manifest_id": current.manifest["manifest_id"],
        "content_policy": "no_prompt_bytes",
    }


def cmd_environment_inspect(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    snapshot_key = require_digest(
        args.snapshot_key if args.snapshot_key.startswith("sha256:") else f"sha256:{args.snapshot_key}"
    )
    inspection = EnvironmentSnapshotService(
        context.store,
        context.cas,
        clock=context.clock,
    ).inspect(
        context.tenant_id,
        project_id,
        args.trust_namespace,
        snapshot_key,
        RestoreEstimate(
            transfer_ms=args.transfer_ms,
            decompression_ms=args.decompression_ms,
            verification_ms=args.verification_ms,
            rebuild_ms=args.rebuild_ms,
            minimum_savings_ms=args.minimum_savings_ms,
            maximum_restore_ratio=args.maximum_restore_ratio,
        ),
    )
    return {
        "schema_version": "1.2.0",
        "tenant_id": context.tenant_id,
        "project_id": project_id,
        "trust_namespace": args.trust_namespace,
        "snapshot_key": inspection.snapshot_key,
        "manifest": dict(inspection.manifest),
        "manifest_digest": inspection.manifest_digest,
        "effective_status": "AVAILABLE",
        "layer_refs": [ref.manifest_entry() for ref in inspection.layer_refs],
        "verified_layer_digests": list(inspection.verified_layer_digests),
        "decision": inspection.decision.to_dict(),
    }


def cmd_environment_seal(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    inputs = _environment_key_inputs(_load_json_object(args.input))
    layers = _environment_layer_payloads(context, args.layer)
    key = build_environment_snapshot_key(inputs)
    owner = context.store.query_one(
        "SELECT tenant_id FROM projects WHERE project_id=?",
        (project_id,),
    )
    if owner is not None and str(owner[0]) != context.tenant_id:
        raise NotFound("project does not exist in this scope")

    def write() -> dict[str, Any]:
        sealed = EnvironmentSnapshotService(
            context.store,
            context.cas,
            clock=context.clock,
        ).seal(
            context.tenant_id,
            project_id,
            args.trust_namespace,
            inputs,
            layers,
            expires_at=args.expires_at,
        )
        return {
            "schema_version": "1.2.0",
            "tenant_id": context.tenant_id,
            "project_id": project_id,
            "trust_namespace": args.trust_namespace,
            "snapshot_key": sealed.key.digest,
            "snapshot_id": sealed.snapshot_id,
            "manifest_digest": sealed.manifest_digest,
            "effective_status": sealed.effective_status,
            "layers": [ref.manifest_entry() for ref in sealed.layers],
            "secret_scan": "PASSED_COMPLETE_PATTERN_SCAN",
            "execution": "NONE",
            "certification": "NOT_CERTIFIED",
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI environment seal",
        {
            "project_id": project_id,
            "trust_namespace": args.trust_namespace,
            "environment_key_digest": key.digest,
            "layers": [
                {
                    "layer_type": layer.layer_type.value,
                    "digest": sha256_bytes(layer.content),
                    "size_bytes": len(layer.content),
                }
                for layer in layers
            ],
            "expires_at": args.expires_at,
        },
        write,
    )


def cmd_environment_restore(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    inputs = _environment_key_inputs(_load_json_object(args.input))
    key = build_environment_snapshot_key(inputs)
    state = ParityMetadataRepository(context.store).get_environment_snapshot_state(
        context.tenant_id,
        project_id,
        key.digest,
    )
    if state is None:
        raise NotFound("environment snapshot is not present in this scope")
    relative_output = normalize_logical_path(args.output_dir)
    output_root = resolve_within(context.base, relative_output)
    policy = RestoreCostPolicy(
        rebuild_ms=args.rebuild_ms,
        transfer_bytes_per_ms=args.transfer_bytes_per_ms,
        decompression_bytes_per_ms=args.decompression_bytes_per_ms,
        verification_bytes_per_ms=args.verification_bytes_per_ms,
        minimum_savings_ms=args.minimum_savings_ms,
        maximum_restore_ratio=args.maximum_restore_ratio,
    )

    def write() -> dict[str, Any]:
        result = EnvironmentSnapshotService(
            context.store,
            context.cas,
            clock=context.clock,
        ).restore(
            context.tenant_id,
            project_id,
            args.trust_namespace,
            inputs,
            policy,
        )
        outputs: list[dict[str, Any]] = []
        if result.decision.action is RestoreAction.RESTORE:
            try:
                output_root.mkdir(parents=True, exist_ok=False)
            except FileExistsError as exc:
                raise ConflictError(
                    "environment restore output directory already exists",
                    output_dir=relative_output,
                ) from exc
            for index, layer in enumerate(result.verified_layers):
                name = f"{index:02d}-{layer.ref.layer_type.value.lower()}.layer"
                destination = resolve_within(output_root, name)
                atomic_write_bytes(destination, layer.content, mode=0o600)
                outputs.append(
                    {
                        "layer_type": layer.ref.layer_type.value,
                        "digest": layer.ref.digest,
                        "size_bytes": layer.ref.size_bytes,
                        "path": f"{relative_output}/{name}",
                    }
                )
        return {
            "schema_version": "1.2.0",
            "tenant_id": context.tenant_id,
            "project_id": project_id,
            "trust_namespace": args.trust_namespace,
            "snapshot_key": result.snapshot_key,
            "manifest_digest": result.manifest_digest,
            "decision": result.decision.to_dict(),
            "outputs": outputs,
            "execution": "NONE",
            "certification": "NOT_CERTIFIED",
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI environment restore",
        {
            "project_id": project_id,
            "trust_namespace": args.trust_namespace,
            "environment_key_digest": key.digest,
            "output_directory": relative_output,
            "cost_policy": {
                "rebuild_ms": policy.rebuild_ms,
                "transfer_bytes_per_ms": policy.transfer_bytes_per_ms,
                "decompression_bytes_per_ms": policy.decompression_bytes_per_ms,
                "verification_bytes_per_ms": policy.verification_bytes_per_ms,
                "minimum_savings_ms": policy.minimum_savings_ms,
                "maximum_restore_ratio": policy.maximum_restore_ratio,
            },
        },
        write,
    )


def cmd_context_plan(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    policy = CompactionPolicy(
        soft_limit_tokens=args.soft_limit_tokens,
        hard_limit_tokens=args.hard_limit_tokens,
        reserved_future_tokens=args.reserved_future_tokens,
    )
    service = _context_compaction_service(
        context,
        args,
        policy=policy,
        require_enabled=True,
    )
    service.ledger.validate_chain()
    position = service.ledger.position()
    active = service.active()
    return {
        "schema_version": "1.2.0",
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "stream_id": args.stream,
        "repository_snapshot_digest": service.ledger.repository_snapshot_digest,
        "compatibility_group": args.compatibility_group,
        "ledger_sequence": position.sequence,
        "ledger_head_digest": position.head_event_digest,
        "need": str(policy.assess(args.current_tokens, args.predicted_next_turn_tokens)),
        "current_tokens": args.current_tokens,
        "predicted_next_turn_tokens": args.predicted_next_turn_tokens,
        "limits": {
            "soft_limit_tokens": policy.soft_limit_tokens,
            "hard_limit_tokens": policy.hard_limit_tokens,
            "reserved_future_tokens": policy.reserved_future_tokens,
        },
        "active_checkpoint": None if active is None else _checkpoint_summary(active),
        "active_compatibility_matches": (active is None or active.compatibility_group == args.compatibility_group),
        "side_effects": "NONE",
    }


def cmd_context_prepare(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    sections = _context_checkpoint_sections(_load_json_object(args.input))
    service = _context_compaction_service(context, args, require_enabled=True)
    # All scope, branch/snapshot binding, ledger-chain and typed-section checks
    # happen before the durable CLI idempotency claim.
    service.ledger.validate_chain()
    for artifact_digest in sections.external_artifact_refs():
        service.verify_artifact_reference(artifact_digest)
    position = service.ledger.position()
    if position.sequence != args.expected_sequence:
        raise ConflictError(
            "context changed before checkpoint preparation",
            expected=args.expected_sequence,
            actual=position.sequence,
        )

    def write() -> dict[str, Any]:
        checkpoint = service.prepare(
            sections,
            compatibility_group=args.compatibility_group,
            expected_sequence=args.expected_sequence,
        )
        return {
            "schema_version": "1.2.0",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "stream_id": args.stream,
            "checkpoint": _checkpoint_summary(checkpoint),
            "next": "typed service must independently warm and adopt with Ed25519 evidence",
            "provider_execution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI context prepare",
        {
            "stream_id": args.stream,
            "branch_lineage": args.branch_lineage,
            "repository_snapshot_digest": service.ledger.repository_snapshot_digest,
            "compatibility_group": args.compatibility_group,
            "expected_sequence": args.expected_sequence,
            "sections_digest": digest_of(sections.to_dict()),
        },
        write,
    )


def cmd_context_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    service = _context_compaction_service(context, args)
    service.ledger.validate_chain()
    position = service.ledger.position()
    active = service.active()
    requested = None
    if args.checkpoint_id is not None:
        requested = service.get(args.checkpoint_id)
        if requested.compatibility_group != args.compatibility_group:
            raise ConflictError("checkpoint is bound to another compatibility group")
    return {
        "schema_version": "1.2.0",
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "stream_id": args.stream,
        "repository_snapshot_digest": service.ledger.repository_snapshot_digest,
        "requested_compatibility_group": args.compatibility_group,
        "ledger_sequence": position.sequence,
        "ledger_head_digest": position.head_event_digest,
        "active_checkpoint": None if active is None else _checkpoint_summary(active),
        "requested_checkpoint": None if requested is None else _checkpoint_summary(requested),
        "compaction_enabled": bool(
            context.config.parity.context_ledger.enabled and context.config.parity.context_ledger.compaction_enabled
        ),
        "provider_execution": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects": "NONE",
    }


def cmd_context_adopt(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    trust, trust_store_digest = _context_trust_verifier(args.trust_store)
    service = _context_compaction_service(
        context,
        args,
        trust_verifier=trust,
        require_enabled=True,
    )
    checkpoint = service.get(args.checkpoint_id)
    if checkpoint.compatibility_group != args.compatibility_group:
        raise ConflictError("checkpoint is bound to another compatibility group")
    service.verify_warm_evidence(checkpoint.checkpoint_id)
    expected_raw = args.expected_active_checkpoint_id
    expected_active = None if expected_raw == "NONE" else expected_raw
    if expected_active is not None:
        predecessor = service.get(expected_active)
        if predecessor.checkpoint_id != checkpoint.previous_checkpoint_id:
            raise ConflictError("expected active checkpoint is not the prepared predecessor")

    def write() -> dict[str, Any]:
        adopted = service.adopt(
            checkpoint.checkpoint_id,
            expected_active_checkpoint_id=expected_active,
        )
        return {
            "schema_version": "1.2.0",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "stream_id": args.stream,
            "adopted_checkpoint": _checkpoint_summary(adopted),
            "provider_execution": "EXTERNAL_EVIDENCE_VERIFIED",
            "certification": "NOT_CERTIFIED",
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI context adopt",
        {
            "stream_id": args.stream,
            "branch_lineage": args.branch_lineage,
            "repository_snapshot_digest": service.ledger.repository_snapshot_digest,
            "compatibility_group": args.compatibility_group,
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "expected_active_checkpoint_id": expected_active,
            "trust_store_digest": trust_store_digest,
        },
        write,
    )


def cmd_context_rollback(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    trust, trust_store_digest = _context_trust_verifier(args.trust_store)
    service = _context_compaction_service(
        context,
        args,
        trust_verifier=trust,
        require_enabled=True,
    )
    current = service.get(args.checkpoint_id)
    if current.compatibility_group != args.compatibility_group:
        raise ConflictError("checkpoint is bound to another compatibility group")
    if current.previous_checkpoint_id is None:
        raise ConflictError("the initial checkpoint has no rollback predecessor")
    # Revalidate tenant ownership, CAS bytes and Ed25519 evidence before the
    # idempotency claim. This still permits exact replay after rollback because
    # it does not require the target to remain ACTIVE.
    service.verify_warm_evidence(current.previous_checkpoint_id)

    def write() -> dict[str, Any]:
        restored = service.rollback(args.checkpoint_id)
        return {
            "schema_version": "1.2.0",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "stream_id": args.stream,
            "rolled_back_checkpoint_id": args.checkpoint_id,
            "restored_checkpoint": _checkpoint_summary(restored),
            "provider_execution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    return _execute_idempotent(
        context,
        args.idempotency_key,
        "CLI context rollback",
        {
            "stream_id": args.stream,
            "branch_lineage": args.branch_lineage,
            "repository_snapshot_digest": service.ledger.repository_snapshot_digest,
            "compatibility_group": args.compatibility_group,
            "checkpoint_id": args.checkpoint_id,
            "trust_store_digest": trust_store_digest,
        },
        write,
    )


def cmd_affinity_decide(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_json_object(args.input)
    _assert_payload_scope(context, payload)
    raise ContractViolation(
        "standalone affinity decisions require a server-side attested runner registry; "
        "caller-supplied candidates are not trusted"
    )


def cmd_parity_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    tables = {
        "prompt_manifests": "prompt_prefix_manifests",
        "provider_usage": "provider_cache_usage",
        "environment_snapshots": "environment_snapshot_manifests",
        "environment_status_events": "environment_snapshot_status_events",
        "cache_outcomes": "cache_outcome_events_v12",
        "affinity_decisions": "cache_affinity_decisions_v12",
        "parity_reports": "cache_parity_reports_v12",
    }
    counts: dict[str, int] = {}
    for label, table in tables.items():
        row = context.store.query_one(
            f"SELECT COUNT(*) FROM {table} WHERE tenant_id=? AND project_id=?",  # noqa: S608
            (context.tenant_id, project_id),
        )
        counts[label] = 0 if row is None else int(row[0])
    parity = context.config.parity
    runtime = ParityRuntime(parity, context.tenant_id, project_id).report()
    if runtime is None:
        runtime = {
            "schema_version": parity.schema_version,
            "claim_mode": parity.claim_mode,
            "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
            "certification": "NOT_CERTIFIED",
            "external_provider_evidence": "NOT_RUN",
            "rollout_phase": parity.rollout_phase,
            "serving_requested": {},
            "serving": {},
            "wiring": {"runtime": "NOT_WIRED"},
            "serving_gate_receipt": {
                "required": False,
                "status": "NOT_REQUIRED",
                "reason_code": "PARITY_PLANE_DISABLED",
                "key_id": None,
                "authorized_layers": [],
            },
            "rollback": {"latched": False, "reason_code": None, "delivery_errors": []},
            "degraded": False,
        }
    return {
        **runtime,
        "enabled": parity.enabled,
        "tenant_id": context.tenant_id,
        "project_id": project_id,
        "records": counts,
    }


def cmd_parity_evaluate(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_json_object(args.input)
    project_id = _assert_payload_scope(context, payload)
    report = evaluate_cache_parity_payload(
        context.tenant_id,
        payload,
        evidence_verifier=CasParityEvidenceVerifier(context.cas),
    )
    document = report.to_dict()
    response = {**document, "persisted": False}
    if not args.persist:
        return response
    repository = ParityMetadataRepository(context.store)

    def write() -> dict[str, Any]:
        repository.put_parity_report(
            context.tenant_id,
            project_id,
            report.report_id,
            document,
        )
        return {**document, "persisted": True}

    return _persist_idempotent(
        context,
        args,
        "CLI parity evaluate",
        project_id,
        document,
        write,
    )


def cmd_parity_report(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    project_id = _require_project(context)
    report = ParityMetadataRepository(context.store).get_parity_report(
        context.tenant_id,
        project_id,
        args.report_id,
    )
    if report is None:
        raise NotFound("parity report does not exist", report_id=args.report_id)
    return report


COMMANDS: dict[tuple[str, str], Any] = {
    ("cache", "status"): cmd_cache_status,
    ("cache", "inspect"): cmd_cache_inspect,
    ("cache", "explain-miss"): cmd_cache_explain_miss,
    ("cache", "explain"): cmd_cache_explain,
    ("cache", "verify"): cmd_cache_verify,
    ("cache", "pin"): cmd_cache_pin,
    ("cache", "unpin"): cmd_cache_unpin,
    ("cache", "gc"): cmd_cache_gc,
    ("cache", "explain-retention"): cmd_cache_explain_retention,
    ("workspace", "list"): cmd_workspace_list,
    ("workspace", "inspect"): cmd_workspace_inspect,
    ("workspace", "recover"): cmd_workspace_recover,
    ("workspace", "quarantine"): cmd_workspace_quarantine,
    ("run", "resume"): cmd_run_resume,
    ("run", "pause"): cmd_run_pause,
    ("run", "cancel"): cmd_run_cancel,
    ("artifact", "materialize"): cmd_artifact_materialize,
    ("doctor", "cache"): cmd_doctor_cache,
    ("policy", "show"): cmd_policy_show,
    ("policy", "benchmark"): cmd_policy_benchmark,
    ("policy", "matrix"): cmd_policy_matrix,
    ("policy", "select"): cmd_policy_select,
    ("policy", "certify"): cmd_policy_certify,
    ("trace", "generate"): cmd_trace_generate,
    ("trace", "verify"): cmd_trace_verify,
    ("trace", "workloads"): cmd_trace_workloads,
    ("prompt", "compile"): cmd_prompt_compile,
    ("prompt", "diff"): cmd_prompt_diff,
    ("environment", "inspect"): cmd_environment_inspect,
    ("environment", "seal"): cmd_environment_seal,
    ("environment", "restore"): cmd_environment_restore,
    ("context", "plan"): cmd_context_plan,
    ("context", "prepare"): cmd_context_prepare,
    ("context", "status"): cmd_context_status,
    ("context", "adopt"): cmd_context_adopt,
    ("context", "rollback"): cmd_context_rollback,
    ("affinity", "decide"): cmd_affinity_decide,
    ("parity", "status"): cmd_parity_status,
    ("parity", "evaluate"): cmd_parity_evaluate,
    ("parity", "report"): cmd_parity_report,
}


def render(payload: dict[str, Any], as_text: bool) -> str:
    if not as_text:
        return json.dumps(payload, indent=2, sort_keys=True, default=str)
    lines: list[str] = []

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                walk(value[key], f"{prefix}{key}.")
        elif isinstance(value, list):
            lines.append(f"{prefix.rstrip('.')}: {len(value)} item(s)")
        else:
            lines.append(f"{prefix.rstrip('.')}: {value}")

    walk(payload)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    key = (args.group, args.command)
    handler = COMMANDS.get(key)
    if handler is None:
        parser.error(f"unknown command: {args.group} {args.command}")
        return EXIT_ERROR
    context: Context | None = None
    try:
        requires_explicit_scope = args.group == "context" or (
            args.group == "environment" and args.command in {"seal", "restore"}
        )
        if requires_explicit_scope and (args.tenant is None or args.project is None):
            raise ContractViolation("this command requires explicit --tenant and --project scope")
        context = _context(args)
        payload = handler(context, args)
    except ElmosCacheError as exc:
        print(json.dumps({"error": exc.to_dict()}, indent=2, sort_keys=True), file=sys.stderr)
        return EXIT_ERROR
    finally:
        if context is not None:
            context.store.close()
    print(render(payload, args.text))
    if key == ("doctor", "cache") and not payload.get("healthy", True):
        return EXIT_UNHEALTHY
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
