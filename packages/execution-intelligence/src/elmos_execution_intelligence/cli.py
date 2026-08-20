from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .artifacts import write_split_artifacts
from .calibration import accuracy_report, apply_calibration, calibrate, estimator_profiles
from .certifier import build_evidence_manifest, evaluate, render_report
from .chaos import render_recovery_evidence, run_chaos
from .comparison import compare
from .cost import estimate_costs
from .decompose import critical_path_seed, decompose, estimation_seed_rows
from .durable import DurableStore, StoreUnavailable, recovery_aware_eta
from .human_anchor import GIT_LOG_COMMAND, anchor_from_log, compare_to_forecast, parse_git_log, render_anchor
from .io_utils import load_json, read_jsonl, write_json, write_text
from .jsonschema_lite import Validator
from .publisher import build_manifest
from .report import write_reports
from .routing import optimize_routing, render_routing_comparison
from .runner import execute_run, render_execution_plan
from .scope import audit_scope, render_scope_baseline, seed_project_profile
from .server import ReferenceServer
from .simulation import simulate_human, simulate_system, summarize_task_tokens, summarize_tokens
from .skill_advice import advise, render_advice
from .telemetry import (
    ingest_report,
    parse_agent_transcript,
    rows_from_pytest_durations,
    rows_from_pytest_logs,
    rows_from_transcripts,
    transcript_ingest_report,
)
from .token_mix import CATEGORIES, compare_mix, forecast_mix, mix_warmup, render_mix
from .token_scan import scan_tokens
from .validation import validate_all, validate_tasks

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PACKAGE_ROOT / "schemas"
CONFIG_DIR = PACKAGE_ROOT / "config"

#: Every emitted JSON artifact is checked against its schema before the command
#: returns. A schema nothing executes is a contract that rots silently.
ARTIFACT_SCHEMAS = {
    "project-forecast.json": "project-forecast.schema.json",
    "token-forecast.json": "token-forecast.schema.json",
    "cost-forecast.json": "cost-forecast.schema.json",
    "autonomous-runtime.json": "autonomous-runtime.schema.json",
    "human-effort.json": "human-effort.schema.json",
    "time-comparison.json": "time-comparison.schema.json",
    "scope-baseline.json": "scope-baseline.schema.json",
    "risk-and-gap-register.json": "risk-and-gap-register.schema.json",
    "task-dag.json": "task-dag.schema.json",
    "critical-path-seed.json": "critical-path-seed.schema.json",
    "project-profile.seed.json": "project-profile.schema.json",
    "model-routing-plan.json": "model-routing-plan.schema.json",
    "result-manifest.json": "result-manifest.schema.json",
    "chaos-test-report.json": "chaos-test-report.schema.json",
    "production-readiness.json": "production-readiness.schema.json",
    "evidence-manifest.json": "evidence-manifest.schema.json",
    "recovery-eta-update.json": "recovery-eta-update.schema.json",
    "telemetry-ingest.json": "telemetry-ingest.schema.json",
    "calibration.json": "calibration.schema.json",
    "token-mix-comparison.json": "token-mix-comparison.schema.json",
}


class Blocked(ValueError):
    """Raised when a required input is missing. The CLI never guesses past this."""


def _load_and_validate(
    project_path: str, tasks_path: str, pricing_path: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project = load_json(project_path)
    tasks = load_json(tasks_path)
    pricing = load_json(pricing_path)
    errors, warnings = validate_all(project, tasks, pricing)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        raise Blocked("BLOCKED — validation failed:\n- " + "\n- ".join(errors))
    return project, tasks, pricing


def command_validate(args: argparse.Namespace) -> int:
    _load_and_validate(args.project, args.tasks, args.pricing)
    print("Validation passed")
    return 0


def build_forecast(
    project: dict[str, Any],
    tasks: dict[str, Any],
    pricing: dict[str, Any],
    static_scan: dict[str, Any] | None = None,
    mix_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    worst_probability = float(project.get("system", {}).get("worst_case_quantile", 0.99))
    system_runtime, token_samples, per_task_tokens = simulate_system(project, tasks)
    tokens = summarize_tokens(token_samples, worst_probability)
    task_tokens = summarize_task_tokens(per_task_tokens, tasks["tasks"], worst_probability)
    costs = estimate_costs(token_samples, pricing, worst_probability, mix_report=mix_report)
    human = simulate_human(project, tasks)
    comparison = compare(project, system_runtime, human, costs)
    forecast: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "tokens": tokens,
        "task_tokens": task_tokens,
        "costs": costs,
        "system_runtime": system_runtime,
        "human_effort": human,
        "comparison": comparison,
    }
    if static_scan is not None:
        forecast["static_scan"] = static_scan
    return forecast


def _check_artifacts(output: Path, names: list[str], schema_dir: Path) -> list[str]:
    validator = Validator(schema_dir)
    failures: list[str] = []
    for name in names:
        schema_name = ARTIFACT_SCHEMAS.get(name)
        if not schema_name:
            continue
        instance = load_json(output / name)
        for error in validator.validate(instance, schema_name):
            failures.append(f"{name}: {error}")
    return failures


def command_forecast(args: argparse.Namespace) -> int:
    project, tasks, pricing = _load_and_validate(args.project, args.tasks, args.pricing)
    static_scan = load_json(args.static_scan) if args.static_scan else None

    # If a mix comparison already exists for this output directory, the cost
    # report says so. Without it the report has to declare that its category mix
    # is an assumption, which is the honest default rather than silence.
    mix_report: dict[str, Any] | None = None
    mix_path = Path(args.output) / "token-mix-comparison.json"
    if mix_path.exists():
        try:
            mix_report = load_json(mix_path)
        except (OSError, ValueError):
            mix_report = None

    forecast = build_forecast(project, tasks, pricing, static_scan, mix_report=mix_report)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "project-forecast.json", forecast)
    split = write_split_artifacts(forecast, output)
    reports = write_reports(forecast, output)
    emitted = ["project-forecast.json"] + split + reports

    schema_dir = Path(args.schema_dir) if args.schema_dir else SCHEMA_DIR
    if not args.skip_schema_check:
        failures = _check_artifacts(output, emitted, schema_dir)
        if failures:
            raise Blocked(
                "BLOCKED — emitted artifacts do not match their schemas:\n- " + "\n- ".join(failures)
            )

    tokens = forecast["tokens"]
    runtime = forecast["system_runtime"]
    human = forecast["human_effort"]
    print(f"Forecast written to {output.resolve()}")
    for name in emitted:
        print(f"  - {name}")
    if not args.skip_schema_check:
        print(f"Schema check passed for {len(ARTIFACT_SCHEMAS)} JSON artifacts")
    print(f"Token  P50/P90 : {int(tokens['total']['p50']):,} / {int(tokens['total']['p90']):,}")
    print(f"System P50/P90 : {runtime['wall_clock_hours']['p50']} / {runtime['wall_clock_hours']['p90']} hours")
    print(f"Human  P50/P90 : {human['calendar_weeks']['p50']} / {human['calendar_weeks']['p90']} calendar weeks")
    return 0


