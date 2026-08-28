package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeException;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

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
        BigDecimal reservationAmount
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
            return new ProductionRuntimeGateFixture(
                    uuid(root, "tenant_id"), uuid(root, "account_id"),
                    uuid(root, "wallet_id"), uuid(root, "project_id"),
                    uuid(root, "job_id"), uuid(root, "stage_id"),
                    uuid(root, "work_item_id"), uuid(root, "attempt_id"),
                    text(root, "provider", 80), text(root, "model", 200),
                    uuid(root, "provider_pricing_version_id"),
                    uuid(root, "commercial_pricing_version_id"), amount);
        } catch (IOException | IllegalArgumentException ex) {
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "PRODUCTION_GATE_FIXTURE_INVALID",
                    "gate fixture cannot be parsed", ex);
        }
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
}
