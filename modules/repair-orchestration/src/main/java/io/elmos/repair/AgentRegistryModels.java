package io.elmos.repair;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Pattern;

/** Public, closed contracts for the durable Agent Registry. */
public final class AgentRegistryModels {
    public static final String SCHEMA_VERSION = "elmos.agent-registry.v1";
    public static final String CAPABILITY_VERSION = "agent-registry-capabilities-v1";

    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}");
    private static final Pattern DECLARATION_NAME = Pattern.compile("[a-z0-9][a-z0-9._:/-]{0,127}");

    private AgentRegistryModels() {}

    /** Merge precedence is explicit and cannot be influenced by input ordering. */
    public enum Source {
        GLOBAL(0), PROJECT(1), MANAGED(2);

        private final int precedence;

        Source(int precedence) {
            this.precedence = precedence;
        }

        public int precedence() {
            return precedence;
        }
    }

    public record AgentLimits(
            int maximumSteps,
            long maximumTokens,
            long maximumCostMicros,
            long timeoutMillis
    ) {
        public AgentLimits {
            if (maximumSteps < 1 || maximumSteps > 10_000) {
                throw rejected("AGENT_LIMITS_INVALID", "maximumSteps must be between 1 and 10000");
            }
            if (maximumTokens < 1 || maximumTokens > 100_000_000L) {
                throw rejected("AGENT_LIMITS_INVALID", "maximumTokens must be between 1 and 100000000");
            }
            if (maximumCostMicros < 0 || maximumCostMicros > 10_000_000_000_000L) {
                throw rejected("AGENT_LIMITS_INVALID", "maximumCostMicros is outside the bounded range");
            }
            if (timeoutMillis < 1 || timeoutMillis > 86_400_000L) {
                throw rejected("AGENT_LIMITS_INVALID", "timeoutMillis must be between 1 and 86400000");
            }
        }
    }

    public record AgentDefinition(
            String id,
            String description,
            String mode,
            String model,
            String prompt,
            Set<String> permissions,
            Set<String> capabilities,
            Map<String, Boolean> featureFlags,
            AgentLimits limits,
            long version,
            boolean enabled
    ) {
        public AgentDefinition {
            id = declarationName(id, "agent.id");
            description = boundedText(description, "agent.description", 2_048);
            mode = declarationName(mode, "agent.mode");
            model = declarationName(model, "agent.model");
            prompt = boundedText(prompt, "agent.prompt", 32_768);
            permissions = declarationSet(permissions, "agent.permissions", 128);
            capabilities = declarationSet(capabilities, "agent.capabilities", 128);
            featureFlags = normalizeFeatureFlags(featureFlags);
            limits = Objects.requireNonNull(limits, "agent.limits");
            if (version < 1) throw rejected("AGENT_VERSION_INVALID", "agent.version must be positive");
        }
    }

    /**
     * Actor permissions are trusted-server context. Public transports must derive them from an authenticated
     * identity and must never deserialize them from request JSON.
     */
    public record LayerUpdate(
            String tenantId,
            String projectId,
            Source source,
            long expectedContextEpoch,
            String actorId,
            Set<String> actorPermissions,
            String idempotencyKey,
            List<AgentDefinition> agents
    ) {
        public LayerUpdate {
            tenantId = identifier(tenantId, "tenantId");
            projectId = identifier(projectId, "projectId");
            source = Objects.requireNonNull(source, "source");
            if (expectedContextEpoch < 0) {
                throw rejected("CONTEXT_EPOCH_INVALID", "expectedContextEpoch cannot be negative");
            }
            actorId = identifier(actorId, "actorId");
            actorPermissions = declarationSet(actorPermissions, "actorPermissions", 128);
            idempotencyKey = identifier(idempotencyKey, "idempotencyKey");
            agents = agentList(agents);
        }
    }

    /** A selection is epoch-bound and persisted before any caller handler can run. */
    public record SelectionRequest(
            String tenantId,
            String projectId,
            String agentId,
            long expectedContextEpoch,
            String actorId,
            Set<String> actorPermissions,
            Set<String> requiredPermissions,
            Set<String> requiredCapabilities,
            String idempotencyKey
    ) {
        public SelectionRequest {
            tenantId = identifier(tenantId, "tenantId");
            projectId = identifier(projectId, "projectId");
            agentId = declarationName(agentId, "agentId");
            if (expectedContextEpoch < 0) {
                throw rejected("CONTEXT_EPOCH_INVALID", "expectedContextEpoch cannot be negative");
            }
            actorId = identifier(actorId, "actorId");
            actorPermissions = declarationSet(actorPermissions, "actorPermissions", 128);
            requiredPermissions = declarationSet(requiredPermissions, "requiredPermissions", 128);
            requiredCapabilities = declarationSet(requiredCapabilities, "requiredCapabilities", 128);
            idempotencyKey = identifier(idempotencyKey, "idempotencyKey");
        }
    }

    public record ResolvedAgent(AgentDefinition definition, Source source) {
        public ResolvedAgent {
            definition = Objects.requireNonNull(definition, "definition");
            source = Objects.requireNonNull(source, "source");
        }
    }

    public record RegistryMetrics(
            long configurationChanges,
            long configurationReplays,
            long allowedSelections,
            long deniedSelections,
            long totalWallClockMicros,
            Map<String, Long> failureTypes
    ) {
        public RegistryMetrics {
            if (configurationChanges < 0 || configurationReplays < 0 || allowedSelections < 0
                    || deniedSelections < 0 || totalWallClockMicros < 0) {
                throw rejected("REGISTRY_METRICS_INVALID", "registry metric counters cannot be negative");
            }
            TreeMap<String, Long> normalizedFailures = new TreeMap<>();
            Objects.requireNonNull(failureTypes, "failureTypes").forEach((key, value) -> {
                String failureType = identifier(key, "failureTypes key");
                if (value == null || value < 0) {
                    throw rejected("REGISTRY_METRICS_INVALID", "failure type counters cannot be negative");
                }
                normalizedFailures.put(failureType, value);
            });
            failureTypes = Map.copyOf(normalizedFailures);
        }
    }

    /** Discoverable local capability. External evidence and certification remain explicitly separate. */
    public record RegistryRuntimeCapability(
            String schemaVersion,
            String capabilityVersion,
            String skillName,
            String implementationState,
            Set<String> supportedOperations,
            Set<String> requiredPermissions,
            boolean sideEffectsAuthorized,
            String externalEvidenceStatus,
            String certification
    ) {
        public RegistryRuntimeCapability {
            schemaVersion = boundedText(schemaVersion, "schemaVersion", 128);
            capabilityVersion = boundedText(capabilityVersion, "capabilityVersion", 128);
            skillName = declarationName(skillName, "skillName");
            implementationState = identifier(implementationState, "implementationState");
            supportedOperations = declarationSet(supportedOperations, "supportedOperations", 32);
            requiredPermissions = declarationSet(requiredPermissions, "requiredPermissions", 32);
            externalEvidenceStatus = identifier(externalEvidenceStatus, "externalEvidenceStatus");
            certification = identifier(certification, "certification");
        }
    }

    public record RegistryView(
            String schemaVersion,
            String capabilityVersion,
            String tenantId,
            String projectId,
            long contextEpoch,
            String registryDigest,
            List<ResolvedAgent> agents,
            RegistryMetrics metrics
    ) {
        public RegistryView {
            schemaVersion = boundedText(schemaVersion, "schemaVersion", 128);
            capabilityVersion = boundedText(capabilityVersion, "capabilityVersion", 128);
            tenantId = identifier(tenantId, "tenantId");
            projectId = identifier(projectId, "projectId");
            if (contextEpoch < 0) throw rejected("CONTEXT_EPOCH_INVALID", "contextEpoch cannot be negative");
            registryDigest = digest(registryDigest, "registryDigest");
            agents = List.copyOf(Objects.requireNonNull(agents, "agents"));
            metrics = Objects.requireNonNull(metrics, "metrics");
        }
    }

    public record MutationResult(
            String status,
            long contextEpoch,
            String registryDigest,
            boolean idempotentReplay
    ) {
        public MutationResult {
            status = declarationName(status, "status");
            if (contextEpoch < 0) throw rejected("CONTEXT_EPOCH_INVALID", "contextEpoch cannot be negative");
            registryDigest = digest(registryDigest, "registryDigest");
        }
    }

    public record SelectionPermit(
            String tenantId,
            String projectId,
            String actorId,
            String agentId,
            Source source,
            long agentVersion,
            long contextEpoch,
            Set<String> permissions,
            Set<String> capabilities,
            AgentLimits limits,
            Instant issuedAt,
            Instant expiresAt,
            String registryDigest,
            String permitDigest
    ) {
        public SelectionPermit {
            tenantId = identifier(tenantId, "tenantId");
            projectId = identifier(projectId, "projectId");
            actorId = identifier(actorId, "actorId");
            agentId = declarationName(agentId, "agentId");
            source = Objects.requireNonNull(source, "source");
            if (agentVersion < 1) throw rejected("AGENT_VERSION_INVALID", "agentVersion must be positive");
            if (contextEpoch < 0) throw rejected("CONTEXT_EPOCH_INVALID", "contextEpoch cannot be negative");
            permissions = declarationSet(permissions, "permissions", 128);
            capabilities = declarationSet(capabilities, "capabilities", 128);
            limits = Objects.requireNonNull(limits, "limits");
            issuedAt = Objects.requireNonNull(issuedAt, "issuedAt");
            expiresAt = Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(issuedAt)) {
                throw rejected("AGENT_PERMIT_EXPIRY_INVALID", "expiresAt must be after issuedAt");
            }
            registryDigest = digest(registryDigest, "registryDigest");
            permitDigest = digest(permitDigest, "permitDigest");
        }
    }

    public record SelectionDecision(
            String status,
            String reasonCode,
            long contextEpoch,
            String registryDigest,
            SelectionPermit permit,
            boolean idempotentReplay
    ) {
        public SelectionDecision {
            status = declarationName(status, "status");
            reasonCode = identifier(reasonCode, "reasonCode");
            if (contextEpoch < 0) throw rejected("CONTEXT_EPOCH_INVALID", "contextEpoch cannot be negative");
            registryDigest = digest(registryDigest, "registryDigest");
            if (("allowed".equals(status)) != (permit != null)) {
                throw rejected("SELECTION_DECISION_INVALID", "allowed decisions require exactly one permit");
            }
        }

        public boolean allowed() {
            return "allowed".equals(status);
        }
    }

    public record InvocationResult<T>(SelectionPermit permit, T value) {
        public InvocationResult {
            permit = Objects.requireNonNull(permit, "permit");
            value = Objects.requireNonNull(value, "value");
        }
    }

    public record AuditEvent(
            long sequence,
            Instant occurredAt,
            String actorId,
            String operation,
            String outcome,
            String requestDigest,
            String registryDigest,
            long contextEpoch
    ) {
        public AuditEvent {
            if (sequence < 1) throw rejected("AUDIT_SEQUENCE_INVALID", "audit sequence must be positive");
            occurredAt = Objects.requireNonNull(occurredAt, "occurredAt");
            actorId = identifier(actorId, "actorId");
            operation = declarationName(operation, "operation");
            outcome = identifier(outcome, "outcome");
            requestDigest = digest(requestDigest, "requestDigest");
            registryDigest = digest(registryDigest, "registryDigest");
            if (contextEpoch < 0) throw rejected("CONTEXT_EPOCH_INVALID", "contextEpoch cannot be negative");
        }
    }

    public static final class AgentRegistryException extends RuntimeException {
        private final String code;

        public AgentRegistryException(String code, String message) {
            super(message);
            this.code = identifier(code, "errorCode");
        }

        public String code() {
            return code;
        }
    }

    static AgentRegistryException rejected(String code, String message) {
        return new AgentRegistryException(code, message);
    }

    static String identifier(String value, String label) {
        if (value == null || !IDENTIFIER.matcher(value).matches()) {
            throw rejected("REGISTRY_IDENTIFIER_INVALID", label + " is not a valid bounded identifier");
        }
        return value;
    }

    static String declarationName(String value, String label) {
        if (value == null || !DECLARATION_NAME.matcher(value).matches()) {
            throw rejected("REGISTRY_DECLARATION_INVALID", label + " is not a valid declaration name");
        }
        return value;
    }

    static String boundedText(String value, String label, int maximumLength) {
        if (value == null || value.isBlank() || value.length() > maximumLength
                || value.codePoints().anyMatch(character -> character == 0 || character == 0x7f)) {
            throw rejected("REGISTRY_TEXT_INVALID", label + " is not valid bounded text");
        }
        return value;
    }

    static String digest(String value, String label) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw rejected("REGISTRY_DIGEST_INVALID", label + " must be a lowercase SHA-256 digest");
        }
        return value;
    }

    private static Set<String> declarationSet(Set<String> values, String label, int maximumItems) {
        Objects.requireNonNull(values, label);
        if (values.size() > maximumItems) {
            throw rejected("REGISTRY_COLLECTION_LIMIT_EXCEEDED", label + " exceeds its item limit");
        }
        TreeSet<String> normalized = new TreeSet<>();
        for (String value : values) normalized.add(declarationName(value, label));
        return Collections.unmodifiableSet(normalized);
    }

    private static Map<String, Boolean> normalizeFeatureFlags(Map<String, Boolean> values) {
        Objects.requireNonNull(values, "agent.featureFlags");
        if (values.size() > 64) {
            throw rejected("REGISTRY_COLLECTION_LIMIT_EXCEEDED", "agent.featureFlags exceeds its item limit");
        }
        TreeMap<String, Boolean> normalized = new TreeMap<>();
        values.forEach((key, value) -> normalized.put(
                declarationName(key, "agent.featureFlags key"),
                Objects.requireNonNull(value, "agent.featureFlags value")));
        return Map.copyOf(normalized);
    }

    private static List<AgentDefinition> agentList(List<AgentDefinition> values) {
        Objects.requireNonNull(values, "agents");
        if (values.size() > 256) {
            throw rejected("REGISTRY_COLLECTION_LIMIT_EXCEEDED", "agents exceeds its item limit");
        }
        List<AgentDefinition> normalized = new ArrayList<>(values.size());
        LinkedHashSet<String> ids = new LinkedHashSet<>();
        for (AgentDefinition value : values) {
            AgentDefinition definition = Objects.requireNonNull(value, "agent definition");
            if (!ids.add(definition.id())) {
                throw rejected("AGENT_ID_DUPLICATE", "agents contains a duplicate id");
            }
            normalized.add(definition);
        }
        normalized.sort((left, right) -> left.id().compareTo(right.id()));
        return List.copyOf(normalized);
    }
}
