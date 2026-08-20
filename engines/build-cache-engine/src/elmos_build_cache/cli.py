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
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .action_cache import ActionCache, HotIndex
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
from .canonical import require_digest
from .cas import ContentAddressableStore
from .clock import SYSTEM_CLOCK, Clock
from .config import CacheConfig, default_config, load_config
from .db import MetadataStore, open_store
from .enums import RunStatus, StagedFileStatus, TrustNamespace
from .errors import ContractViolation, ElmosCacheError, NotFound
from .gc import GarbageCollector, RetentionPolicy, explain_retention
from .journal import LeaseManager, RunCoordinator, RunJournal
from .policy_certification import (
    CertificationContext,
    RolloutPlan,
    benchmark_matrix,
    certify_policy,
)
from .policy_orchestrator import RuleSelector, configuration_digest
from .policy_plane import PolicyPlane
from .security import Ed25519ProvenanceSigner
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
                create_policy(
                    self.config.policy.l2_policy, self.config.local.max_size_gb * 1024**3
                )
                if self.config.policy.enabled
                else None
            ),
        )

    def workspace(self, run_id: str) -> Workspace:
        run = self.store.get_run(run_id)
        return Workspace(
            self.base / self.config.workspace.root,
            run.tenant_id,
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
    parser.add_argument("--tenant", default="default", help="tenant scope (required for mutations)")
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

    doctor = subparsers.add_parser("doctor", help="diagnostics").add_subparsers(
        dest="command", required=True
    )
    doctor.add_parser("cache", help="check local cache health")
    return parser


def _context(args: argparse.Namespace) -> Context:
    config = load_config(args.config) if args.config else default_config()
    base = Path(args.base)
    paths = config.resolved(base)
    store = open_store(paths.metadata)
    cas = ContentAddressableStore(
        paths.cache_root,
        compression=config.local.compression,
        max_bytes=config.local.max_size_gb * 1024**3,
    )
    return Context(config, base, args.tenant, args.project, store, cas)


# --------------------------------------------------------------------------
# cache commands
# --------------------------------------------------------------------------
def cmd_cache_status(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "tenant_id": context.tenant_id,
        "cas": context.cas.accounting(),
        "action_cache": context.action_cache.statistics(context.tenant_id),
        "runs": {
            str(status): len(context.store.list_runs(context.tenant_id, [status]))
            for status in RunStatus
        },
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
    events = [
        event
        for event in context.store.list_events(args.run_id)
        if event["node_id"] == args.node_id
    ]
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
            "no recorded miss reasons; re-run with the planner attached to record "
            "fingerprint dimension comparisons"
            if not miss_events
            else ""
        ),
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
    expires = (
        context.clock.now() + args.expires_in_hours * 3600.0 if args.expires_in_hours else None
    )
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
            raise ElmosCacheError("--apply requires --idempotency-key")
        with context.store.transaction():
            collector.approve(args.apply_plan)
            outcome = collector.apply(args.apply_plan)
        return {"applied": True, **outcome}
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
    digest = require_digest(
        args.digest if args.digest.startswith("sha256:") else f"sha256:{args.digest}"
    )
    return explain_retention(context.collector(), digest)


# --------------------------------------------------------------------------
# workspace commands
# --------------------------------------------------------------------------
def cmd_workspace_list(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    runs = context.store.list_runs(context.tenant_id)
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
    workspace = context.workspace(args.run_id)
    record = context.store.get_staged_file(args.staged_file_id)
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
    workspace = context.workspace(args.run_id)
    coordinator = context.coordinator(args.run_id)
    with context.store.transaction():
        recovery = workspace.recover()
        expired = coordinator.recover_expired()
        run = context.store.get_run(args.run_id)
        if run.status is not RunStatus.RUNNING:
            context.store.transition_run(args.run_id, RunStatus.RUNNING, run.version)
    return {"run_id": args.run_id, "recovery": recovery, "reclaimed_nodes": expired}


def cmd_run_pause(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    run = context.store.get_run(args.run_id)
    if run.version != args.expected_version:
        raise ElmosCacheError(
            f"run version conflict: expected {args.expected_version}, found {run.version}"
        )
    with context.store.transaction():
        context.coordinator(args.run_id).pause_run(args.run_id)
    return {"run_id": args.run_id, "status": str(context.store.get_run(args.run_id).status)}


def cmd_run_cancel(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    run = context.store.get_run(args.run_id)
    if run.version != args.expected_version:
        raise ElmosCacheError(
            f"run version conflict: expected {args.expected_version}, found {run.version}"
        )
    with context.store.transaction():
        context.coordinator(args.run_id).cancel_run(args.run_id, args.reason)
    staged = context.store.list_staged_files(args.run_id)
    return {
        "run_id": args.run_id,
        "status": str(context.store.get_run(args.run_id).status),
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


# --------------------------------------------------------------------------
# artifact and doctor
# --------------------------------------------------------------------------
def cmd_artifact_materialize(context: Context, args: argparse.Namespace) -> dict[str, Any]:
    digest = require_digest(
        args.digest if args.digest.startswith("sha256:") else f"sha256:{args.digest}"
    )
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
        run.run_id
        for run in context.store.list_runs(context.tenant_id, [RunStatus.RUNNING, RunStatus.RECOVERING])
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
        "capabilities": PolicyPlane.from_config(
            policy, tenant_id=context.tenant_id
        ).report()["capabilities"],
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
            "signed with an ephemeral key; supply --signing-key for a certificate "
            "anyone else can verify"
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


COMMANDS: dict[tuple[str, str], Any] = {
    ("cache", "status"): cmd_cache_status,
    ("cache", "inspect"): cmd_cache_inspect,
    ("cache", "explain-miss"): cmd_cache_explain_miss,
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
    context = _context(args)
    try:
        payload = handler(context, args)
    except ElmosCacheError as exc:
        print(json.dumps({"error": exc.to_dict()}, indent=2, sort_keys=True), file=sys.stderr)
        return EXIT_ERROR
    finally:
        pass
    print(render(payload, args.text))
    if key == ("doctor", "cache") and not payload.get("healthy", True):
        return EXIT_UNHEALTHY
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
