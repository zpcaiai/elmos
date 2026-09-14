from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Optional

from .models import SpringVersion
from .project_scanner import SpringProjectScanner
from .plan_generator import MigrationPlanGenerator
from .rule_engine import RuleEngine
from .differential_oracle import DifferentialOracle

def _parse_target_version(target_str: Optional[str]) -> SpringVersion:
    if not target_str:
        return SpringVersion.BOOT_3_2
    cleaned = target_str.strip().lower().replace("boot-", "").replace("boot_", "").replace("boot", "")
    mapping = {
        "1.5": SpringVersion.BOOT_1_5,
        "2.0": SpringVersion.BOOT_2_0,
        "2.7": SpringVersion.BOOT_2_7,
        "3.0": SpringVersion.BOOT_3_0,
        "3.2": SpringVersion.BOOT_3_2,
        "3.5": SpringVersion.BOOT_3_5,
        "4.0": SpringVersion.BOOT_4_0,
    }
    return mapping.get(cleaned, SpringVersion.BOOT_3_2)

def main(args_list: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Spring Modernization Engine CLI")
    parser.add_argument("command", choices=["scan", "plan", "apply", "verify", "report"])
    parser.add_argument("--project", default=".", help="Project directory")
    parser.add_argument("--target", default="3.2", help="Target Spring Boot version")
    parser.add_argument("--plan", help="Migration plan file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--results", help="Results file")
    parser.add_argument("--requests", help="JSON request corpus for differential verification")
    parser.add_argument("--source-url", help="Running source application base URL")
    parser.add_argument("--target-url", help="Running target application base URL")
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")

    args = parser.parse_args(args_list)
    project_dir = str(Path(args.project).resolve())
    target_version = _parse_target_version(args.target)

    output_data: dict[str, Any] = {"command": args.command, "status": "SUCCESS"}

    if args.command == "scan":
        scanner = SpringProjectScanner()
        profile = scanner.scan(project_dir)
        output_data["profile"] = {
            "version": profile.version.value,
            "security_mode": profile.security_mode,
            "data_access_type": profile.data_access_type,
            "config_format": profile.config_format,
            "modules": profile.modules,
            "dependencies_count": len(profile.dependencies),
            "dependencies": profile.dependencies
        }

    elif args.command == "plan":
        scanner = SpringProjectScanner()
        profile = scanner.scan(project_dir)
        generator = MigrationPlanGenerator()
        plan = generator.generate_plan(profile, target_version)
        blockers = generator.identify_blocking_issues(plan, profile)
        effort = generator.estimate_effort(plan)
        waves = generator.generate_migration_waves(plan)

        output_data["plan"] = {
            "plan_id": plan.plan_id,
            "source_version": plan.source_version.value,
            "target_version": plan.target_version.value,
            "rule_count": len(plan.rules),
            "rules": [r.rule_id for r in plan.rules],
            "estimated_changes": plan.estimated_changes,
            "effort_estimate_sp": effort,
            "risk_summary": {k.value: v for k, v in plan.risk_summary.items()},
            "blocking_issues": blockers,
            "wave_count": len(waves),
            "waves": [[r.rule_id for r in wave] for wave in waves]
        }

        if args.plan:
            Path(args.plan).write_text(json.dumps(output_data["plan"], indent=2), encoding="utf-8")

    elif args.command == "apply":
        scanner = SpringProjectScanner()
        profile = scanner.scan(project_dir)
        generator = MigrationPlanGenerator()
        plan = generator.generate_plan(profile, target_version)
        engine = RuleEngine()
        result = engine.apply_plan(project_dir, plan, dry_run=args.dry_run)

        output_data["apply_result"] = {
            "plan_id": result.plan_id,
            "applied_rules": result.applied_rules,
            "skipped_rules": result.skipped_rules,
            "failed_rules": result.failed_rules,
            "files_modified": len(result.file_changes),
            "warnings": result.warnings,
            "dry_run": args.dry_run
        }

    elif args.command == "verify":
        if not args.requests or not args.source_url or not args.target_url:
            parser.error("verify requires --requests, --source-url, and --target-url")
        if args.source_url == args.target_url:
            parser.error("verify requires distinct source and target URLs")
        if args.request_timeout <= 0:
            parser.error("--request-timeout must be positive")
        try:
            request_data = json.loads(Path(args.requests).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"unable to load request corpus: {exc}")
        if not isinstance(request_data, list) or not request_data:
            parser.error("request corpus must be a non-empty JSON array")
        if not all(isinstance(item, dict) for item in request_data):
            parser.error("every request corpus entry must be a JSON object")
        oracle = DifferentialOracle()
        oracle.config.request_timeout_seconds = args.request_timeout
        report = oracle.run_tests(
            request_data,
            source_base_url=args.source_url,
            target_base_url=args.target_url,
        )
        output_data["status"] = "FAILED" if report.failed or report.differed else "SUCCESS"
        output_data["verification_report"] = {
            "total_requests": report.total_requests,
            "passed": report.passed,
            "failed": report.failed,
            "differed": report.differed,
            "details": report.details
        }

    elif args.command == "report":
        scanner = SpringProjectScanner()
        profile = scanner.scan(project_dir)
        generator = MigrationPlanGenerator()
        plan = generator.generate_plan(profile, target_version)
        blockers = generator.identify_blocking_issues(plan, profile)

        output_data["modernization_report"] = {
            "project_directory": project_dir,
            "current_version": profile.version.value,
            "target_version": target_version.value,
            "recommended_rules": [r.rule_id for r in plan.rules],
            "estimated_effort_sp": generator.estimate_effort(plan),
            "blockers": blockers
        }

    if args.results:
        Path(args.results).write_text(json.dumps(output_data, indent=2), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(output_data, indent=2))
    else:
        print(f"Executed {args.command}")
        print(f"Status: {output_data['status']}")

    print(f"Executed {args.command}")

if __name__ == "__main__":
    main()
