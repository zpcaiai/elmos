import pytest

from elmos_spring_modernization.differential_oracle import DifferentialOracle, ResponseComparator

def test_comparator():
    comp = ResponseComparator()
    assert comp.compare({"status": 200}, {"status": 200})
    assert not comp.compare({"status": 200}, {"status": 500})

def test_oracle_report():
    oracle = DifferentialOracle()
    with pytest.raises(RuntimeError, match="endpoints are required"):
        oracle.run_tests([{"path": "/health"}])


def test_oracle_rejects_empty_corpus():
    oracle = DifferentialOracle(executor=lambda _role, _request: {"status": 200})
    with pytest.raises(ValueError, match="At least one"):
        oracle.run_tests([])
