"""ELMOS Composite Modernization Engine.

System-level orchestration, cross-system dependency analysis,
contract consumer governance, and strangler-fig cutover decision engine.
"""

__version__ = "1.0.0"

from .models import (
    SystemNode,
    DependencyEdge,
    CompatibilityWindow,
    ContractConsumerMatrix,
    CutoverDecision,
    MigrationWave,
)
from .topology import DependencyGraphAnalyzer
from .contract_governance import ContractGovernanceEngine
from .shadow_differential import ShadowTrafficValidator
from .cutover_engine import SystemCutoverOrchestrator
from .wave_planner import MigrationWavePlanner

__all__ = [
    "SystemNode",
    "DependencyEdge",
    "CompatibilityWindow",
    "ContractConsumerMatrix",
    "CutoverDecision",
    "MigrationWave",
    "DependencyGraphAnalyzer",
    "ContractGovernanceEngine",
    "ShadowTrafficValidator",
    "SystemCutoverOrchestrator",
    "MigrationWavePlanner",
]