def command_scan_tokens(args: argparse.Namespace) -> int:
    calibration = None
    if args.calibration:
        calibration = load_json(args.calibration)
    elif not args.no_default_calibration and (CONFIG_DIR / "token-count-calibration.json").exists():
        calibration = load_json(CONFIG_DIR / "token-count-calibration.json")
    result = scan_tokens(
        args.path,
        model=args.model,
        calibration=calibration,
        max_file_bytes=args.max_file_bytes,
        extra_ignore_dirs=tuple(args.ignore_dir or ()),
        group_depth=args.group_depth,
        top_n=args.top,
        include_file_list=args.include_file_list,
    )
    write_json(args.output, result)
    totals = result["totals"]
    print(f"Scanned {totals['files']:,} files ({totals['characters']:,} characters)")
    print(f"Estimated one-pass tokens: {totals['estimated_tokens']:,} ({result['counting_method']})")
    if totals.get("calibrated_tokens"):
        drift = totals["calibrated_tokens"] / totals["estimated_tokens"] - 1.0
        print(f"Calibrated against a real BPE tokenizer: {totals['calibrated_tokens']:,} "
              f"({drift * 100:+.1f}% vs the raw heuristic)")
    if result["findings"]:
        print(f"Context-pressure findings: {len(result['findings'])}")
    print(f"Result written to {Path(args.output).resolve()}")
    return 0


def command_audit_scope(args: argparse.Namespace) -> int:
    static_scan = load_json(args.static_scan) if args.static_scan else None
    baseline = audit_scope(
        args.path,
        token_scan=static_scan,
        extra_ignore_dirs=tuple(args.ignore_dir or ()),
    )
    defaults = load_json(args.defaults or (CONFIG_DIR / "estimation-defaults.json"))
    human_baselines = load_json(args.human_baselines or (CONFIG_DIR / "human-baselines.json"))
    model = load_json(args.model or (CONFIG_DIR / "decomposition-model.json"))
    widest = max(float(template.get("worker_units", 1)) for template in model["templates"])
    profile = seed_project_profile(
        baseline, defaults, human_baselines,
        project_id=args.project_id or Path(args.path).resolve().name,
        mode=args.mode,
        min_worker_units=widest,
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    register = baseline["risk_and_gap_register"]
    write_json(output / "scope-baseline.json", baseline)
    write_json(output / "risk-and-gap-register.json", register)
    write_json(output / "project-profile.seed.json", profile)
    write_text(output / "scope-baseline.md", render_scope_baseline(baseline))

    failures = _check_artifacts(
        output,
        ["scope-baseline.json", "risk-and-gap-register.json", "project-profile.seed.json"],
        Path(args.schema_dir) if args.schema_dir else SCHEMA_DIR,
    )
    if failures:
        raise Blocked("BLOCKED — scope artifacts do not match their schemas:\n- " + "\n- ".join(failures))

    print(f"Scope baseline written to {output.resolve()}")
    for name in ("scope-baseline.json", "scope-baseline.md",
                 "risk-and-gap-register.json", "project-profile.seed.json"):
        print(f"  - {name}")
    counts = register["counts_by_severity"]
    print(f"Gaps: high {counts['high']}, medium {counts['medium']}, low {counts['low']}")
    blocking = [gap["id"] for gap in register["gaps"] if gap.get("needs_human_input")]
    if blocking:
        print("Needs a human decision before a production-grade forecast: " + ", ".join(blocking))
    return 0


def command_decompose(args: argparse.Namespace) -> int:
    baseline = load_json(args.scope)
    model = load_json(args.model or (CONFIG_DIR / "decomposition-model.json"))
    document = decompose(baseline, model, dag_id=args.dag_id)

    errors = validate_tasks(document)
    if errors:
        raise Blocked("BLOCKED — generated task DAG is invalid:\n- " + "\n- ".join(errors))

    seed = critical_path_seed(document)
    rows = estimation_seed_rows(document)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "task-dag.json", document)
    write_json(output / "critical-path-seed.json", seed)

    csv_path = output / "task-estimation-seed.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    failures = _check_artifacts(
        output, ["task-dag.json", "critical-path-seed.json"],
        Path(args.schema_dir) if args.schema_dir else SCHEMA_DIR,
    )
    if failures:
        raise Blocked("BLOCKED — decomposition artifacts do not match their schemas:\n- " + "\n- ".join(failures))

    print(f"Task DAG written to {output.resolve()}")
    for name in ("task-dag.json", "critical-path-seed.json", "task-estimation-seed.csv"):
        print(f"  - {name}")
    print(f"Tasks: {len(document['tasks'])}")
    print(f"Drivers: {document['drivers']}")
    print(f"Critical path (no contention): {seed['critical_path_hours']} hours over "
          f"{len(seed['critical_path'])} tasks")
    return 0


