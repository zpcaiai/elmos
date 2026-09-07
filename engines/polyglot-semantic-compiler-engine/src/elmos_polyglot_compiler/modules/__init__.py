"""18 Layer Modules for Polyglot Repository Semantic Compiler Engine (Batches A-R)."""

from .discovery_ingestion import DiscoveryIngestionModule
from .ir_normalization import IrNormalizationModule
from .adapters_frontends import AdaptersFrontendsModule
from .core_transformation import CoreTransformationModule
from .systems_ui_transformation import SystemsUiTransformationModule
from .database_data_transformation import DatabaseDataTransformationModule
from .integration_specialized_transformation import IntegrationSpecializedTransformationModule
from .verification_testing import VerificationTestingModule
from .delivery_orchestration import DeliveryOrchestrationModule
from .frontend_syntax_semantics import FrontendSyntaxSemanticsModule
from .type_contract_semantics import TypeContractSemanticsModule
from .control_dataflow_semantics import ControlDataflowSemanticsModule
from .runtime_memory_concurrency import RuntimeMemoryConcurrencyModule
from .observable_behavior_oracle import ObservableBehaviorOracleModule
from .corpus_governance import CorpusGovernanceModule
from .native_runtime_lab import NativeRuntimeLabModule
from .formal_assurance import FormalAssuranceModule
from .semantic_fuzzing import SemanticFuzzingModule

__all__ = [
    "DiscoveryIngestionModule",
    "IrNormalizationModule",
    "AdaptersFrontendsModule",
    "CoreTransformationModule",
    "SystemsUiTransformationModule",
    "DatabaseDataTransformationModule",
    "IntegrationSpecializedTransformationModule",
    "VerificationTestingModule",
    "DeliveryOrchestrationModule",
    "FrontendSyntaxSemanticsModule",
    "TypeContractSemanticsModule",
    "ControlDataflowSemanticsModule",
    "RuntimeMemoryConcurrencyModule",
    "ObservableBehaviorOracleModule",
    "CorpusGovernanceModule",
    "NativeRuntimeLabModule",
    "FormalAssuranceModule",
    "SemanticFuzzingModule",
]
