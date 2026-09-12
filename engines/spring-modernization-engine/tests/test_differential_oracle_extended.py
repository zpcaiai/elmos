from elmos_spring_modernization.differential_oracle import DifferentialOracle, ResponseComparator

def test_comparator():
    comp = ResponseComparator()
    assert comp.compare({"status": 200}, {"status": 200})
    assert not comp.compare({"status": 200}, {"status": 500})

def test_oracle_report():
    oracle = DifferentialOracle()
    report = oracle.run_tests([{"status": 200}])
    assert report.total_requests == 1
    assert report.passed == 1
    assert report.differed == 0
