from elmos_spring_modernization.repair_agent import (
    BuildFailureDiagnosticClassifier,
    FailureCategory,
    RepairVerificationLoop
)

def test_classifier():
    classifier = BuildFailureDiagnosticClassifier()
    assert classifier.classify("error: cannot find symbol: class User") == FailureCategory.COMPILATION_ERROR
    assert classifier.classify("[ERROR] package jakarta.validation.constraints does not exist") == FailureCategory.DEPENDENCY_MISSING
    assert classifier.classify("No qualifying bean of type 'UserService' available") == FailureCategory.CONFIG_ERROR
    assert classifier.classify("incompatible types: String cannot be converted to Long") == FailureCategory.TYPE_MISMATCH
    assert classifier.classify("org.opentest4j.AssertionFailedError: expected: <1> but was: <2>") == FailureCategory.TEST_FAILURE
    assert classifier.classify("java.lang.NoSuchMethodError: org.springframework.util.Assert") == FailureCategory.RUNTIME_ERROR

def test_repair_loop_single_step_real_transform():
    loop = RepairVerificationLoop()
    code = "User u = userRepository.getOne(userId);"
    res = loop.run("cannot find symbol: method getOne(Long)", source_code=code)
    assert res.success is False
    assert res.attempts == 1
    assert "getReferenceById" in res.repaired_content
    assert "getOne" not in res.repaired_content
    assert "RULE_JPA_GET_ONE_TO_REFERENCE" in res.applied_patches
    assert res.final_strategy == "VERIFICATION_REQUIRED"

def test_repair_loop_multi_step_verification():
    loop = RepairVerificationLoop()
    initial_code = (
        "import javax.persistence.Entity;\n"
        "public class SecConfig extends WebSecurityConfigurerAdapter {}\n"
    )

    def verifier(code: str):
        # Step 1 fails if javax.persistence remains
        if "javax.persistence" in code:
            return False, "package javax.persistence does not exist"
        # Step 2 fails if WebSecurityConfigurerAdapter remains
        if "WebSecurityConfigurerAdapter" in code:
            return False, "cannot find symbol: class WebSecurityConfigurerAdapter"
        return True, ""

    res = loop.run(
        error_log="package javax.persistence does not exist",
        source_code=initial_code,
        verifier=verifier
    )

    assert res.success is True
    assert res.attempts == 2
    assert "jakarta.persistence" in res.repaired_content
    assert "WebSecurityConfigurerAdapter" not in res.repaired_content
    assert len(res.applied_patches) == 2

def test_repair_loop_manual():
    loop = RepairVerificationLoop()
    res = loop.run("completely unknown proprietary compiler crash 0xDEADBEEF")
    assert res.success is False
    assert res.attempts == 1
    assert res.final_strategy == "MANUAL_REVIEW"

def test_repair_loop_does_not_claim_resolution_without_code_or_verifier():
    loop = RepairVerificationLoop()
    res = loop.run("cannot find symbol: class LegacyType")
    assert res.success is False
    assert res.final_strategy == "EVIDENCE_REQUIRED"
    assert res.applied_patches == []
