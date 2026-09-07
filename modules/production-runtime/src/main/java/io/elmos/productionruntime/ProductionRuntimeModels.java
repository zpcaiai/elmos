package io.elmos.productionruntime;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** Public, serializable boundaries for the production repository execution kernel. */
public final class ProductionRuntimeModels {
    private ProductionRuntimeModels() {}

    public enum WorkItemStatus { PENDING, READY, RESERVING, WAITING_FOR_CREDIT, RESERVED, DISPATCHING, RUNNING, SUCCEEDED, RETRY_WAIT, FAILED, CANCELLED }
    public enum DispatchState { CREATED, RESERVING, RESERVED, ATTEMPT_CREATED, DISPATCHING, ACKED, COMPLETED, ABORTED }
    public enum AttemptStatus { CREATED, RUNNING, SUCCEEDED, FAILED, TIMED_OUT, LOST, CANCELLED }
    public enum ReservationStatus { ACTIVE, SETTLED, RELEASED, EXPIRED }
    public enum ModelCallStatus { CREATED, PROVIDER_ACCEPTED, RUNNING, COMPLETE, FAILED, UNKNOWN }
    public enum ToolCallStatus { CREATED, PROVIDER_ACCEPTED, COMPLETE, FAILED, UNKNOWN }
    public enum IdempotencyState { IN_PROGRESS, SUCCEEDED, FAILED }
    public enum TopUpStatus { PENDING, COMPLETED, REJECTED }

    public record TenantAccount(UUID tenantId, UUID accountId, UUID billingAccountId, UUID walletId, String currency) {}

    public record ProjectRequest(UUID tenantId, UUID accountId, String name, String projectType) {
        public ProjectRequest {
            require(tenantId, "tenantId");
            require(accountId, "accountId");
            requireText(name, "name", 200);
            requireText(projectType, "projectType", 80);
        }
    }

    public record JobRequest(
            UUID tenantId,
            UUID accountId,
            UUID projectId,
            String jobType,
            List<String> stageTypes,
            int maxParallelism,
            int priority
    ) {
        public JobRequest {
            require(tenantId, "tenantId");
            require(accountId, "accountId");
            require(projectId, "projectId");
            requireText(jobType, "jobType", 80);
            if (stageTypes == null || stageTypes.isEmpty() || stageTypes.stream().anyMatch(value -> value == null || value.isBlank())) {
                throw new IllegalArgumentException("stageTypes must contain at least one non-empty stage");
            }
            stageTypes = List.copyOf(stageTypes);
            if (maxParallelism < 1 || maxParallelism > 10_000) throw new IllegalArgumentException("maxParallelism out of range");
            if (priority < 0 || priority > 1_000) throw new IllegalArgumentException("priority out of range");
        }
    }

    public record WorkItemRequest(
            UUID tenantId,
            UUID jobId,
            UUID stageId,
            String workType,
            String resourceKey,
            long estimatedTokens,
            BigDecimal estimatedCredits,
            int maxRetries,
            String idempotencyKey
    ) {
        public WorkItemRequest {
            require(tenantId, "tenantId");
            require(jobId, "jobId");
            require(stageId, "stageId");
            requireText(workType, "workType", 120);
            requireText(resourceKey, "resourceKey", 500);
            requireText(idempotencyKey, "idempotencyKey", 200);
            if (estimatedTokens < 0 || estimatedCredits == null || estimatedCredits.signum() < 0) throw new IllegalArgumentException("estimate must be non-negative");
            if (maxRetries < 0 || maxRetries > 100) throw new IllegalArgumentException("maxRetries out of range");
            estimatedCredits = canonicalMoney(estimatedCredits);
        }
    }

