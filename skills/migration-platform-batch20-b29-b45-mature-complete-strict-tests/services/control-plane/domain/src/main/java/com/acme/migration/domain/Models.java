package com.acme.migration.domain;

import java.time.Instant;
import java.util.UUID;

public final class Models {
    private Models() {}

    public record Project(UUID projectId, UUID tenantId, String name, Instant createdAt) {}

    public record Migration(
            UUID migrationId,
            UUID tenantId,
            UUID projectId,
            String sourceRepository,
            String sourceLanguage,
            String targetLanguage,
            String targetFramework,
            String status,
            String currentPhase,
            String riskTier,
            Instant createdAt,
            Instant updatedAt) {}

    public record Runner(
            UUID runnerId,
            UUID tenantId,
            String name,
            String version,
            String capabilities,
            String status,
            Instant lastHeartbeatAt) {}

    public record Task(
            UUID taskId,
            UUID tenantId,
            UUID workflowInstanceId,
            String taskType,
            String status,
            int priority,
            int attempt,
            int maxAttempts,
            String payload,
            UUID leasedBy,
            Instant leaseExpiresAt,
            String commitToken) {}
}
