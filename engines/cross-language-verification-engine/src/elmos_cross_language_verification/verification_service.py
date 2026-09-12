from __future__ import annotations

import time
import uuid
from typing import Any

from .models import (
    Language,
    LanguagePair,
    VerificationReport,
    ComparisonResult,
    TestSuite,
    TestCase
)
from .executor import ExecutorRegistry
from .comparator import OutputComparator


class VerificationService:
    @classmethod
    def verify_equivalence(
        cls,
        source_code: str,
        target_code: str,
        source_lang: Language,
        target_lang: Language,
        test_suite: TestSuite
    ) -> VerificationReport:
        source_executor = ExecutorRegistry.get_executor(source_lang)
        target_executor = ExecutorRegistry.get_executor(target_lang)

        results = []
        passed = 0
        failed = 0
        
        for case in test_suite.test_cases:
            case.test_id = case.test_id or str(uuid.uuid4())
            
            source_res = source_executor.execute(source_code, case.input_data, case.timeout_seconds)
            source_res.test_id = case.test_id
            
            target_res = target_executor.execute(target_code, case.input_data, case.timeout_seconds)
            target_res.test_id = case.test_id
            
            match = False
            diff_summary = None
            if source_res.success and target_res.success:
                match, diffs = OutputComparator.compare_json(source_res.output_data, target_res.output_data)
                if not match:
                    diff_summary = str(diffs)
            elif source_res.success != target_res.success:
                diff_summary = "Execution success mismatch"

            results.append(ComparisonResult(
                test_id=case.test_id,
                source_result=source_res,
                target_result=target_res,
                match=match,
                diff_summary=diff_summary
            ))
            
            if match:
                passed += 1
            else:
                failed += 1
                
        return VerificationReport(
            suite_id=test_suite.suite_id,
            total=len(test_suite.test_cases),
            passed=passed,
            failed=failed,
            skipped=0,
            results=results,
            summary=f"Passed {passed}/{len(test_suite.test_cases)}",
            timestamp=time.time()
        )

    @classmethod
    def verify_function(
        cls,
        source_func: str,
        target_func: str,
        source_lang: Language,
        target_lang: Language,
        test_cases: list[TestCase]
    ) -> VerificationReport:
        suite = TestSuite(
            suite_id=str(uuid.uuid4()),
            name="function-test",
            source_language=source_lang,
            target_language=target_lang,
            test_cases=test_cases
        )
        return cls.verify_equivalence(source_func, target_func, source_lang, target_lang, suite)

    @classmethod
    def generate_and_verify(
        cls,
        source_code: str,
        target_code: str,
        source_lang: Language,
        target_lang: Language
    ) -> VerificationReport:
        from .test_generator import TestCaseGenerator
        
        # Dummy cases
        inputs = TestCaseGenerator.generate_from_function_signature("foo", {"a": "int"}, "int", source_lang)
        cases = [TestCase(test_id=str(i), name=f"test_{i}", input_data=tc) for i, tc in enumerate(inputs)]
        
        return cls.verify_function(source_code, target_code, source_lang, target_lang, cases)

    @classmethod
    def get_supported_pairs(cls) -> list[LanguagePair]:
        return [
            LanguagePair(Language.JAVA, Language.PYTHON, True),
            LanguagePair(Language.PYTHON, Language.JAVA, True),
            LanguagePair(Language.TYPESCRIPT, Language.PYTHON, True),
        ]
