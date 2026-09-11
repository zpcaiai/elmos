"""Typed computational families for every Foundry atomic skill.

Classification is deterministic: skill-name tokens first, pack identity second.
Every skill maps to exactly one family that has a real algorithm.
"""

from __future__ import annotations

from enum import StrEnum


class KernelFamily(StrEnum):
    AST_TRANSFORM = "AST_TRANSFORM"
    SQL_DIALECT = "SQL_DIALECT"
    CONCURRENCY_WFG = "CONCURRENCY_WFG"
    SECURITY_SCAN = "SECURITY_SCAN"
    DEPENDENCY_GRAPH = "DEPENDENCY_GRAPH"
    CONTRACT_INFERENCE = "CONTRACT_INFERENCE"
    RETRIEVAL_RANK = "RETRIEVAL_RANK"
    TEST_SYNTHESIS = "TEST_SYNTHESIS"
    GRAPH_REACHABILITY = "GRAPH_REACHABILITY"
    POLICY_EVAL = "POLICY_EVAL"
    COST_ROUTE = "COST_ROUTE"
    LINEAGE_HASH = "LINEAGE_HASH"
    NORMALIZATION = "NORMALIZATION"
    FUZZ_MUTATION = "FUZZ_MUTATION"
    API_CONTRACT = "API_CONTRACT"
    DATAFLOW = "DATAFLOW"
    SCHEDULE_DAG = "SCHEDULE_DAG"
    MEMORY_ISOLATION = "MEMORY_ISOLATION"


_TOKEN_RULES: tuple[tuple[tuple[str, ...], KernelFamily], ...] = (
    (("deadlock", "race", "lock", "concurrent", "mutex", "thread-safe", "wait-for"), KernelFamily.CONCURRENCY_WFG),
    (("sql", "dialect", "plpgsql", "ddl", "dml", "query-plan", "jdbc"), KernelFamily.SQL_DIALECT),
    (("inject", "jailbreak", "secret", "sbom", "cve", "threat", "pii", "oauth", "sast"), KernelFamily.SECURITY_SCAN),
    (("fuzz", "mutat", "metamorphic", "property-based"), KernelFamily.FUZZ_MUTATION),
    (("test", "oracle", "coverage", "qa-", "assert", "tck"), KernelFamily.TEST_SYNTHESIS),
    (("retriev", "rag", "embed", "chunk", "bm25", "re-rank", "rerank", "context-pack"), KernelFamily.RETRIEVAL_RANK),
    (("openapi", "grpc", "protobuf", "webhook", "rest-api", "graphql"), KernelFamily.API_CONTRACT),
    (("dataflow", "taint", "def-use", "reaching"), KernelFamily.DATAFLOW),
    (("schedul", "saga", "lease", "worker-pool", "orchestr", "checkpoint", "queue"), KernelFamily.SCHEDULE_DAG),
    (("memory", "episode", "replay", "isolation", "tenant-memory"), KernelFamily.MEMORY_ISOLATION),
    (("lineage", "provenance", "merkle", "audit-log", "artifact-identity"), KernelFamily.LINEAGE_HASH),
    (("policy", "rbac", "allowlist", "consent", "tenancy", "authorization"), KernelFamily.POLICY_EVAL),
    (("cost", "latency", "finops", "token-budget", "routing"), KernelFamily.COST_ROUTE),
    (("contract", "invariant", "schema", "typed-skill", "precondition"), KernelFamily.CONTRACT_INFERENCE),
    (("dependenc", "sbom", "license", "call-graph", "module-graph"), KernelFamily.DEPENDENCY_GRAPH),
    (("graph", "topology", "scc", "dag"), KernelFamily.GRAPH_REACHABILITY),
    (("normaliz", "canonical", "ingest", "tokenize", "extract"), KernelFamily.NORMALIZATION),
    (("ast", "codemod", "parse", "refactor", "symbol", "ir-", "semantic"), KernelFamily.AST_TRANSFORM),
)

