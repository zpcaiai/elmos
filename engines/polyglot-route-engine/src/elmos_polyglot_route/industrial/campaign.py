"""210-route industrial campaign: emit, interpret, host-run, fail closed."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from elmos_polyglot_route.industrial.anti_template import emission_is_template, missing_domain_tokens
from elmos_polyglot_route.industrial.concurrency import ConcurrencySemanticEngine
from elmos_polyglot_route.industrial.corpora import IndustrialCorpus, all_corpora
from elmos_polyglot_route.industrial.emitter import emit_industrial_module
from elmos_polyglot_route.industrial.exceptions import ExceptionErrorEngine
from elmos_polyglot_route.industrial.framework import FrameworkSubsetEngine
from elmos_polyglot_route.industrial.host_runner import HostRunError, run_python
from elmos_polyglot_route.industrial.interpreter import IndustrialInterpreter, Observation
from elmos_polyglot_route.industrial.io_ops import SystemIoEngine
from elmos_polyglot_route.industrial.languages import INDUSTRIAL_ROUTE_KEYS
from elmos_polyglot_route.industrial.ownership import OwnershipMemoryEngine


@dataclass
class RouteCorpusResult:
    source: str
    target: str
    corpus_id: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    host_python: bool = False


def lower_industrial(module, source: str, target: str):
    lowered = deepcopy(module)
    lowered.source_language = source
    lowered = OwnershipMemoryEngine.lower_module(lowered, source, target)
    lowered = ConcurrencySemanticEngine.lower_module(lowered, target)
    lowered = ExceptionErrorEngine.lower_module(lowered, target)
    lowered = SystemIoEngine.lower_module(lowered, target)
    lowered = FrameworkSubsetEngine.lower_module(lowered, target)
    return lowered


def _same_observation(left: Observation, right: Observation) -> bool:
    if left.status != right.status:
        return False
    if left.status == "ERROR":
        return True
    return left.value == right.value


def prove_route_corpus(source: str, target: str, corpus: IndustrialCorpus) -> RouteCorpusResult:
    errors: list[str] = []
    oracle = IndustrialInterpreter(corpus.module)
    source_ir = lower_industrial(corpus.module, source, source)
    target_ir = lower_industrial(corpus.module, source, target)
    try:
        source_code = emit_industrial_module(source_ir, source)
        target_code = emit_industrial_module(target_ir, target)
    except Exception as exc:  # noqa: BLE001
        return RouteCorpusResult(source, target, corpus.corpus_id, False, [f"emit:{exc}"])

    for label, code, lang in (("source", source_code, source), ("target", target_code, target)):
        templates = emission_is_template(code)
        if templates:
            errors.append(f"{label}-template:{templates[0]}")
        missing = missing_domain_tokens(code, lang, corpus.domain, corpus.corpus_id)
        if missing:
            errors.append(f"{label}-tokens:{missing[0]}")

    host_python = False
    for case in corpus.cases:
        expected = oracle.invoke(corpus.entrypoint, case.args)
        if case.expect_error:
            if expected.status != "ERROR":
                errors.append(f"oracle-missed-error:{case.args}")
                continue
        elif expected.status != "RETURNED" or expected.value != case.expected:
            errors.append(f"oracle:{case.args}:got={expected.value}:want={case.expected}")
            continue
        source_obs = IndustrialInterpreter(source_ir).invoke(corpus.entrypoint, case.args)
        target_obs = IndustrialInterpreter(target_ir).invoke(corpus.entrypoint, case.args)
        if not _same_observation(expected, source_obs):
            errors.append(f"source-ir:{source}:{case.args}:{source_obs}")
        if not _same_observation(expected, target_obs):
            errors.append(f"target-ir:{target}:{case.args}:{target_obs}")
        if target == "python":
            try:
                got = run_python(target_code, corpus.entrypoint, case.args)
                if expected.status == "RETURNED" and got != expected.value:
                    errors.append(f"python-host:{case.args}:got={got}:want={expected.value}")
                host_python = True
            except Exception as exc:  # noqa: BLE001
                if expected.status == "ERROR":
                    host_python = True
                else:
                    errors.append(f"python-host-exc:{exc}")
        if source == "python" and target != "python":
            try:
                got = run_python(source_code, corpus.entrypoint, case.args)
                if expected.status == "RETURNED" and got != expected.value:
                    errors.append(f"python-source-host:{case.args}:got={got}")
                host_python = True
            except HostRunError as exc:
                errors.append(f"python-source-host-exc:{exc}")
            except Exception as exc:  # noqa: BLE001
                if expected.status != "ERROR":
                    errors.append(f"python-source-host-exc:{exc}")

    return RouteCorpusResult(
        source=source,
        target=target,
        corpus_id=corpus.corpus_id,
        passed=not errors,
        errors=errors,
        host_python=host_python,
    )


def run_industrial_campaign(limit_routes: int | None = None) -> dict[str, Any]:
    corpora = all_corpora()
    routes = INDUSTRIAL_ROUTE_KEYS if limit_routes is None else INDUSTRIAL_ROUTE_KEYS[:limit_routes]
    results: list[RouteCorpusResult] = []
    for source, target in routes:
        for corpus in corpora:
            results.append(prove_route_corpus(source, target, corpus))
    passed = [item for item in results if item.passed]
    failed = [item for item in results if not item.passed]
    host_runs = sum(1 for item in results if item.host_python)
    return {
        "route_count": len(routes),
        "corpus_count": len(corpora),
        "pairs_total": len(results),
        "pairs_passed": len(passed),
        "pairs_failed": len(failed),
        "host_python_runs": host_runs,
        "failures": [
            {
                "source": item.source,
                "target": item.target,
                "corpus_id": item.corpus_id,
                "errors": item.errors[:4],
            }
            for item in failed[:20]
        ],
    }
