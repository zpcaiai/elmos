from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto

MAX_REPAIR_ATTEMPTS = 5

class FailureCategory(Enum):
    DEPENDENCY_MISSING = auto()
    API_INCOMPATIBLE = auto()
    TYPE_MISMATCH = auto()
    CONFIG_ERROR = auto()
    COMPILATION_ERROR = auto()
    RUNTIME_ERROR = auto()
    TEST_FAILURE = auto()

class RepairStrategy(Enum):
    ADD_DEPENDENCY = auto()
    APPLY_RECIPE = auto()
    RENAME_SYMBOL = auto()
    UPDATE_CONFIG = auto()
    APPLY_MIGRATION_SHIM = auto()
    MANUAL_REVIEW = auto()

@dataclass(frozen=True)
class RepairResult:
    success: bool
    attempts: int
    final_strategy: str

class BuildFailureDiagnosticClassifier:
    def classify(self, error_log: str) -> FailureCategory:
        if "cannot find symbol" in error_log:
            return FailureCategory.COMPILATION_ERROR
        if "No qualifying bean" in error_log:
            return FailureCategory.CONFIG_ERROR
        return FailureCategory.RUNTIME_ERROR

class RepairStrategyEngine:
    def select_strategy(self, category: FailureCategory) -> RepairStrategy:
        mapping = {
            FailureCategory.COMPILATION_ERROR: RepairStrategy.RENAME_SYMBOL,
            FailureCategory.CONFIG_ERROR: RepairStrategy.UPDATE_CONFIG,
            FailureCategory.DEPENDENCY_MISSING: RepairStrategy.ADD_DEPENDENCY,
        }
        return mapping.get(category, RepairStrategy.MANUAL_REVIEW)

class RepairVerificationLoop:
    def __init__(self):
        self.classifier = BuildFailureDiagnosticClassifier()
        self.engine = RepairStrategyEngine()

    def run(self, error_log: str) -> RepairResult:
        attempts = 0
        while attempts < MAX_REPAIR_ATTEMPTS:
            attempts += 1
            category = self.classifier.classify(error_log)
            strategy = self.engine.select_strategy(category)
            
            if strategy == RepairStrategy.MANUAL_REVIEW:
                return RepairResult(success=False, attempts=attempts, final_strategy=strategy.name)
            
            # Simulate success on 2nd attempt
            if attempts == 2:
                return RepairResult(success=True, attempts=attempts, final_strategy=strategy.name)
                
        return RepairResult(success=False, attempts=attempts, final_strategy="MAX_RETRIES_EXCEEDED")
