"""Industrial 210-route quality: interpret, emit, host-run, anti-template."""

from __future__ import annotations

from pathlib import Path

from elmos_polyglot_route.industrial.anti_template import emission_is_template, scan_path_for_templates
from elmos_polyglot_route.industrial.campaign import prove_route_corpus, run_industrial_campaign
from elmos_polyglot_route.industrial.corpora import all_corpora
from elmos_polyglot_route.industrial.emitter import emit_industrial_module
from elmos_polyglot_route.industrial.host_runner import run_python
from elmos_polyglot_route.industrial.interpreter import IndustrialInterpreter
from elmos_polyglot_route.industrial.languages import INDUSTRIAL_LANGUAGES, INDUSTRIAL_ROUTE_KEYS
from elmos_polyglot_route.industrial.metric import industrial_quality_percent


def test_matrix_shape() -> None:
    assert len(INDUSTRIAL_LANGUAGES) == 15
    assert len(INDUSTRIAL_ROUTE_KEYS) == 210


def test_oracle_matches_all_corpora() -> None:
    for corpus in all_corpora():
        interp = IndustrialInterpreter(corpus.module)
        for case in corpus.cases:
            obs = interp.invoke(corpus.entrypoint, case.args)
            assert obs.status == "RETURNED", (corpus.corpus_id, case, obs)
            assert obs.value == case.expected, (corpus.corpus_id, case, obs)


def test_python_host_runs_all_corpora() -> None:
    for corpus in all_corpora():
        source = emit_industrial_module(corpus.module, "python")
        assert not emission_is_template(source)
        for case in corpus.cases:
            got = run_python(source, corpus.entrypoint, case.args)
            assert got == case.expected, (corpus.corpus_id, case, got)


def test_emitters_have_no_asset_templates() -> None:
    emitter_dir = Path(__file__).resolve().parents[1] / "src" / "elmos_polyglot_route" / "ast_compiler" / "emitters"
    for path in emitter_dir.glob("*.py"):
        assert not scan_path_for_templates(path), path


def test_sample_routes_across_domains() -> None:
    sample = (
        ("go", "java"),
        ("java", "python"),
        ("python", "rust"),
        ("rust", "go"),
        ("csharp", "typescript"),
        ("vb6", "python"),
        ("cpp", "swift"),
    )
    for source, target in sample:
        for corpus in all_corpora():
            result = prove_route_corpus(source, target, corpus)
            assert result.passed, (source, target, corpus.corpus_id, result.errors)


def test_full_210_campaign_is_one_hundred_percent() -> None:
    campaign = run_industrial_campaign()
    quality = industrial_quality_percent(campaign)
    assert campaign["pairs_total"] == 210 * 5
    assert campaign["pairs_failed"] == 0, campaign["failures"][:8]
    assert quality == 100.0, (quality, campaign["failures"][:8])
