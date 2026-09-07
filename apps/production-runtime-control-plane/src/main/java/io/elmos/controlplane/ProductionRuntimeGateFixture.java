package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeException;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import io.elmos.productionruntime.ProductionWorkloadPackCatalog;

/** Exact, deployment-owned fixture for authorized target-environment runtime gates. */
record ProductionRuntimeGateFixture(
        UUID tenantId,
        UUID accountId,
        UUID walletId,
        UUID projectId,
        UUID jobId,
        UUID stageId,
        UUID workItemId,
        UUID attemptId,
        String provider,
        String model,
        UUID providerPricingVersionId,
        UUID commercialPricingVersionId,
        BigDecimal reservationAmount,
        long inputTokens,
        long cachedInputTokens,
        long outputTokens,
        long reasoningTokens,
        BigDecimal providerTotalCost,
        BigDecimal customerCreditCost,
        Map<String, WorkloadGateFixture> workloads
) {
    static ProductionRuntimeGateFixture load(Path path, ObjectMapper json) {
        if (path == null || Files.isSymbolicLink(path) || !Files.isRegularFile(path)) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture must be a regular non-symlink file");
        }
        try {
            JsonNode root = json.readTree(path.toFile());
            if (root.path("schema_version").asInt() != 1) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID", "gate fixture schema is invalid");
            }
            BigDecimal amount = root.path("reservation_amount").decimalValue();
            if (amount.signum() <= 0 || amount.compareTo(BigDecimal.ONE) > 0) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID",
                        "gate reservation amount must be in (0, 1]");
            }
            long inputTokens = nonNegativeLong(root, "input_tokens");
            long cachedInputTokens = nonNegativeLong(root, "cached_input_tokens");
            long outputTokens = nonNegativeLong(root, "output_tokens");
            long reasoningTokens = nonNegativeLong(root, "reasoning_tokens");
            if (inputTokens + outputTokens + reasoningTokens < 1L
                    || cachedInputTokens > inputTokens) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID",
                        "gate usage must be non-zero and cached input cannot exceed input");
            }
            BigDecimal providerCost = positiveDecimal(root, "provider_total_cost");
            BigDecimal customerCost = positiveDecimal(root, "customer_credit_cost");
            if (customerCost.compareTo(amount) > 0) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID",
                        "gate customer cost cannot exceed the reservation amount");
            }
            Map<String, WorkloadGateFixture> workloads = workloads(root);
            return new ProductionRuntimeGateFixture(
                    uuid(root, "tenant_id"), uuid(root, "account_id"),
                    uuid(root, "wallet_id"), uuid(root, "project_id"),
                    uuid(root, "job_id"), uuid(root, "stage_id"),
                    uuid(root, "work_item_id"), uuid(root, "attempt_id"),
                    text(root, "provider", 80), text(root, "model", 200),
                    uuid(root, "provider_pricing_version_id"),
                    uuid(root, "commercial_pricing_version_id"), amount,
                    inputTokens, cachedInputTokens, outputTokens, reasoningTokens,
                    providerCost, customerCost, workloads);
        } catch (IOException | IllegalArgumentException ex) {
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture cannot be parsed", ex);
        }
    }

    WorkloadGateFixture workload(String jobType) {
        WorkloadGateFixture workload = workloads.get(jobType);
        if (workload == null) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_WORKLOAD_UNKNOWN",
                    "gate fixture does not bind workload: " + jobType);
        }
        return workload;
    }

    private static Map<String, WorkloadGateFixture> workloads(JsonNode root) {
        JsonNode values = root.path("workloads");
        if (!values.isArray() || values.size() != 4) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture must bind exactly four workload outputs");
        }
        Map<String, WorkloadGateFixture> result = new LinkedHashMap<>();
        var jobIds = new java.util.HashSet<UUID>();
        var workItemIds = new java.util.HashSet<UUID>();
        for (JsonNode value : values) {
            String jobType = text(value, "job_type", 80);
            ProductionWorkloadPackCatalog.requireComplete(jobType);
            String workType = text(value, "work_type", 120);
            UUID jobId = uuid(value, "job_id");
            UUID workItemId = uuid(value, "work_item_id");
            String artifactSha256 = text(value, "artifact_sha256", 64)
                    .toLowerCase(java.util.Locale.ROOT);
            if (!artifactSha256.matches("[0-9a-f]{64}")) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID",
                        "workload artifact_sha256 must be lowercase SHA-256");
            }
            WorkloadGateFixture fixture = new WorkloadGateFixture(
                    jobType, workType, jobId, workItemId, artifactSha256);
            if (result.put(jobType, fixture) != null
                    || !jobIds.add(jobId) || !workItemIds.add(workItemId)) {
                throw new ProductionRuntimeException(
                        "PRODUCTION_GATE_FIXTURE_INVALID",
                        "workload identities must be exact and unique");
            }
        }
        Set<String> expected = Set.of(
                "SPRING_MODERNIZATION", "LANGUAGE_CONVERSION",
                "PROJECT_GENERATION", "SQL_CONVERSION");
        if (!result.keySet().equals(expected)) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture must bind all four exact workload job types");
        }
        return Map.copyOf(result);
    }

    private static long nonNegativeLong(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.canConvertToLong() || value.asLong() < 0) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture field must be a non-negative integer: " + field);
        }
        return value.asLong();
    }

    private static BigDecimal positiveDecimal(JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isNumber() || value.decimalValue().signum() <= 0) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture field must be positive: " + field);
        }
        return value.decimalValue();
    }

    private static UUID uuid(JsonNode root, String field) {
        return UUID.fromString(text(root, field, 36));
    }

    private static String text(JsonNode root, String field, int maximum) {
        String value = root.path(field).asText("");
        if (value.isBlank() || value.length() > maximum) {
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture field is invalid: " + field);
        }
        return value;
    }

    record WorkloadGateFixture(
            String jobType,
            String workType,
            UUID jobId,
            UUID workItemId,
            String artifactSha256
    ) {}
}
