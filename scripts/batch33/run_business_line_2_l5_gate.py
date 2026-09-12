#!/usr/bin/env python3
"""Industrial L5 gate for Business Line 2: cross-language 210 routes.

Phases:
1. Anti-template / anti-string-audit
2. Required industrial architecture
3. Five corpora oracle
4. 210-route industrial campaign
5. Python host execution
6. Honest metric == 100
7. Merkle seal
8. Dossier issuance
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = REPO_ROOT / "engines" / "polyglot-route-engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_route.industrial.anti_template import FORBIDDEN_AUDIT_SNIPPETS, scan_path_for_templates
from elmos_polyglot_route.industrial.campaign import run_industrial_campaign
from elmos_polyglot_route.industrial.corpora import all_corpora
from elmos_polyglot_route.industrial.emitter import emit_industrial_module
from elmos_polyglot_route.industrial.host_runner import run_python
from elmos_polyglot_route.industrial.interpreter import IndustrialInterpreter
from elmos_polyglot_route.industrial.metric import industrial_quality_percent


@dataclass
class PhaseResult:
    phase_number: int
    name: str
    passed: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"EMPTY_MERKLE_TREE").hexdigest()
    current = sorted(hashes)
    while len(current) > 1:
        nxt: list[str] = []
        for i in range(0, len(current), 2):
            pair = current[i] + (current[i + 1] if i + 1 < len(current) else current[i])
            nxt.append(hashlib.sha256(pair.encode("utf-8")).hexdigest())
        current = nxt
    return current[0]


class BusinessLine2L5Gate:
    def __init__(self) -> None:
        self.phases: list[PhaseResult] = []
        self.digests: dict[str, str] = {}
        self.campaign: dict[str, Any] = {}
        self.quality = 0.0

    def _record(self, result: PhaseResult) -> PhaseResult:
        self.phases.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] Phase {result.phase_number}: {result.name} ({result.duration_ms:.1f}ms)")
        for error in result.errors[:5]:
            print(f"        {error}")
        return result

    def phase_1_anti_template(self) -> PhaseResult:
        t0 = time.perf_counter()
        errors: list[str] = []
        emitter_dir = ENGINE_SRC / "elmos_polyglot_route" / "ast_compiler" / "emitters"
        for path in emitter_dir.glob("*.py"):
            hits = scan_path_for_templates(path)
            if hits:
                errors.append(f"{path.name}:{hits[0]}")
            self.digests[str(path.relative_to(REPO_ROOT))] = sha256_file(path)
        audit = REPO_ROOT / "scripts" / "operations" / "run_polyglot_enterprise_audit.py"
        text = audit.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_AUDIT_SNIPPETS:
            if snippet in text:
                errors.append(f"audit-still-string-only:{snippet}")
        if 'assert "Asset" in transpiled' in text or "len(transpiled) > 100" in text:
            errors.append("enterprise audit still uses string-length/Asset checks")
        return self._record(PhaseResult(
            1, "Anti-template and anti-string-audit", not errors,
            (time.perf_counter() - t0) * 1000, {"files": len(self.digests)}, errors,
        ))

    def phase_2_architecture(self) -> PhaseResult:
        t0 = time.perf_counter()
        errors: list[str] = []
        required = [
            ENGINE_SRC / "elmos_polyglot_route" / "industrial" / name
            for name in (
                "concurrency.py", "ownership.py", "io_ops.py", "exceptions.py",
                "framework.py", "interpreter.py", "emitter.py", "corpora.py",
                "campaign.py", "metric.py", "host_runner.py", "anti_template.py",
            )
        ]
        missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.exists()]
        if missing:
            errors.append(f"missing:{missing}")
        for path in required:
            if path.exists():
                self.digests[str(path.relative_to(REPO_ROOT))] = sha256_file(path)
        return self._record(PhaseResult(
            2, "Industrial architecture", not errors,
            (time.perf_counter() - t0) * 1000, {"required": len(required)}, errors,
        ))

    def phase_3_oracle(self) -> PhaseResult:
        t0 = time.perf_counter()
        errors: list[str] = []
        for corpus in all_corpora():
            interp = IndustrialInterpreter(corpus.module)
            for case in corpus.cases:
                obs = interp.invoke(corpus.entrypoint, case.args)
                if obs.status != "RETURNED" or obs.value != case.expected:
                    errors.append(f"{corpus.corpus_id}:{case.args}:{obs.value}")
        return self._record(PhaseResult(
            3, "Five-corpus IR oracle", not errors,
            (time.perf_counter() - t0) * 1000, {"corpora": 5}, errors,
        ))

    def phase_4_campaign(self) -> PhaseResult:
        t0 = time.perf_counter()
        self.campaign = run_industrial_campaign()
        errors = []
        if self.campaign["route_count"] != 210:
            errors.append(f"routes={self.campaign['route_count']}")
        if self.campaign["pairs_total"] != 1050:
            errors.append(f"pairs={self.campaign['pairs_total']}")
        if self.campaign["pairs_failed"]:
            errors.append(f"failed={self.campaign['pairs_failed']}")
            errors.extend(str(item) for item in self.campaign["failures"][:5])
        return self._record(PhaseResult(
            4, "210-route industrial campaign", not errors,
            (time.perf_counter() - t0) * 1000, self.campaign, errors,
        ))

    def phase_5_python_host(self) -> PhaseResult:
        t0 = time.perf_counter()
        errors: list[str] = []
        runs = 0
        for corpus in all_corpora():
            source = emit_industrial_module(corpus.module, "python")
            for case in corpus.cases:
                got = run_python(source, corpus.entrypoint, case.args)
                runs += 1
                if got != case.expected:
                    errors.append(f"{corpus.corpus_id}:{case.args}:{got}")
        if self.campaign.get("host_python_runs", 0) < 14:
            errors.append(f"campaign host_python_runs={self.campaign.get('host_python_runs')}")
        return self._record(PhaseResult(
            5, "Python host compile-run", not errors,
            (time.perf_counter() - t0) * 1000, {"runs": runs}, errors,
        ))

    def phase_6_metric(self) -> PhaseResult:
        t0 = time.perf_counter()
        self.quality = industrial_quality_percent(self.campaign)
        errors = []
        if self.quality != 100.0:
            errors.append(f"industrial_quality_percent={self.quality}")
        return self._record(PhaseResult(
            6, "Honest industrial quality metric", not errors,
            (time.perf_counter() - t0) * 1000, {"industrial_quality_percent": self.quality}, errors,
        ))

    def phase_7_merkle(self) -> PhaseResult:
        t0 = time.perf_counter()
        root = merkle_root(list(self.digests.values()))
        return self._record(PhaseResult(
            7, "Merkle seal", True,
            (time.perf_counter() - t0) * 1000,
            {"merkle_root": root, "leaf_count": len(self.digests)},
            [],
        ))

    def phase_8_dossier(self) -> PhaseResult:
        t0 = time.perf_counter()
        passed = all(phase.passed for phase in self.phases)
        merkle = next(phase.details["merkle_root"] for phase in self.phases if phase.phase_number == 7)
        dossier = {
            "schema_version": 1,
            "business_line": 2,
            "title": "Cross-language 210-route industrial L5 certification",
            "issued_at": datetime.now(UTC).isoformat(),
            "decision": "CERTIFIED_L5_AUTONOMOUS" if passed else "FAILED_REJECTED",
            "autonomy_level": "L5_AUTONOMOUS_ZERO_HUMAN",
            "industrial_quality_percent": self.quality,
            "route_count": 210,
            "corpus_count": 5,
            "pairs_passed": self.campaign.get("pairs_passed"),
            "pairs_total": self.campaign.get("pairs_total"),
            "host_python_runs": self.campaign.get("host_python_runs"),
            "merkle_root": merkle,
            "phases": [asdict(phase) for phase in self.phases],
            "human_review_backlog_count": 0 if passed else len([p for p in self.phases if not p.passed]),
        }
        out = REPO_ROOT / "certification" / "reports" / "business-line-2-polyglot-210-l5-certification.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dossier, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt = {
            "industrial_quality_percent": self.quality,
            "decision": dossier["decision"],
            "merkle_root": merkle,
            "campaign": {
                "pairs_passed": self.campaign.get("pairs_passed"),
                "pairs_total": self.campaign.get("pairs_total"),
            },
        }
        receipt_path = REPO_ROOT / "certification" / "reports" / "polyglot-210-industrial-evaluation-receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors = [] if passed else ["prior phases failed"]
        return self._record(PhaseResult(
            8, "Dossier issuance", passed,
            (time.perf_counter() - t0) * 1000,
            {"dossier": str(out.relative_to(REPO_ROOT))},
            errors,
        ))

    def run(self) -> int:
        print("ELMOS Business Line 2 L5 Industrial Gate")
        self.phase_1_anti_template()
        self.phase_2_architecture()
        self.phase_3_oracle()
        self.phase_4_campaign()
        self.phase_5_python_host()
        self.phase_6_metric()
        self.phase_7_merkle()
        self.phase_8_dossier()
        passed = all(phase.passed for phase in self.phases)
        print(f"Decision: {'CERTIFIED_L5_AUTONOMOUS' if passed else 'FAILED'} quality={self.quality}")
        return 0 if passed else 1


def main() -> int:
    argparse.ArgumentParser(description="Business line 2 L5 gate").parse_args()
    return BusinessLine2L5Gate().run()


if __name__ == "__main__":
    sys.exit(main())
