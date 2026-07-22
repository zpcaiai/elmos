package io.elmos.planning;

public interface MigrationPlanStore {
    record SaveContext(String organizationId, int planVersion, String compatibilityMatrixVersion,
                       String planArtifactRef, String planSha256) {}
    void save(PlanningModels.MigrationPlan plan, SaveContext context);
}
