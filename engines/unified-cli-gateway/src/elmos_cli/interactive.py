"""Interactive REPL Modernizer Wizard for ELMOS Enterprise CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict

from .composite_pipeline import run_composite_pipeline
from .config import load_config
from .formatters import generate_executive_html_report


def run_interactive_wizard() -> int:
    cfg = load_config()
    print("=" * 70)
    print("  ELMOS Enterprise Flagship Modernization Suite · Interactive REPL")
    print("=" * 70)
    print("Welcome to the interactive modernization console.")
    print(f"Active Tenant: {cfg.get('tenant_id')} | Actor: {cfg.get('actor_id')}")
    print("-" * 70)
    print("Select an action:")
    print("  [1] Global System Status & 41-Engine Health")
    print("  [2] Quick Polyglot Code Snippet Transformation")
    print("  [3] SMT Formal Proof Obligations Solver")
    print("  [4] Run Full Composite Modernization Pipeline")
    print("  [5] Export Executive Assurance HTML Report")
    print("  [0] Exit")
    print("-" * 70)

    try:
        choice = input("Enter choice [0-5] (default: 4): ").strip() or "4"
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        return 0

    if choice == "0":
        print("Goodbye.")
        return 0

    if choice == "1":
        from .dispatcher import _get_global_status
        status = _get_global_status()
        print("\n" + json.dumps(status, indent=2, ensure_ascii=False))
        return 0

    if choice == "2":
        src = input(f"Source Language (default: {cfg.get('default_src_lang', 'java')}): ").strip() or cfg.get("default_src_lang", "java")
        tgt = input(f"Target Language (default: {cfg.get('default_tgt_lang', 'csharp')}): ").strip() or cfg.get("default_tgt_lang", "csharp")
        print("\nEnter source code (press Enter then Ctrl+D when finished, or leave empty for sample):")
        try:
            lines = sys.stdin.readlines()
            code = "".join(lines).strip() or "public class SampleOrder { public String id; public double total; }"
        except Exception:
            code = "public class SampleOrder { public String id; public double total; }"

        print(f"\nTransforming {src} -> {tgt}...")
        t0 = time.perf_counter()
        result = run_composite_pipeline(
            project_path=Path.cwd(),
            source_language=src,
            target_language=tgt,
            source_code=code,
            budget_limit_usd=cfg.get("budget_limit_usd", 50.0),
        )
        dur = (time.perf_counter() - t0) * 1000
        print(f"Completed in {dur:.1f}ms! Status: {result.get('status')}")
        print("-" * 70)
        print("Generated Target Code:")
        print(result.get("stages", {}).get("polyglot_transform", {}).get("target_code", ""))
        print("-" * 70)
        return 0

    if choice == "3":
        formula = input("Enter SMT Formula (default: 'forall x: P(x) ==> Q(x)'): ").strip() or "forall x: P(x) ==> Q(x)"
        print("\nSolving SMT proof obligations with Z3/CVC5 solver...")
        from elmos_polyglot_compiler.service import check_smt_formula
        res = check_smt_formula(formula)
        print(json.dumps(res, indent=2))
        return 0

    if choice in ("4", "5"):
        src = cfg.get("default_src_lang", "java")
        tgt = cfg.get("default_tgt_lang", "csharp")
        sample_code = """public class EnterpriseAccount {
    private String accountId;
    private BigDecimal balance;
    public void deposit(BigDecimal amount) {
        if (amount.compareTo(BigDecimal.ZERO) > 0) {
            this.balance = this.balance.add(amount);
        }
    }
}"""
        print(f"\nExecuting End-to-End Modernization Pipeline for {src} -> {tgt}...")
        t0 = time.perf_counter()
        result = run_composite_pipeline(
            project_path=Path.cwd(),
            source_language=src,
            target_language=tgt,
            source_code=sample_code,
            budget_limit_usd=cfg.get("budget_limit_usd", 50.0),
        )
        dur = (time.perf_counter() - t0) * 1000
        print(f"\n[OK] Pipeline finished in {dur:.1f}ms! Status: {result.get('status')}")
        
        report_path = Path("docs/reports/executive_assurance_report.html")
        generate_executive_html_report("Enterprise Account Modernization Dossier", result, report_path)
        print(f"Executive Assurance HTML report exported to: {report_path.resolve()}")
        return 0

    print("Unknown option.")
    return 1
