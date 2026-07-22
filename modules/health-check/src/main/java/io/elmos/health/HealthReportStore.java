package io.elmos.health;

public interface HealthReportStore {
    record SaveContext(String organizationId, String correlationId, String scannerVersion,
                       String policyHash, String reportArtifactRef, String reportSha256) {}
    void save(HealthModels.LegacyHealthReport report, SaveContext context);
}
