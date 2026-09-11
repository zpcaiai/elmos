from elmos_spring_modernization.repair_agent import BuildFailureDiagnosticClassifier, FailureCategory, RepairVerificationLoop

def test_classifier():
    classifier = BuildFailureDiagnosticClassifier()
    cat = classifier.classify("error: cannot find symbol")
    assert cat == FailureCategory.COMPILATION_ERROR

def test_repair_loop():
    loop = RepairVerificationLoop()
    res = loop.run("error: cannot find symbol")
    # Our mock mock succeeds on attempt 2
    assert res.success == True
    assert res.attempts == 2

def test_repair_loop_manual():
    loop = RepairVerificationLoop()
    res = loop.run("unknown error")
    assert res.success == False
    assert res.attempts == 1
    assert res.final_strategy == "MANUAL_REVIEW"
