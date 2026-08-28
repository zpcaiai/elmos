from etgb.io import package_root
from etgb.scoring import score_results


def test_score_perfect_smoke() -> None:
    root = package_root()
    results = [{
        "status": "passed", "business_line": "spring-modernization", "priority": "P0",
        "oracle_results": [{"passed": True}], "silent_semantic_error": False,
        "evidence": {"environment": {}, "adapter": "x"}
    }]
    score = score_results(results, root)
    assert score["metrics"]["weighted_pass_rate"] == 1.0
    assert score["metrics"]["silent_semantic_error_rate"] == 0.0
