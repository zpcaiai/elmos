"""Core domain models for composite system modernization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SystemNode:
    nodeId: str
    organizationId: str
    nodeType: str  # SERVICE, DATABASE, GATEWAY, BATCH_JOB, MESSAGE_BROKER
    name: str
    language: str
    repositoryId: str
    deployableId: str
    environment: str
    schemaVersion: str = "1.0"
    evidenceRefs: List[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    edgeId: str
    organizationId: str
    sourceNodeId: str
    targetNodeId: str
    edgeType: str  # CALLS_HTTP, CALLS_GRPC, WRITES_DB, READS_DB, PRODUCES_MSG, CONSUMES_MSG
    environment: str
    confidence: float = 1.0
    validity: str = "ACTIVE"
    hardDependency: bool = True
    contractRef: Optional[str] = None
    schemaVersion: str = "1.0"
    evidenceRefs: List[str] = field(default_factory=list)


@dataclass
class CompatibilityWindow:
    windowId: str
    organizationId: str
    contractId: str
    oldVersion: str
    newVersion: str
    startsAt: str
    expiresAt: str
    owner: str
    status: str  # ACTIVE, EXPIRED, EXTENDED, CLOSED
    strategies: List[str] = field(default_factory=list)
    removalTaskId: Optional[str] = None
    oldVersionUsage: int = 0
    schemaVersion: str = "1.0"
    evidenceRefs: List[str] = field(default_factory=list)


@dataclass
class ContractConsumer:
    consumerNodeId: str
    supportedVersion: str
    lastObserved: Optional[str] = None
    trafficSharePct: float = 0.0


@dataclass
class ContractConsumerMatrix:
    contractId: str
    producerNodeId: str
    currentVersion: str
    protocol: str  # HTTP, GRPC, PROTOBUF, MESSAGE_TOPIC
    consumers: List[ContractConsumer] = field(default_factory=list)
    schemaVersion: str = "1.0"


@dataclass
class CutoverDecision:
    cutoverPlanId: str
    organizationId: str
    landscapeId: str
    currentState: str
    requestedState: str
    decision: str  # APPROVED, BLOCKED, ROLLBACK
    humanApprovalRequired: bool
    rollbackClassification: str  # AUTOMATIC_REVERSIBLE, FORWARD_FIX_ONLY, MANUAL_REPLAY
    blockers: List[str] = field(default_factory=list)
    schemaVersion: str = "1.0"
    evidenceRefs: List[str] = field(default_factory=list)


@dataclass
class MigrationWave:
    waveNumber: int
    name: str
    nodes: List[str]
    prerequisiteWaves: List[int] = field(default_factory=list)
    estimatedRisk: str = "LOW"