def command_calibrate(args: argparse.Namespace) -> int:
    result = calibrate(read_jsonl(args.history))
    profiles = estimator_profiles(result)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "calibration.json", result)
    write_json(output / "estimator-profiles.json", profiles)
    write_text(output / "forecast-accuracy-report.md", accuracy_report(result, profiles))

    schema_dir = Path(args.schema_dir) if args.schema_dir else SCHEMA_DIR
    if not args.skip_schema_check:
        errors = Validator(schema_dir).validate(result, "calibration.schema.json")
        if errors:
            raise Blocked("BLOCKED — calibration.json does not match its schema:\n- " + "\n- ".join(errors))

    print(f"Calibration written to {output.resolve()} ({result['valid_samples']} valid samples)")
    for name in ("calibration.json", "estimator-profiles.json", "forecast-accuracy-report.md"):
        print(f"  - {name}")
    for label, block in (("runtime", result["global"]["runtime_multiplier"]),
                         ("token  ", result["global"]["token_multiplier"])):
        print(f"Global {label} multiplier P50: "
              + (str(block["p50"]) if block else "no data (not inferred)"))
    for reason in result.get("unavailable", []):
        print(f"  unavailable — {reason}")
    print(f"Applicable groups: {len(profiles['by_group'])}")
    return 0


def command_apply_calibration(args: argparse.Namespace) -> int:
    tasks = load_json(args.tasks)
    profiles = load_json(args.profiles)
    updated, changelog = apply_calibration(tasks, profiles)
    write_json(args.output, updated)
    grouped = sum(1 for row in changelog if row["basis"] == "group")
    print(f"Calibrated task DAG written to {Path(args.output).resolve()}")
    print(f"  {len(changelog)} tasks rewritten; {grouped} used a group multiplier, "
          f"{len(changelog) - grouped} fell back to global")
    return 0


def command_validate_schemas(args: argparse.Namespace) -> int:
    schema_dir = Path(args.schema_dir) if args.schema_dir else SCHEMA_DIR
    validator = Validator(schema_dir)
    directory = Path(args.directory)
    checked = 0
    failures: list[str] = []
    for name, schema_name in sorted(ARTIFACT_SCHEMAS.items()):
        candidate = directory / name
        if not candidate.exists():
            continue
        checked += 1
        for error in validator.validate(load_json(candidate), schema_name):
            failures.append(f"{name}: {error}")
    for extra, schema_name in (("calibration.json", "calibration.schema.json"),):
        candidate = directory / extra
        if candidate.exists():
            checked += 1
            for error in validator.validate(load_json(candidate), schema_name):
                failures.append(f"{extra}: {error}")
    if failures:
        print("BLOCKED — schema violations:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 3
    if checked == 0:
        print(f"BLOCKED — no known artifacts found under {directory}", file=sys.stderr)
        return 3
    print(f"Schema check passed for {checked} artifacts under {directory}")
    return 0


def _schema_dir(args: argparse.Namespace) -> Path:
    return Path(args.schema_dir) if getattr(args, "schema_dir", None) else SCHEMA_DIR


def _emit(output: Path, names: list[str], args: argparse.Namespace, label: str) -> None:
    failures = _check_artifacts(output, names, _schema_dir(args))
    if failures:
        raise Blocked(f"BLOCKED — {label} do not match their schemas:\n- " + "\n- ".join(failures))


def command_plan(args: argparse.Namespace) -> int:
    project = load_json(args.project)
    tasks = load_json(args.tasks)
    errors = validate_tasks(tasks)
    if errors:
        raise Blocked("BLOCKED — task DAG is invalid:\n- " + "\n- ".join(errors))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    plan = render_execution_plan(project, tasks, run_id=args.run_id or "not-yet-submitted",
                                 generated_at=args.generated_at or "unset")
    write_text(output / "TASK_EXECUTION_PLAN.md", plan)
    print(f"Execution plan written to {(output / 'TASK_EXECUTION_PLAN.md').resolve()}")
    return 0


def command_execute(args: argparse.Namespace) -> int:
    project = load_json(args.project)
    tasks = load_json(args.tasks)
    errors = validate_tasks(tasks)
    if errors:
        raise Blocked("BLOCKED — task DAG is invalid:\n- " + "\n- ".join(errors))

    store = DurableStore(args.store)
    try:
        result = execute_run(project, tasks, store, capacity=args.capacity, seed=args.seed,
                             failure_scale=args.failure_scale)
        run_id = result["run_id"]
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)

        manifest = build_manifest(store, run_id)
        eta = recovery_aware_eta(store, run_id, capacity=args.capacity or 4.0)
        rows = store.calibration_rows(run_id)

        write_json(output / "result-manifest.json", manifest)
        write_json(output / "recovery-eta-update.json", eta)
        write_json(output / "run-summary.json", {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "state": result["state"],
            "tasks": [{"task_id": t["task_id"], "state": t["state"], "attempts": t["attempt_count"]}
                      for t in result["tasks"]],
            "events": len(store.events_since(run_id, 0, limit=1_000_000)),
            "simulated": True,
            "note": "Executed by the simulated executor. Telemetry is synthetic but the durable "
                    "properties exercised are real.",
        })
        telemetry = output / "telemetry.jsonl"
        telemetry.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

        _emit(output, ["result-manifest.json", "recovery-eta-update.json"], args, "execution artifacts")

        print(f"Run {run_id} finished in state '{result['state']}'")
        for name in ("run-summary.json", "result-manifest.json", "recovery-eta-update.json", "telemetry.jsonl"):
            print(f"  - {name}")
        print(f"Artifacts published: {manifest['artifact_count']}, telemetry rows: {len(rows)}")
        print(f"Store: {Path(args.store).resolve() if args.store != ':memory:' else ':memory:'}")
        return 0
    finally:
        store.close()


