from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .models import SpringVersion, MigrationPlan, SpringProjectProfile
from .project_scanner import SpringProjectScanner
from .plan_generator import MigrationPlanGenerator
from .rule_engine import RuleEngine
from .differential_oracle import DifferentialOracle
from .repair_agent import RepairVerificationLoop

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
    parser.add_argument("command", choices=["scan", "plan", "apply", "verify", "report", "compare-db"])
    parser.add_argument("--project", default=".", help="Project directory")
    parser.add_argument("--target", default="3.2", help="Target Spring Boot version")
    parser.add_argument("--plan", help="Migration plan file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--results", help="Results file")
    parser.add_argument("--baseline-db", help="Baseline DB dataset JSON file path")
    parser.add_argument("--shadow-db", help="Shadow DB dataset JSON file path")
    parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format")

    args = parser.parse_args(args_list)
    project_dir = str(Path(args.project).resolve())
    target_version = _parse_target_version(args.target)

    output_data = {"command": args.command, "status": "SUCCESS"}

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
        oracle = DifferentialOracle()
        report = oracle.run_tests([])
        output_data["verification_report"] = {
            "total_requests": report.total_requests,
            "passed": report.passed,
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

    elif args.command == "compare-db":
        from .spring_database_state_comparator import SpringDatabaseStateComparator
        dataset: dict[str, Any] = {}
        if args.baseline_db and Path(args.baseline_db).is_file():
            b_data = json.loads(Path(args.baseline_db).read_text(encoding="utf-8"))
            dataset = b_data.get("tables", b_data)
        report = SpringDatabaseStateComparator.generate_report(
            baseline_db="baseline_primary",
            shadow_db="shadow_secondary",
            dataset=dataset
        )
        output_data["database_state_report"] = report.to_dict()

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
