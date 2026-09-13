"""Autonomous QA Industrial Subsystems Package.

Authentic domain engines covering:
- Spec normalization (OpenAPI & Gherkin)
- In-Parameter-Order (IPO) pairwise covering array generation
- AST operator mutation testing (AOR, ROR, COR)
- API contract fuzzing and schema verification
- WCAG 2.2 accessibility and contrast ratio evaluation
- Database cryptographic state differential auditing
- Wilson score interval statistical flakiness bisecting
- Chaos fault injection and circuit breaker state machines
- Bidirectional requirement-to-test traceability matrix and gap analysis
- Declarative test DSL lexer, parser, and polyglot target compiler
- Functional BVA, equivalence partitioning, and decision tables
- Distributed event stream ordering, outbox deduplication, and Saga orchestrator
- Page Object Model synthesis and multi-tier resilient UI journey runner
- Visual regression geometry diffing, IoU, and layout shift scoring
- Performance latency percentiles, Little's Law, and soak memory leak OLS regression
- OWASP Top 10 security abuse mutation and input sanitizer auditing
- Relational schema topological DAG dependency solver and PII pseudonymization
- Consistent hash ring test sharding and greedy LPT makespan minimization
"""

from .spec_normalization_engine import SpecNormalizationEngine, CanonicalTestSpec
from .pairwise_combinatorial_engine import PairwiseCombinatorialEngine, CoveringArray
from .ast_mutation_testing_engine import ASTMutationTestingEngine, MutationScoreReport
from .api_contract_testing_engine import APIContractTestingEngine, FuzzPayload
from .wcag_a11y_compliance_engine import WCAGA11yComplianceEngine, ContrastEvaluationResult
from .db_state_verification_engine import DBStateVerificationEngine, TableDifferentialResult
from .flaky_test_bisect_engine import FlakyTestBisectEngine, FlakinessReport
from .chaos_fault_injection_engine import ChaosFaultInjectionEngine, ChaosExperimentResult
from .traceability_matrix_engine import TraceabilityMatrixEngine, TraceNode, TraceEdge, TraceabilityReport
from .test_dsl_compiler import TestDSLCompiler, DSLScenario, DSLStep, DSLAssertion
from .functional_test_engine import FunctionalTestEngine, BVAResult, EquivalencePartition, DecisionRule
from .workflow_message_test_engine import WorkflowMessageTestEngine, MessageEvent, StreamOrderReport, SagaStep, SagaExecutionResult
from .ui_e2e_testing_engine import UIE2ETestingEngine, UIElementSelector, UIJourneyStep, JourneyExecutionReport
from .visual_regression_engine import VisualRegressionEngine, BoundingBox, VisualDiffResult
from .performance_stress_engine import PerformanceStressEngine, LatencyPercentiles, MemoryLeakReport
from .security_abuse_fuzz_engine import SecurityAbuseFuzzEngine, SecurityVulnerabilityReport
from .test_data_synthesis_engine import TestDataSynthesisEngine, ForeignKeyConstraint, TableSchema
from .distributed_runner_engine import DistributedRunnerEngine, ConsistentHashRing, TestJob

__all__ = [
    "SpecNormalizationEngine",
    "CanonicalTestSpec",
    "PairwiseCombinatorialEngine",
    "CoveringArray",
    "ASTMutationTestingEngine",
    "MutationScoreReport",
    "APIContractTestingEngine",
    "FuzzPayload",
    "WCAGA11yComplianceEngine",
    "ContrastEvaluationResult",
    "DBStateVerificationEngine",
    "TableDifferentialResult",
    "FlakyTestBisectEngine",
    "FlakinessReport",
    "ChaosFaultInjectionEngine",
    "ChaosExperimentResult",
    "TraceabilityMatrixEngine",
    "TraceNode",
    "TraceEdge",
    "TraceabilityReport",
    "TestDSLCompiler",
    "DSLScenario",
    "DSLStep",
    "DSLAssertion",
    "FunctionalTestEngine",
    "BVAResult",
    "EquivalencePartition",
    "DecisionRule",
    "WorkflowMessageTestEngine",
    "MessageEvent",
    "StreamOrderReport",
    "SagaStep",
    "SagaExecutionResult",
    "UIE2ETestingEngine",
    "UIElementSelector",
    "UIJourneyStep",
    "JourneyExecutionReport",
    "VisualRegressionEngine",
    "BoundingBox",
    "VisualDiffResult",
    "PerformanceStressEngine",
    "LatencyPercentiles",
    "MemoryLeakReport",
    "SecurityAbuseFuzzEngine",
    "SecurityVulnerabilityReport",
    "TestDataSynthesisEngine",
    "ForeignKeyConstraint",
    "TableSchema",
    "DistributedRunnerEngine",
    "ConsistentHashRing",
    "TestJob",
]