def command_events(args: argparse.Namespace) -> int:
    store = DurableStore(args.store)
    try:
        if args.sse:
            print(store.sse_frames(args.run_id, last_event_id=args.after, limit=args.limit))
            return 0
        events = store.events_since(args.run_id, args.after, limit=args.limit)
        for event in events:
            print(f"{event['seq']:>5}  {event['event_type']:<24} {event['task_id'] or '-':<28} "
                  f"{json.dumps(event['payload'], ensure_ascii=False)}")
        print(f"{len(events)} event(s) after seq {args.after}")
        return 0
    finally:
        store.close()


def command_eta(args: argparse.Namespace) -> int:
    store = DurableStore(args.store)
    try:
        eta = recovery_aware_eta(store, args.run_id, capacity=args.capacity)
        if args.output:
            write_json(args.output, eta)
            print(f"ETA written to {Path(args.output).resolve()}")
        print(f"Completed {eta['completed_fraction'] * 100:.1f}% · basis {eta['basis']} · "
              f"observed multiplier {eta['observed_runtime_multiplier']}")
        print(f"Remaining wall-clock P50/P90: {eta['wall_clock_hours']['p50']} / "
              f"{eta['wall_clock_hours']['p90']} hours (machine-autonomous only)")
        return 0
    finally:
        store.close()


def command_export_telemetry(args: argparse.Namespace) -> int:
    store = DurableStore(args.store)
    try:
        rows = store.calibration_rows(args.run_id)
        if not rows:
            print("BLOCKED — no completed task has both an estimate and executed usage", file=sys.stderr)
            return 3
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(f"{len(rows)} telemetry row(s) written to {destination.resolve()}")
        return 0
    finally:
        store.close()


def command_ingest_telemetry(args: argparse.Namespace) -> int:
    tasks = load_json(args.tasks)
    task = next((item for item in tasks["tasks"] if item["id"] == args.task_id), None)
    if task is None:
        raise Blocked(
            f"BLOCKED — task '{args.task_id}' is not in {args.tasks}; "
            "telemetry has to attach to a task whose estimate it can be compared against"
        )

    sources = [bool(args.pytest_log), bool(args.durations_log), bool(args.transcript)]
    if sum(sources) != 1:
        raise Blocked(
            "BLOCKED — give exactly one source: --pytest-log (aggregate), --durations-log "
            "(per node), or --transcript (per session, the only one carrying token counts). "
            "Mixing measurement bases in one file would make the calibration unreadable."
        )

    caveats = tuple(args.caveat or ())
    if args.transcript:
        rows, parsed = rows_from_transcripts(
            args.transcript, task, task_type=args.task_type,
            complexity=args.complexity, caveats=caveats)
        report = transcript_ingest_report(rows, parsed)
    elif args.durations_log:
        if not args.unit_count:
            raise Blocked("BLOCKED — --unit-count is required for a pytest source")
        rows, parsed = rows_from_pytest_durations(
            args.durations_log, task, unit_count=args.unit_count,
            task_type=args.task_type, complexity=args.complexity, caveats=caveats,
            allow_truncated=args.allow_truncated_durations)
        report = ingest_report(rows, parsed)
        report["measurement"] = "per_node_observed"
    else:
        if not args.unit_count:
            raise Blocked("BLOCKED — --unit-count is required for a pytest source")
        rows, parsed = rows_from_pytest_logs(
            args.pytest_log, task, unit_count=args.unit_count,
            task_type=args.task_type, complexity=args.complexity, caveats=caveats)
        report = ingest_report(rows, parsed)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "telemetry-real.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    write_json(output / "telemetry-ingest.json", report)
    _emit(output, ["telemetry-ingest.json"], args, "telemetry ingest artifacts")

    print(f"Ingested {len(rows)} real measurement(s) into {output.resolve()}")
    for name in ("telemetry-real.jsonl", "telemetry-ingest.json"):
        print(f"  - {name}")
    print(f"Measurement basis: {report['measurement']}; "
          f"token data available: {report['token_data_available']}")

    if args.transcript:
        for row, item in zip(rows, parsed, strict=True):
            ratio = row["actual_total_tokens"] / row["estimated_total_tokens"]
            print(f"  {item['transcript']}: {int(row['actual_total_tokens']):,} real tokens "
                  f"vs estimated {int(row['estimated_total_tokens']):,} (ratio {ratio:.3f})")
    elif args.durations_log:
        for item in parsed:
            print(f"  {item['log']}: {item['executed_nodes']} nodes, "
                  f"mean {item['mean_seconds_per_node']:.2f}s/node")
    else:
        for row, item in zip(rows, parsed, strict=True):
            ratio = row["actual_minutes"] / row["estimated_minutes"] if row["estimated_minutes"] else 0.0
            print(f"  {item['log']}: {item['executed_nodes']} nodes in {item['total_seconds']}s "
                  f"-> {row['actual_minutes']:.3f} min/unit vs estimated "
                  f"{row['estimated_minutes']:.3f} (ratio {ratio:.3f})")
    return 0


