from etgb.io import iter_cases, package_root
from etgb.runner import run_cases


def test_all_offline_smoke_cases_pass() -> None:
    root = package_root()
    cases = [case for case in iter_cases(root) if "smoke" in case["profiles"]]
    assert len(cases) == 4
    results = run_cases(cases, root)
    assert [r["status"] for r in results] == ["passed"] * 4, results
    assert not any(r["silent_semantic_error"] for r in results)