_PACK_FALLBACK: dict[str, KernelFamily] = {
    "00-foundation-contracts": KernelFamily.CONTRACT_INFERENCE,
    "01-knowledge-ingestion-governance": KernelFamily.NORMALIZATION,
    "02-repository-semantic-intelligence": KernelFamily.AST_TRANSFORM,
    "03-retrieval-context-engineering": KernelFamily.RETRIEVAL_RANK,
    "04-memory-experience-flywheel": KernelFamily.MEMORY_ISOLATION,
    "05-skill-foundry-runtime": KernelFamily.SCHEDULE_DAG,
    "06-dataset-foundry": KernelFamily.NORMALIZATION,
    "07-private-model-foundry": KernelFamily.COST_ROUTE,
    "08-agentic-training-rl": KernelFamily.POLICY_EVAL,
    "09-evaluation-proof-certification": KernelFamily.TEST_SYNTHESIS,
    "10-serving-routing-inference": KernelFamily.COST_ROUTE,
    "11-security-privacy-compliance": KernelFamily.SECURITY_SCAN,
    "12-observability-lineage-finops": KernelFamily.LINEAGE_HASH,
    "13-commercial-multitenant-platform": KernelFamily.POLICY_EVAL,
    "14-human-governance-operations": KernelFamily.POLICY_EVAL,
    "15-domain-engineering-packs": KernelFamily.AST_TRANSFORM,
    "16-self-evolution-release-engineering": KernelFamily.SCHEDULE_DAG,
    "17-repository-execution-os": KernelFamily.AST_TRANSFORM,
    "18-java-spring-enterprise-modernization": KernelFamily.AST_TRANSFORM,
    "19-cross-language-semantic-conversion": KernelFamily.AST_TRANSFORM,
    "20-sql-database-modernization": KernelFamily.SQL_DIALECT,
    "21-project-generation-product-engineering": KernelFamily.CONTRACT_INFERENCE,
    "22-frontend-mobile-miniapp-modernization": KernelFamily.AST_TRANSFORM,
    "23-repository-refactoring-technical-debt": KernelFamily.AST_TRANSFORM,
    "24-api-event-integration-modernization": KernelFamily.API_CONTRACT,
    "25-data-engineering-lakehouse-analytics": KernelFamily.DATAFLOW,
    "26-cloud-native-devops-platform-engineering": KernelFamily.SCHEDULE_DAG,
    "27-test-quality-assurance-factory": KernelFamily.TEST_SYNTHESIS,
    "28-security-compliance-supply-chain": KernelFamily.SECURITY_SCAN,
    "29-performance-reliability-cost-engineering": KernelFamily.COST_ROUTE,
    "30-architecture-documentation-ide": KernelFamily.CONTRACT_INFERENCE,
    "31-ai-agent-rag-ml-engineering": KernelFamily.RETRIEVAL_RANK,
    "32-legacy-mainframe-enterprise-modernization": KernelFamily.AST_TRANSFORM,
    "33-industrial-iot-edge-robotics": KernelFamily.GRAPH_REACHABILITY,
    "34-language-runtime-adapters": KernelFamily.AST_TRANSFORM,
    "35-database-engine-adapters": KernelFamily.SQL_DIALECT,
    "36-framework-runtime-adapters": KernelFamily.AST_TRANSFORM,
    "37-cloud-platform-adapters": KernelFamily.SCHEDULE_DAG,
    "38-golden-route-customer-delivery": KernelFamily.CONTRACT_INFERENCE,
    "39-product-commercialization-marketplace": KernelFamily.POLICY_EVAL,
    "40-regulated-industry-assurance": KernelFamily.POLICY_EVAL,
}


def classify_skill(skill_name: str, pack: str = "") -> KernelFamily:
    """Return the unique computational family for a skill."""
    lowered = skill_name.lower()
    for tokens, family in _TOKEN_RULES:
        if any(token in lowered for token in tokens):
            return family
    if pack in _PACK_FALLBACK:
        return _PACK_FALLBACK[pack]
    prefix = pack.split("-", 1)[0] if pack else ""
    for pack_id, family in _PACK_FALLBACK.items():
        if pack_id.startswith(prefix) and prefix:
            return family
    return KernelFamily.NORMALIZATION