def command_advise_skills(args: argparse.Namespace) -> int:
    scan = load_json(args.static_scan)
    report = advise(args.path or scan["root"], scan, threshold=args.threshold, top_n=args.top)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "skill-split-advice.json", report)
    write_text(output / "SKILL_SPLIT_ADVICE.md", render_advice(report))
    print(f"Split advice written to {output.resolve()}")
    for name in ("skill-split-advice.json", "SKILL_SPLIT_ADVICE.md"):
        print(f"  - {name}")
    print(f"Flagged {report['flagged']}, advised {report['advised']}; "
          f"{report['total_tokens_movable']:,} tokens are movable to references/")
    if report["cannot_fit_by_moving_alone"]:
        print(f"{len(report['cannot_fit_by_moving_alone'])} skill(s) cannot fit by moving sections alone "
              "— they need splitting into separate skills", file=sys.stderr)
    return 0


def command_token_mix(args: argparse.Namespace) -> int:
    dag = load_json(args.tasks)
    tasks = dag.get("tasks") or dag.get("nodes") or []
    if not tasks:
        raise Blocked(f"BLOCKED — {args.tasks} contains no tasks to read a token profile from")

    observed: dict[str, float] = dict.fromkeys(CATEGORIES, 0.0)
    models: list[str] = []
    sessions = 0
    turns: list[dict[str, int]] = []
    for transcript in args.transcript:
        report = parse_agent_transcript(transcript)
        sessions += 1
        for field in CATEGORIES:
            observed[field] += float(report["tokens"][field])
        for model in report["models"]:
            if model not in models:
                models.append(model)
        turns.extend(report["turns"])

    if args.project_tokens is not None:
        p50 = float(args.project_tokens)
    else:
        forecast = load_json(args.forecast)
        totals = forecast.get("totals") or {}
        if "total" not in totals or "p50" not in (totals.get("total") or {}):
            raise Blocked(
                f"BLOCKED — {args.forecast} has no totals.total.p50 to compare against. "
                "Pass --project-tokens explicitly if you mean to supply it by hand."
            )
        p50 = float(totals["total"]["p50"])

    report = compare_mix(
        forecast_mix(tasks), observed, p50, load_json(args.pricing),
        observed_sessions=sessions, observed_models=models,
        minimum_sessions=args.minimum_sessions,
        warmup=mix_warmup(turns) if turns else None,
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "token-mix-comparison.json", report)
    write_text(output / "TOKEN_MIX_COMPARISON.md", render_mix(report))
    print(f"Token mix comparison written to {output.resolve()}")
    for name in ("token-mix-comparison.json", "TOKEN_MIX_COMPARISON.md"):
        print(f"  - {name}")
    depth_rows = report.get("cost_by_session_depth") or []
    if depth_rows:
        shortest, longest = depth_rows[0], depth_rows[-1]
        print(f"Cost overstatement scales with task length: "
              f"{shortest['overstatement_factor']:.2f}x at {shortest['turns']} turns -> "
              f"{longest['overstatement_factor']:.2f}x at {longest['turns']}. "
              "It is not a flat factor.")
    else:
        factor = report["overstatement_factor_range"]
        if factor:
            print(f"Cost is overstated up to {factor[1]:.2f}x by the assumed mix alone "
                  f"(token total unchanged)")
    warmup = report.get("warmup")
    if warmup:
        print(f"Cache share warms up {warmup['cached_input_share_at_shallowest'] * 100:.1f}% -> "
              f"{warmup['cached_input_share_at_full_session'] * 100:.1f}% over "
              f"{warmup['per_turn_cached_share']['turns']} turns; short tasks do not get the "
              "full-session mix")
    if not report["sample_sufficient"]:
        print(f"{sessions} session(s) is below the {args.minimum_sessions}-session floor — "
              "this is a finding, not a calibration", file=sys.stderr)
    return 0