    public record WorkerRegistration(
            UUID workerId,
            String workerName,
            String workerType,
            String endpointUri,
            String region,
            String zone,
            Map<String, Object> capabilities
    ) {
        public WorkerRegistration {
            require(workerId, "workerId");
            requireText(workerName, "workerName", 160);
            requireText(workerType, "workerType", 100);
            requireText(endpointUri, "endpointUri", 2_000);
            requireText(region, "region", 120);
            requireText(zone, "zone", 120);
            capabilities = capabilities == null ? Map.of() : Map.copyOf(capabilities);
            Object tuples = capabilities.get("routeTuples");
            if (!(tuples instanceof List<?> values) || values.isEmpty()
                    || values.size() > 10_000) {
                throw new IllegalArgumentException("worker routeTuples capability is required");
            }
            var distinct = new java.util.HashSet<String>();
            for (Object value : values) {
                if (!(value instanceof String tuple)
                        || !tuple.matches("[A-Z][A-Z0-9_]{0,79}:[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
                        || !distinct.add(tuple)) {
                    throw new IllegalArgumentException("worker routeTuples capability is malformed");
                }
            }
            Object concurrency = capabilities.get("maxConcurrent");
            if (!(concurrency instanceof Number number)
                    || number.intValue() < 1 || number.intValue() > 1024
                    || number.doubleValue() != number.intValue()) {
                throw new IllegalArgumentException("worker maxConcurrent capability is malformed");
            }
        }
    }

    public record DispatchIntent(
            UUID id,
            UUID tenantId,
            UUID workItemId,
            DispatchState state,
            UUID reservationId,
            UUID workerId,
            UUID attemptId,
            long fencingToken,
            String reservationIdempotencyKey,
            String dispatchIdempotencyKey,
            UUID projectId,
            UUID jobId,
            UUID walletId,
            BigDecimal estimatedCredits,
            Instant reservationExpiresAt,
            String payloadJson
    ) {}

    public record DispatchEnvelope(
            UUID tenantId,
            UUID workItemId,
            UUID attemptId,
            UUID workerId,
            long fencingToken,
            String endpointUri,
            String dispatchIdempotencyKey,
            Map<String, Object> payload
    ) {
        public DispatchEnvelope {
            require(tenantId, "tenantId");
            require(workItemId, "workItemId");
            require(attemptId, "attemptId");
            require(workerId, "workerId");
            if (fencingToken < 1) {
                throw new IllegalArgumentException("fencingToken must be positive");
            }
            requireText(endpointUri, "endpointUri", 2_000);
            requireText(dispatchIdempotencyKey, "dispatchIdempotencyKey", 240);
            payload = payload == null ? Map.of() : Map.copyOf(payload);
        }
    }

    public record ReserveRequest(
            UUID tenantId,
            UUID walletId,
            UUID projectId,
            UUID jobId,
            UUID workItemId,
            String idempotencyKey,
            BigDecimal amount,
            Instant expiresAt
    ) {
        public ReserveRequest {
            require(tenantId, "tenantId"); require(walletId, "walletId"); require(projectId, "projectId"); require(workItemId, "workItemId");
            requireText(idempotencyKey, "idempotencyKey", 240);
            if (amount == null || amount.signum() <= 0) throw new IllegalArgumentException("amount must be positive");
            if (expiresAt == null || !expiresAt.isAfter(Instant.now())) throw new IllegalArgumentException("expiresAt must be in the future");
            amount = canonicalMoney(amount);
        }
    }

    public record ReservationResult(UUID reservationId, ReservationStatus status, BigDecimal reservedAmount, BigDecimal availableBalance) {}

    public record MeterSnapshot(
            UUID tenantId,
            UUID reservationId,
            UUID modelCallId,
            long sequenceNo,
            long cumulativeInputTokens,
            long cumulativeCachedInputTokens,
            long cumulativeOutputTokens,
            long cumulativeReasoningTokens,
            BigDecimal meteredProviderCost,
            BigDecimal meteredCreditCost
    ) {
        public MeterSnapshot {
            require(tenantId, "tenantId"); require(reservationId, "reservationId"); require(modelCallId, "modelCallId");
            if (sequenceNo < 1 || cumulativeInputTokens < 0 || cumulativeCachedInputTokens < 0 || cumulativeOutputTokens < 0 || cumulativeReasoningTokens < 0) throw new IllegalArgumentException("meter values out of range");
            if (meteredProviderCost == null || meteredCreditCost == null || meteredProviderCost.signum() < 0 || meteredCreditCost.signum() < 0) throw new IllegalArgumentException("metered costs must be non-negative");
            meteredProviderCost = canonicalMoney(meteredProviderCost);
            meteredCreditCost = canonicalMoney(meteredCreditCost);
        }
    }

    public record FinalUsage(
            UUID tenantId,
            UUID reservationId,
            UUID modelCallId,
            String provider,
            String model,
            String providerUsageId,
            UUID providerPricingVersionId,
            UUID commercialPricingVersionId,
            long inputTokens,
            long cachedInputTokens,
            long outputTokens,
            long reasoningTokens,
            BigDecimal providerTotalCost,
            BigDecimal customerCreditCost
    ) {
        public FinalUsage {
            require(tenantId, "tenantId"); require(reservationId, "reservationId"); require(modelCallId, "modelCallId");
            requireText(provider, "provider", 80); requireText(model, "model", 200); requireText(providerUsageId, "providerUsageId", 240);
            require(providerPricingVersionId, "providerPricingVersionId"); require(commercialPricingVersionId, "commercialPricingVersionId");
            if (inputTokens < 0 || cachedInputTokens < 0 || outputTokens < 0 || reasoningTokens < 0) throw new IllegalArgumentException("final token values must be non-negative");
            if (providerTotalCost == null || providerTotalCost.signum() < 0 || customerCreditCost == null || customerCreditCost.signum() < 0) throw new IllegalArgumentException("final costs must be non-negative");
            providerTotalCost = canonicalMoney(providerTotalCost); customerCreditCost = canonicalMoney(customerCreditCost);
        }
    }

    public record SettlementRequest(UUID workItemId, FinalUsage usage) {
        public SettlementRequest {
            require(workItemId, "workItemId"); Objects.requireNonNull(usage, "usage");
        }
    }

    public record ModelCallRequest(
            UUID tenantId,
            UUID accountId,
            UUID projectId,
            UUID jobId,
            UUID stageId,
            UUID workItemId,
            UUID attemptId,
            String provider,
            String model,
            String idempotencyKey,
            String requestHash
    ) {
        public ModelCallRequest {
            require(tenantId, "tenantId"); require(accountId, "accountId"); require(projectId, "projectId"); require(jobId, "jobId"); require(stageId, "stageId"); require(workItemId, "workItemId"); require(attemptId, "attemptId");
            requireText(provider, "provider", 80); requireText(model, "model", 200); requireText(idempotencyKey, "idempotencyKey", 240); requireText(requestHash, "requestHash", 128);
        }
    }

    public record ModelCallReceipt(UUID modelCallId, ModelCallStatus status, String providerRequestId, String responseArtifactId) {}

    public record ToolCallRequest(
            UUID tenantId, UUID accountId, UUID projectId, UUID jobId, UUID stageId,
            UUID workItemId, UUID attemptId, String tool, String idempotencyKey, String requestHash
    ) {
        public ToolCallRequest {
            require(tenantId, "tenantId"); require(accountId, "accountId"); require(projectId, "projectId"); require(jobId, "jobId"); require(stageId, "stageId"); require(workItemId, "workItemId"); require(attemptId, "attemptId");
            requireText(tool, "tool", 200); requireText(idempotencyKey, "idempotencyKey", 240); requireText(requestHash, "requestHash", 128);
        }
    }

    public record ToolCallReceipt(UUID toolCallId, ToolCallStatus status, String providerRequestId, UUID responseArtifactId) {}

    /**
     * Digest-bound evidence that an engine output satisfied the workload-pack
     * completion contract.  This is deliberately an engineering gate receipt,
     * not a production certification claim.
     */
    public record OutputVerificationReceipt(
            String schemaVersion,
            String packId,
            String jobType,
            String workType,
            String artifactUri,
            String artifactSha256,
            String verifier,
            String verificationStatus,
            String certificationStatus,
            Map<String, Object> checks
    ) {
        public static final String SCHEMA_VERSION = "elmos.production-output-verification/v1";

        public OutputVerificationReceipt {
            requireText(schemaVersion, "schemaVersion", 120);
            requireText(packId, "packId", 160);
            requireText(jobType, "jobType", 80);
            requireText(workType, "workType", 120);
            requireText(artifactUri, "artifactUri", 2_000);
            requireText(artifactSha256, "artifactSha256", 128);
            requireText(verifier, "verifier", 240);
            requireText(verificationStatus, "verificationStatus", 40);
            requireText(certificationStatus, "certificationStatus", 40);
            if (!SCHEMA_VERSION.equals(schemaVersion)) {
                throw new IllegalArgumentException("unsupported output verification schemaVersion");
            }
            if (!artifactSha256.matches("[0-9a-fA-F]{64}")) {
                throw new IllegalArgumentException("artifactSha256 must be a SHA-256 digest");
            }
            artifactSha256 = artifactSha256.toLowerCase(java.util.Locale.ROOT);
            java.net.URI parsed;
            try {
                parsed = java.net.URI.create(artifactUri);
            } catch (IllegalArgumentException ex) {
                throw new IllegalArgumentException("artifactUri must be a valid absolute URI", ex);
            }
            if (!parsed.isAbsolute() || parsed.getScheme() == null
                    || !java.util.Set.of("cas", "s3", "gs", "azblob", "https")
                            .contains(parsed.getScheme().toLowerCase(java.util.Locale.ROOT))) {
                throw new IllegalArgumentException("artifactUri must use an approved immutable/object-store scheme");
            }
            if (!"PASSED".equals(verificationStatus)) {
                throw new IllegalArgumentException("verificationStatus must be PASSED");
            }
            if (!"NOT_CERTIFIED".equals(certificationStatus)) {
                throw new IllegalArgumentException("output gate receipt cannot claim certification");
            }
            if (checks == null || checks.isEmpty() || checks.size() > 100) {
                throw new IllegalArgumentException("checks must contain bounded output-gate results");
            }
            var canonicalChecks = new java.util.LinkedHashMap<String, Object>();
            checks.forEach((name, value) -> {
                requireText(name, "check name", 120);
                if (!name.matches("[a-z][a-z0-9_]{0,119}")) {
                    throw new IllegalArgumentException("check name must be a lower_snake_case identifier");
                }
                if (!(value instanceof Boolean || value instanceof Byte
                        || value instanceof Short || value instanceof Integer
                        || value instanceof Long || value instanceof java.math.BigInteger
                        || value instanceof String)) {
                    throw new IllegalArgumentException("check values must be scalar booleans, integers, or strings");
                }
                canonicalChecks.put(name, value);
            });
            checks = Map.copyOf(canonicalChecks);
        }
    }

    public record Completion(
            UUID tenantId,
            UUID workItemId,
            UUID attemptId,
            UUID workerId,
            long fencingToken,
            AttemptStatus status,
            String errorCode,
            String errorMessage
    ) {
        public Completion {
            require(tenantId, "tenantId");
            require(workItemId, "workItemId");
            require(attemptId, "attemptId");
            require(workerId, "workerId");
            if (fencingToken < 1) {
                throw new IllegalArgumentException("fencingToken must be positive");
            }
            if (status == null || (status != AttemptStatus.SUCCEEDED
                    && status != AttemptStatus.FAILED
                    && status != AttemptStatus.TIMED_OUT
                    && status != AttemptStatus.LOST
                    && status != AttemptStatus.CANCELLED)) {
                throw new IllegalArgumentException("completion status must be terminal");
            }
            optionalText(errorCode, "errorCode", 200);
            optionalText(errorMessage, "errorMessage", 2_000);
            if (status == AttemptStatus.SUCCEEDED
                    && (errorCode != null || errorMessage != null)) {
                throw new IllegalArgumentException("successful completion cannot contain an error");
            }
        }
    }

    public record Checkpoint(UUID tenantId, UUID jobId, UUID workItemId, UUID attemptId, String checkpointType, long sequenceNo, String stateObjectUri, String stateHash) {
        public Checkpoint {
            require(tenantId, "tenantId"); require(jobId, "jobId"); require(workItemId, "workItemId"); require(attemptId, "attemptId");
            requireText(checkpointType, "checkpointType", 100); requireText(stateObjectUri, "stateObjectUri", 2_000); requireText(stateHash, "stateHash", 128);
            if (sequenceNo < 1) throw new IllegalArgumentException("sequenceNo must be positive");
            if (!stateHash.matches("[0-9a-fA-F]{64}")) {
                throw new IllegalArgumentException("stateHash must be a SHA-256 digest");
            }
            stateHash = stateHash.toLowerCase(java.util.Locale.ROOT);
        }
    }

    public record ProgressSnapshot(UUID tenantId, UUID projectId, UUID jobId, long total, long ready, long running, long completed, long failed, BigDecimal progress, long tokensConsumed, BigDecimal creditsConsumed, Instant updatedAt) {}

    /** Read-only status used by the authorized external workload-output gate. */
    public record WorkloadOutputStatus(
            UUID jobId,
            UUID workItemId,
            String jobType,
            String workType,
            String jobStatus,
            String workItemStatus,
            String artifactSha256,
            String verificationStatus,
            String certificationStatus,
            Instant verifiedAt
    ) {}

    /** Tenant-owned hard admission ceilings enforced under a PostgreSQL row lock. */
    public record AdmissionPolicy(
            UUID tenantId,
            int maxActiveJobs,
            int maxActiveWorkItems,
            int maxProjectActiveWorkItems,
            int maxConcurrentModelCalls,
            int maxCompileTestSlots,
            int maxProviderCallsPerMinute,
            long dailyTokenCap,
            BigDecimal dailyCreditCap
    ) {
        public AdmissionPolicy {
            require(tenantId, "tenantId");
            requireLimit(maxActiveJobs, "maxActiveJobs", 1_000_000);
            requireLimit(maxActiveWorkItems, "maxActiveWorkItems", 1_000_000);
            requireLimit(maxProjectActiveWorkItems, "maxProjectActiveWorkItems", 1_000_000);
            requireLimit(maxConcurrentModelCalls, "maxConcurrentModelCalls", 1_000_000);
            requireLimit(maxCompileTestSlots, "maxCompileTestSlots", 1_000_000);
            requireLimit(maxProviderCallsPerMinute, "maxProviderCallsPerMinute", 1_000_000);
            if (dailyTokenCap < 1 || dailyTokenCap > 9_000_000_000_000_000L) {
                throw new IllegalArgumentException("dailyTokenCap out of range");
            }
            if (dailyCreditCap == null || dailyCreditCap.signum() <= 0) {
                throw new IllegalArgumentException("dailyCreditCap must be positive");
            }
            dailyCreditCap = canonicalMoney(dailyCreditCap);
        }
    }

    public record TopUpRequest(UUID tenantId, UUID walletId, String provider, String providerPaymentId, BigDecimal amount, String requestHash) {
        public TopUpRequest {
            require(tenantId, "tenantId"); require(walletId, "walletId"); requireText(provider, "provider", 80); requireText(providerPaymentId, "providerPaymentId", 240);
            if (amount == null || amount.signum() <= 0) throw new IllegalArgumentException("amount must be positive");
            requireText(requestHash, "requestHash", 128);
            amount = canonicalMoney(amount);
        }
    }

    public record TopUpResult(UUID topUpId, TopUpStatus status, BigDecimal availableBalance) {}

    public record OutboxMessage(long id, UUID tenantId, String aggregateType, UUID aggregateId, String eventType, String payloadJson, UUID claimToken) {}

    public record ReadyWorkItem(
            UUID tenantId,
            UUID accountId,
            UUID projectId,
            UUID jobId,
            UUID stageId,
            UUID workItemId,
            UUID walletId,
            UUID workerId,
            String jobType,
            String workType,
            String resourceKey,
            int priority,
            int retryCount,
            BigDecimal estimatedCredits,
            Instant readyAt,
            Instant createdAt
    ) {
        public ReadyWorkItem {
            require(tenantId, "tenantId"); require(accountId, "accountId");
            require(projectId, "projectId"); require(jobId, "jobId");
            require(stageId, "stageId"); require(workItemId, "workItemId");
            requireText(jobType, "jobType", 80); requireText(workType, "workType", 120);
            requireText(resourceKey, "resourceKey", 500);
            if (retryCount < 0 || estimatedCredits == null || estimatedCredits.signum() <= 0) {
                throw new IllegalArgumentException("ready work item has invalid retry or credit state");
            }
        }
    }

    public record JobProjectionCandidate(UUID tenantId, UUID jobId) {
        public JobProjectionCandidate {
            require(tenantId, "tenantId"); require(jobId, "jobId");
        }
    }

    public record ModelCallRecoveryCandidate(
            UUID modelCallId,
            ModelCallRequest request,
            String providerRequestId,
            ModelCallStatus status,
            int reconcileAttempts
    ) {
        public ModelCallRecoveryCandidate {
            require(modelCallId, "modelCallId"); Objects.requireNonNull(request, "request");
            Objects.requireNonNull(status, "status");
            if (reconcileAttempts < 0) throw new IllegalArgumentException("reconcileAttempts is negative");
        }
    }

    public record RepositorySnapshotRequest(
            UUID tenantId, UUID projectId, String gitCommitSha, String snapshotHash,
            String objectUri, long totalFiles, long totalLoc, long totalBytes
    ) {
        public RepositorySnapshotRequest {
            require(tenantId, "tenantId"); require(projectId, "projectId");
            requireText(gitCommitSha, "gitCommitSha", 128); requireText(snapshotHash, "snapshotHash", 128); requireText(objectUri, "objectUri", 2_000);
            if (!snapshotHash.matches("[0-9a-fA-F]{64}")) throw new IllegalArgumentException("snapshotHash must be a SHA-256 digest");
            if (totalFiles < 0 || totalLoc < 0 || totalBytes < 0) throw new IllegalArgumentException("snapshot metrics must be non-negative");
            gitCommitSha = gitCommitSha.toLowerCase(java.util.Locale.ROOT); snapshotHash = snapshotHash.toLowerCase(java.util.Locale.ROOT);
        }
    }

    public record ArtifactRequest(
            UUID tenantId, UUID projectId, UUID jobId, UUID workItemId,
            String artifactType, String objectUri, String sha256, long sizeBytes
    ) {
        public ArtifactRequest {
            require(tenantId, "tenantId"); require(projectId, "projectId"); requireText(artifactType, "artifactType", 120); requireText(objectUri, "objectUri", 2_000); requireText(sha256, "sha256", 64);
            if (!sha256.matches("[0-9a-fA-F]{64}")) throw new IllegalArgumentException("sha256 must be a SHA-256 digest");
            if (sizeBytes < 0) throw new IllegalArgumentException("sizeBytes must be non-negative");
            sha256 = sha256.toLowerCase(java.util.Locale.ROOT);
        }
    }

    public record ValidationRunRequest(UUID tenantId, UUID jobId, String validationType) {
        public ValidationRunRequest {
            require(tenantId, "tenantId"); require(jobId, "jobId"); requireText(validationType, "validationType", 160);
        }
    }

    public static void require(UUID value, String name) { Objects.requireNonNull(value, name); }
    public static void requireText(String value, String name, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength) throw new IllegalArgumentException(name + " is blank or too long");
    }
    private static void optionalText(String value, String name, int maxLength) {
        if (value != null && (value.isBlank() || value.length() > maxLength)) {
            throw new IllegalArgumentException(name + " is blank or too long");
        }
    }
    private static void requireLimit(int value, String name, int maximum) {
        if (value < 1 || value > maximum) throw new IllegalArgumentException(name + " out of range");
    }
    static BigDecimal canonicalMoney(BigDecimal value) { return value.setScale(12, RoundingMode.UNNECESSARY); }
}
