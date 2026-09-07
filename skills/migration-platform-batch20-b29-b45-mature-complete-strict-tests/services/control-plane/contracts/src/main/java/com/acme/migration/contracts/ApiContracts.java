package com.acme.migration.contracts;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class ApiContracts {
    private ApiContracts() {}

    public record CreateProjectRequest(@NotBlank String name) {}
    public record ProjectResponse(UUID projectId, UUID tenantId, String name, Instant createdAt) {}

    public record CreateMigrationRequest(
            @NotNull UUID projectId,
            @NotBlank String sourceRepository,
            @NotBlank String sourceLanguage,
            @NotBlank String targetLanguage,
            @NotBlank String targetFramework) {}

    public record MigrationResponse(
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

    public record OverviewResponse(
            long projects,
            long migrations,
            long queuedTasks,
            long onlineRunners,
            List<MigrationResponse> recentMigrations) {}

    public record RunnerRegisterRequest(@NotBlank String name, @NotBlank String version, List<String> capabilities) {}
    public record RunnerRegisterResponse(UUID runnerId, String status) {}
    public record RunnerHeartbeatRequest(@NotBlank String status) {}

    public record ClaimJobResponse(
            UUID jobId,
            String jobType,
            String payload,
            Instant leaseExpiresAt,
            String commitToken) {}

    public record JobCompleteRequest(
            @NotBlank String commitToken,
            @NotBlank String status,
            String outputPayload,
            String artifactPath) {}

    public record DemoBootstrapResponse(UUID projectId, UUID migrationId, UUID taskId) {}
}