def command_human_anchor(args: argparse.Namespace) -> int:
    if not Path(args.git_log).exists():
        raise Blocked(
            f"BLOCKED — {args.git_log} does not exist. Produce it with:\n  {GIT_LOG_COMMAND}"
        )
    rows = parse_git_log(args.git_log)
    anchor = anchor_from_log(
        rows, scope_label=args.scope or args.git_log,
        work_hours_per_day=args.work_hours_per_day, focus_ratio=args.focus_ratio)

    comparison = None
    if args.forecast:
        forecast = load_json(args.forecast)
        comparison = compare_to_forecast(anchor, forecast["human_effort"])
        anchor["comparison_to_forecast"] = comparison

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "human-baseline-anchor.json", anchor)
    write_text(output / "HUMAN_BASELINE_ANCHOR.md", render_anchor(anchor, comparison))

    print(f"Anchor written to {output.resolve()}")
    for name in ("human-baseline-anchor.json", "HUMAN_BASELINE_ANCHOR.md"):
        print(f"  - {name}")
    bounds = anchor["person_hours_bounds"]
    print(f"{anchor['commits']} commits by {anchor['authors']} author(s) over "
          f"{anchor['calendar_days']} calendar days")
    print(f"Person-hours anchor: {bounds['lower']:,.0f} - {bounds['upper']:,.0f} (bounds, not a measurement)")
    if comparison:
        print(f"Versus the forecast: {comparison['verdict']}")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    store = DurableStore(args.store, allow_cross_thread=True)
    server = ReferenceServer(store, host=args.host, port=args.port, bearer=args.bearer)
    print(f"Reference server on {server.base_url}")
    print("  This implements the guarantee-bearing parts of openapi/task-execution-api.yaml.")
    print("  It is a reference, not a deployment: single process, no TLS, no rate limiting.")
    print("  Try:")
    print(f"    curl -s {server.base_url}/runs/<id>/events?afterSeq=0 | head")
    print(f"    curl -s -H 'Last-Event-ID: 5' -H 'Accept: text/event-stream' "
          f"{server.base_url}/runs/<id>/events")
    try:
        server.start()
        server.thread.join() if server.thread else None
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.stop()
        store.close()
    return 0


def command_route(args: argparse.Namespace) -> int:
    tasks = load_json(args.tasks)
    pricing = load_json(args.pricing)
    capabilities = load_json(args.capabilities or (CONFIG_DIR / "provider-capabilities.json"))
    plan = optimize_routing(tasks, pricing, capabilities, currency=args.currency)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "model-routing-plan.json", plan)
    write_text(output / "MODEL_ROUTING_COMPARISON.md", render_routing_comparison(plan))
    _emit(output, ["model-routing-plan.json"], args, "routing artifacts")

    totals = plan["totals"]
    print(f"Routing plan written to {output.resolve()}")
    for name in ("model-routing-plan.json", "MODEL_ROUTING_COMPARISON.md"):
        print(f"  - {name}")
    print(f"Currency {plan['currency']}: optimized {totals['optimized']} vs "
          f"frontier baseline {totals['frontier_baseline']} "
          f"(saving {totals['saving']})")
    if plan["unroutable_tasks"]:
        print(f"WARNING: {len(plan['unroutable_tasks'])} task(s) have no eligible model", file=sys.stderr)
    if plan["rates_are_illustrative"]:
        print("WARNING: rates are illustrative and must not back a budget", file=sys.stderr)
    return 0


def command_chaos(args: argparse.Namespace) -> int:
    project = load_json(args.project)
    report = run_chaos(project, args.scenario)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "chaos-test-report.json", report)
    write_text(output / "recovery-evidence.md", render_recovery_evidence(report))
    _emit(output, ["chaos-test-report.json"], args, "chaos artifacts")

    counts = report["counts"]
    print(f"Chaos report written to {output.resolve()}")
    for name in ("chaos-test-report.json", "recovery-evidence.md"):
        print(f"  - {name}")
    print(f"Scenarios run {counts['run']} · passed {counts['passed']} · failed {counts['failed']} "
          f"· not run {counts['not_run']}")
    for scenario in report["scenarios"]:
        if not scenario["passed"]:
            failing = [item["name"] for item in scenario["assertions"] if not item["ok"]]
            print(f"  FAILED {scenario['scenario']}: {failing}", file=sys.stderr)
    return 0 if report["passed"] else 1


