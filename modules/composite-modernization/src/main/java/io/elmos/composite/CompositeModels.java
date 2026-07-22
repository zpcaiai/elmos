package io.elmos.composite;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class CompositeModels {
    private CompositeModels() {}

    public enum Language { JAVA, DOTNET, PYTHON, FRONTEND_CLIENT, MULTI_LANGUAGE, NONE, UNKNOWN }
    public enum NodeType {
        ORGANIZATION, BUSINESS_DOMAIN, BUSINESS_CAPABILITY, REPOSITORY, BUILD_ARTIFACT, DEPLOYABLE,
        SERVICE, WEB_APPLICATION, BATCH_JOB, SCHEDULED_TASK, MESSAGE_PROCESSOR, MODEL_ENDPOINT,
        DATABASE, SCHEMA, TABLE, FILE_EXCHANGE, EXTERNAL_SYSTEM, USER_INTERFACE,
        CLIENT_APPLICATION, CLIENT_ROUTE, BFF, DESIGN_SYSTEM
    }
    public enum EdgeType {
        CALLS_HTTP, CALLS_GRPC, CALLS_SOAP, PUBLISHES_MESSAGE, CONSUMES_MESSAGE, READS_DATABASE,
        WRITES_DATABASE, SHARES_DATABASE, READS_FILE, WRITES_FILE, INVOKES_MODEL, USES_PACKAGE,
        DEPLOYS_WITH, AUTHENTICATES_VIA, TRIGGERS, SCHEDULES, ROUTES_TO, SHADOWS, REPLICATES_TO,
        RENDERS_COMPONENT, CALLS_BFF, USES_DESIGN_SYSTEM
    }
    public enum EvidenceSource {
        DECLARED_CONTRACT, STATIC_SOURCE, BUILD_DEPENDENCY, DEPLOYMENT_CONFIG, GATEWAY_CONFIG,
        SERVICE_MESH, RUNTIME_TRACE, BROKER_METADATA, DATABASE_AUDIT, LOG_CORRELATION,
        CUSTOMER_DECLARATION
    }
    public enum EdgeValidity { ACTIVE, DORMANT, HISTORICAL, SUSPECTED, STALE, UNVERIFIED }
    public enum CompositeState {
        DISCOVERY, LANDSCAPE_BUILDING, CONTRACT_BASELINING, MIGRATION_ORDERING,
        COMPATIBILITY_PREPARING, PARALLEL_RUNTIME, SHADOW_VALIDATING, DATA_SYNCHRONIZING,
        READ_CUTOVER, WRITE_CUTOVER, FULL_TRAFFIC, STABILITY_HOLD, LEGACY_READ_ONLY,
        DECOMMISSION_READY, DECOMMISSIONED, LANDSCAPE_INCOMPLETE, UNKNOWN_CONSUMER_BLOCKER,
        CONTRACT_BREAKING, COMPATIBILITY_WINDOW_EXPIRED, CDC_LAG_EXCEEDED,
        DATA_RECONCILIATION_FAILED, SHADOW_DIFFERENCE_EXCEEDED, CANARY_SLO_FAILED,
        WRITE_OWNERSHIP_CONFLICT, CUTOVER_PAUSED, ROLLBACK_REQUIRED, ROLLBACK_BLOCKED,
        LEGACY_DECOMMISSION_BLOCKED
    }
    public enum OwnershipState {
        LEGACY_AUTHORITATIVE, LEGACY_WRITE_NEW_SHADOW, LEGACY_WRITE_NEW_REPLICA,
        DUAL_WRITE_LEGACY_AUTH, DUAL_WRITE_NEW_AUTH, NEW_WRITE_LEGACY_REPLICA,
        NEW_AUTHORITATIVE, LEGACY_READ_ONLY, DECOMMISSIONED
    }
    public enum ShadowStatus {
        EXACT_MATCH, SEMANTIC_MATCH, WITHIN_TOLERANCE, EXPECTED_DIFFERENCE, REGRESSION,
        NOT_COMPARABLE, SHADOW_EXECUTION_FAILED
    }
    public enum TrafficDecision { PROMOTE, HOLD, PAUSE, ROLLBACK, HUMAN_REVIEW }
    public enum ConsistencyStatus {
        CONSISTENT, EVENTUALLY_CONSISTENT, CONSISTENT_AFTER_REPAIR, BUSINESS_INVARIANT_FAILED,
        MESSAGE_INCOMPLETE, DATA_INCOMPLETE, INCONCLUSIVE
    }
    public enum RollbackClassification {
        REVERSIBLE, REVERSIBLE_WITH_DATA_REPAIR, FORWARD_FIX_ONLY, IRREVERSIBLE
    }

    public record SystemNode(
            String nodeId, String organizationId, NodeType nodeType, String name, Language language,
            String repositoryId, String deployableId, String environment, List<String> evidenceRefs) {
        public SystemNode {
            require(nodeId, "nodeId"); require(organizationId, "organizationId");
            Objects.requireNonNull(nodeType, "nodeType"); require(name, "name");
            Objects.requireNonNull(language, "language"); require(environment, "environment");
            evidenceRefs = immutable(evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("system node requires evidence");
        }
    }

    public record EdgeEvidence(
            String evidenceRef, EvidenceSource source, Instant observedAt, String environment,
            String artifactHash) {
        public EdgeEvidence {
            require(evidenceRef, "evidenceRef"); Objects.requireNonNull(source, "source");
            Objects.requireNonNull(observedAt, "observedAt"); require(environment, "environment");
            require(artifactHash, "artifactHash");
        }
    }

    public record DependencyEdge(
            String edgeId, String organizationId, String sourceNodeId, String targetNodeId,
            EdgeType edgeType, String environment, double confidence, Instant firstObservedAt,
            Instant lastObservedAt, long observationCount, EdgeValidity validity,
            List<EdgeEvidence> evidence, boolean hardDependency, String contractRef) {
        public DependencyEdge {
            require(edgeId, "edgeId"); require(organizationId, "organizationId");
            require(sourceNodeId, "sourceNodeId"); require(targetNodeId, "targetNodeId");
            Objects.requireNonNull(edgeType, "edgeType"); require(environment, "environment");
            if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("confidence must be in [0,1]");
            Objects.requireNonNull(firstObservedAt, "firstObservedAt");
            Objects.requireNonNull(lastObservedAt, "lastObservedAt");
            if (lastObservedAt.isBefore(firstObservedAt)) throw new IllegalArgumentException("edge observation time reversed");
            if (observationCount < 1) throw new IllegalArgumentException("observationCount must be positive");
            Objects.requireNonNull(validity, "validity"); evidence = immutable(evidence);
            if (evidence.isEmpty()) throw new IllegalArgumentException("dependency edge requires evidence");
            if (validity == EdgeValidity.SUSPECTED && hardDependency) {
                throw new IllegalArgumentException("suspected edge cannot be a hard dependency");
            }
        }
    }

    public record LandscapeCoverage(
            double repository, double deployable, double runtime, double contract, double trace,
            double message, double database, double externalSystem) {
        public LandscapeCoverage {
            for (double value : List.of(repository, deployable, runtime, contract, trace, message, database, externalSystem)) {
                if (value < 0 || value > 1) throw new IllegalArgumentException("coverage must be in [0,1]");
            }
        }
        public double minimum() {
            return List.of(repository, deployable, runtime, contract, trace, message, database, externalSystem)
                    .stream().mapToDouble(Double::doubleValue).min().orElse(0);
        }
    }

    public record SystemLandscape(
            String landscapeId, String organizationId, long version, Instant observedAt,
            List<SystemNode> nodes, List<DependencyEdge> edges, LandscapeCoverage coverage,
            List<String> unknowns, boolean complete) {
        public SystemLandscape {
            require(landscapeId, "landscapeId"); require(organizationId, "organizationId");
            if (version < 1) throw new IllegalArgumentException("version must be positive");
            Objects.requireNonNull(observedAt, "observedAt"); nodes = immutable(nodes); edges = immutable(edges);
            Objects.requireNonNull(coverage, "coverage"); unknowns = immutable(unknowns);
            if (complete && (coverage.minimum() < 1 || !unknowns.isEmpty())) {
                throw new IllegalArgumentException("incomplete landscape cannot claim completeness");
            }
        }
    }

    public record DataOwnership(
            String dataAssetId, String organizationId, String authoritativeWriter,
            String authoritativeStore, OwnershipState state, Instant effectiveAt,
            List<String> replicas, List<String> evidenceRefs) {
        public DataOwnership {
            require(dataAssetId, "dataAssetId"); require(organizationId, "organizationId");
            require(authoritativeWriter, "authoritativeWriter"); require(authoritativeStore, "authoritativeStore");
            Objects.requireNonNull(state, "state"); Objects.requireNonNull(effectiveAt, "effectiveAt");
            replicas = immutable(replicas); evidenceRefs = immutable(evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("data ownership requires evidence");
        }
    }

    static <T> List<T> immutable(List<T> values) {
        return values == null ? List.of() : List.copyOf(values);
    }
    static <K,V> Map<K,V> immutable(Map<K,V> values) {
        return values == null ? Map.of() : Map.copyOf(values);
    }
    static <T> Set<T> immutable(Set<T> values) {
        return values == null ? Set.of() : Set.copyOf(values);
    }
    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