def command_certify(args: argparse.Namespace) -> int:
    report = evaluate(args.evidence, min_calibration_samples=args.min_calibration_samples)
    manifest = build_evidence_manifest(report, args.evidence)
    output = Path(args.output or args.evidence)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "production-readiness.json", report)
    write_json(output / "evidence-manifest.json", manifest)
    write_text(output / "production-readiness-report.md", render_report(report))
    _emit(output, ["production-readiness.json", "evidence-manifest.json"], args, "certification artifacts")

    print(f"Certification written to {output.resolve()}")
    for name in ("production-readiness.json", "production-readiness-report.md", "evidence-manifest.json"):
        print(f"  - {name}")
    counts = report["counts"]
    print(f"Decision: {report['decision'].upper()} "
          f"(pass {counts['pass']} · fail {counts['fail']} · not executed {counts['not_executed']})")
    return 0 if report["decision"] == "release" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elmos-ei",
        description="Elmos execution intelligence: token, cost, autonomous runtime and human-baseline forecasting.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a project profile, task DAG and pricing registry")
    validate_parser.add_argument("--project", required=True)
    validate_parser.add_argument("--tasks", required=True)
    validate_parser.add_argument("--pricing", required=True)
    validate_parser.set_defaults(func=command_validate)

    forecast_parser = subparsers.add_parser(
        "forecast", help="Produce token, cost, runtime, human and comparison forecasts")
    forecast_parser.add_argument("--project", required=True)
    forecast_parser.add_argument("--tasks", required=True)
    forecast_parser.add_argument("--pricing", required=True)
    forecast_parser.add_argument("--static-scan", help="Optional scan-tokens output to fold into TOKEN_BUDGET.md")
    forecast_parser.add_argument("--output", required=True)
    forecast_parser.add_argument("--schema-dir")
    forecast_parser.add_argument("--skip-schema-check", action="store_true",
                                 help="Emit artifacts without checking them against schemas/ (not recommended)")
    forecast_parser.set_defaults(func=command_forecast)

    scan_parser = subparsers.add_parser("scan-tokens", help="Estimate the one-pass token cost of material on disk")
    scan_parser.add_argument("path")
    scan_parser.add_argument("--model")
    scan_parser.add_argument("--max-file-bytes", type=int, default=2_000_000)
    scan_parser.add_argument("--ignore-dir", action="append", help="Extra directory name to skip (repeatable)")
    scan_parser.add_argument("--group-depth", type=int, default=1)
    scan_parser.add_argument("--top", type=int, default=40)
    scan_parser.add_argument("--include-file-list", action="store_true", help="Embed every scanned file in the output")
    scan_parser.add_argument("--calibration", help="Token-count calibration file (defaults to config/)")
    scan_parser.add_argument("--no-default-calibration", action="store_true",
                             help="Report the raw heuristic only, with no measured correction")
    scan_parser.add_argument("--output", required=True)
    scan_parser.set_defaults(func=command_scan_tokens)

    calibrate_parser = subparsers.add_parser(
        "calibrate", help="Derive runtime/token multipliers from executed telemetry")
    calibrate_parser.add_argument("--history", required=True, help="JSONL of executed tasks")
    calibrate_parser.add_argument("--output", required=True, help="Directory for calibration artifacts")
    calibrate_parser.add_argument("--schema-dir")
    calibrate_parser.add_argument("--skip-schema-check", action="store_true")
    calibrate_parser.set_defaults(func=command_calibrate)

    apply_parser = subparsers.add_parser(
        "apply-calibration", help="Rewrite a task DAG with calibrated runtime and token multipliers")
    apply_parser.add_argument("--tasks", required=True)
    apply_parser.add_argument("--profiles", required=True, help="estimator-profiles.json from calibrate")
    apply_parser.add_argument("--output", required=True)
    apply_parser.set_defaults(func=command_apply_calibration)

    scope_parser = subparsers.add_parser(
        "audit-scope", help="Audit a repository and seed a project profile plus a risk/gap register")
    scope_parser.add_argument("path")
    scope_parser.add_argument("--output", required=True)
    scope_parser.add_argument("--static-scan", help="Reuse an existing scan-tokens result instead of rescanning")
    scope_parser.add_argument("--ignore-dir", action="append")
    scope_parser.add_argument("--project-id")
    scope_parser.add_argument("--mode", default="verification")
    scope_parser.add_argument("--defaults")
    scope_parser.add_argument("--human-baselines")
    scope_parser.add_argument("--model", help="decomposition model, used to size the seeded worker count")
    scope_parser.add_argument("--schema-dir")
    scope_parser.set_defaults(func=command_audit_scope)

    decompose_parser = subparsers.add_parser(
        "decompose", help="Derive a task DAG from a scope baseline")
    decompose_parser.add_argument("--scope", required=True, help="scope-baseline.json from audit-scope")
    decompose_parser.add_argument("--model", help="decomposition model config (defaults to config/)")
    decompose_parser.add_argument("--dag-id", default="generated-dag")
    decompose_parser.add_argument("--output", required=True)
    decompose_parser.add_argument("--schema-dir")
    decompose_parser.set_defaults(func=command_decompose)

    plan_parser = subparsers.add_parser("plan", help="Render the task execution plan for a DAG")
    plan_parser.add_argument("--project", required=True)
    plan_parser.add_argument("--tasks", required=True)
    plan_parser.add_argument("--run-id")
    plan_parser.add_argument("--generated-at")
    plan_parser.add_argument("--output", required=True)
    plan_parser.set_defaults(func=command_plan)

    execute_parser = subparsers.add_parser(
        "execute", help="Execute a DAG durably with the simulated executor (produces real telemetry)")
    execute_parser.add_argument("--project", required=True)
    execute_parser.add_argument("--tasks", required=True)
    execute_parser.add_argument("--store", default=":memory:", help="SQLite path for durable state")
    execute_parser.add_argument("--capacity", type=float)
    execute_parser.add_argument("--seed", type=int, default=42)
    execute_parser.add_argument("--failure-scale", type=float, default=1.0)
    execute_parser.add_argument("--output", required=True)
    execute_parser.add_argument("--schema-dir")
    execute_parser.set_defaults(func=command_execute)

    events_parser = subparsers.add_parser("events", help="Replay a run's event stream from a sequence")
    events_parser.add_argument("--store", required=True)
    events_parser.add_argument("--run-id", required=True)
    events_parser.add_argument("--after", type=int, default=0, help="Last-Event-ID already processed")
    events_parser.add_argument("--limit", type=int, default=500)
    events_parser.add_argument("--sse", action="store_true", help="Emit SSE frames instead of a table")
    events_parser.set_defaults(func=command_events)

    eta_parser = subparsers.add_parser("eta", help="Recompute the ETA from executed telemetry")
    eta_parser.add_argument("--store", required=True)
    eta_parser.add_argument("--run-id", required=True)
    eta_parser.add_argument("--capacity", type=float, default=4.0)
    eta_parser.add_argument("--output")
    eta_parser.set_defaults(func=command_eta)

    telemetry_parser = subparsers.add_parser(
        "export-telemetry", help="Export executed usage as calibrate-ready JSONL")
    telemetry_parser.add_argument("--store", required=True)
    telemetry_parser.add_argument("--run-id", required=True)
    telemetry_parser.add_argument("--output", required=True)
    telemetry_parser.set_defaults(func=command_export_telemetry)

    ingest_parser = subparsers.add_parser(
        "ingest-telemetry",
        help="Turn real run artefacts (pytest logs) into calibrate rows, with their measurement basis recorded")
    ingest_parser.add_argument("--tasks", required=True)
    ingest_parser.add_argument("--task-id", required=True, help="Which DAG task the logs are evidence about")
    ingest_parser.add_argument("--pytest-log", action="append",
                               help="pytest log with a summary line: an aggregate mean per node (repeatable)")
    ingest_parser.add_argument("--durations-log", action="append",
                               help="pytest log produced with --durations=0 --durations-min=0: a real "
                                    "duration per node (repeatable). --durations=0 ALONE is not enough: "
                                    "pytest hides sub-5ms entries, leaving a slow-biased subset")
    ingest_parser.add_argument("--allow-truncated-durations", action="store_true",
                               help="Accept a durations log that pytest truncated. Off by default: the "
                                    "hidden entries are the fast ones, so the surviving sample inflates "
                                    "the mean in a consistent direction")
    ingest_parser.add_argument("--transcript", action="append",
                               help="Agent session transcript (Claude Code / Codex JSONL): the only source "
                                    "carrying real token counts (repeatable)")
    ingest_parser.add_argument("--unit-count", type=int,
                               help="How many units (routes/nodes) the task estimate covers; "
                                    "required for pytest sources")
    ingest_parser.add_argument("--task-type")
    ingest_parser.add_argument("--complexity")
    ingest_parser.add_argument("--caveat", action="append",
                               help="Extra caveat recorded on every emitted row (repeatable)")
    ingest_parser.add_argument("--output", required=True)
    ingest_parser.add_argument("--schema-dir")
    ingest_parser.set_defaults(func=command_ingest_telemetry)

    advise_parser = subparsers.add_parser(
        "advise-skills", help="Say which sections of an oversized SKILL.md to move to references/")
    advise_parser.add_argument("--static-scan", required=True, help="scan-tokens output")
    advise_parser.add_argument("--path", help="Repository root (defaults to the scan's root)")
    advise_parser.add_argument("--threshold", type=int, default=5000)
    advise_parser.add_argument("--top", type=int, default=50)
    advise_parser.add_argument("--output", required=True)
    advise_parser.set_defaults(func=command_advise_skills)

    mix_parser = subparsers.add_parser(
        "token-mix",
        help="Compare the forecast's assumed token category mix against real observed usage")
    mix_parser.add_argument("--tasks", required=True, help="task-dag.json")
    mix_parser.add_argument("--forecast", required=True, help="token-forecast.json")
    mix_parser.add_argument("--pricing", required=True, help="model-pricing.json")
    mix_parser.add_argument("--transcript", action="append", required=True,
                            help="Agent session transcript (repeatable)")
    mix_parser.add_argument("--project-tokens", type=float,
                            help="Override the P50 token total instead of reading the forecast")
    mix_parser.add_argument("--minimum-sessions", type=int, default=20)
    mix_parser.add_argument("--output", required=True)
    mix_parser.set_defaults(func=command_token_mix)

    anchor_parser = subparsers.add_parser(
        "human-anchor", help="Derive a human-effort anchor from an exported git log")
    anchor_parser.add_argument("--git-log", required=True,
                               help=f"Export produced by: {GIT_LOG_COMMAND}")
    anchor_parser.add_argument("--scope", help="Label for what the log covers")
    anchor_parser.add_argument("--forecast", help="project-forecast.json to compare against")
    anchor_parser.add_argument("--work-hours-per-day", type=float, default=8.0)
    anchor_parser.add_argument("--focus-ratio", type=float, default=0.65)
    anchor_parser.add_argument("--output", required=True)
    anchor_parser.set_defaults(func=command_human_anchor)

    serve_parser = subparsers.add_parser(
        "serve", help="Run the reference HTTP server for the task-execution API contract")
    serve_parser.add_argument("--store", default=":memory:")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument("--bearer", help="Require this bearer token")
    serve_parser.set_defaults(func=command_serve)

    route_parser = subparsers.add_parser(
        "route", help="Assign each task to the cheapest model that meets its capability floor")
    route_parser.add_argument("--tasks", required=True)
    route_parser.add_argument("--pricing", required=True)
    route_parser.add_argument("--capabilities")
    route_parser.add_argument("--currency")
    route_parser.add_argument("--output", required=True)
    route_parser.add_argument("--schema-dir")
    route_parser.set_defaults(func=command_route)

    chaos_parser = subparsers.add_parser(
        "chaos", help="Inject faults into a durable run and assert the recovery properties")
    chaos_parser.add_argument("--project", required=True)
    chaos_parser.add_argument("--scenario", action="append", help="Run only these scenarios (repeatable)")
    chaos_parser.add_argument("--output", required=True)
    chaos_parser.add_argument("--schema-dir")
    chaos_parser.set_defaults(func=command_chaos)

    certify_parser = subparsers.add_parser(
        "certify", help="Evaluate release gates against the evidence actually present")
    certify_parser.add_argument("--evidence", required=True, help="Directory holding the evidence artifacts")
    certify_parser.add_argument("--min-calibration-samples", type=int, default=20)
    certify_parser.add_argument("--output")
    certify_parser.add_argument("--schema-dir")
    certify_parser.set_defaults(func=command_certify)

    schema_parser = subparsers.add_parser(
        "validate-schemas", help="Check emitted artifacts in a directory against schemas/")
    schema_parser.add_argument("directory")
    schema_parser.add_argument("--schema-dir")
    schema_parser.set_defaults(func=command_validate_schemas)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (Blocked, StoreUnavailable) as exc:
        print(str(exc) if isinstance(exc, Blocked) else f"BLOCKED — {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
