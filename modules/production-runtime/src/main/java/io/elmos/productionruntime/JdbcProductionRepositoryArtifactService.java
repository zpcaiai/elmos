package io.elmos.productionruntime;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Objects;
import java.util.UUID;

/** PostgreSQL adapter for immutable source/output lineage and validation state. */
public final class JdbcProductionRepositoryArtifactService implements ProductionRepositoryArtifactPort {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcProductionRepositoryArtifactService(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public UUID registerSnapshot(ProductionRuntimeModels.RepositorySnapshotRequest request) {
        return inTenant(request.tenantId(), () -> {
            assertProject(request.tenantId(), request.projectId());
            return jdbc.sql("insert into project.repository_snapshots (tenant_id, project_id, git_commit_sha, snapshot_hash, object_uri, total_files, total_loc, total_bytes) values (:tenantId, :projectId, :commit, :hash, :uri, :files, :loc, :bytes) on conflict (project_id, snapshot_hash) do update set object_uri = excluded.object_uri, total_files = excluded.total_files, total_loc = excluded.total_loc, total_bytes = excluded.total_bytes returning id")
                    .param("tenantId", request.tenantId()).param("projectId", request.projectId()).param("commit", request.gitCommitSha()).param("hash", request.snapshotHash()).param("uri", request.objectUri()).param("files", request.totalFiles()).param("loc", request.totalLoc()).param("bytes", request.totalBytes()).query(UUID.class).single();
        });
    }

    @Override
    public void bindInputSnapshot(UUID tenantId, UUID jobId, UUID snapshotId) {
        inTenant(tenantId, () -> {
            int updated = jdbc.sql("update orchestration.jobs j set input_snapshot_id = :snapshotId, updated_at = now() where j.tenant_id = :tenantId and j.id = :jobId and exists (select 1 from project.repository_snapshots s where s.tenant_id = j.tenant_id and s.project_id = j.project_id and s.id = :snapshotId)")
                    .param("tenantId", tenantId).param("jobId", jobId).param("snapshotId", snapshotId).update();
            if (updated != 1) throw new ProductionRuntimeException("SNAPSHOT_JOB_MISMATCH", "snapshot is not owned by the job project");
            return null;
        });
    }

    @Override
    public UUID registerArtifact(ProductionRuntimeModels.ArtifactRequest request) {
        return inTenant(request.tenantId(), () -> {
            assertProject(request.tenantId(), request.projectId());
            return jdbc.sql("insert into artifact.artifacts (tenant_id, project_id, job_id, work_item_id, artifact_type, object_uri, sha256, size_bytes) values (:tenantId, :projectId, :jobId, :workItemId, :type, :uri, :sha256, :sizeBytes) returning id")
                    .param("tenantId", request.tenantId()).param("projectId", request.projectId()).param("jobId", request.jobId()).param("workItemId", request.workItemId()).param("type", request.artifactType()).param("uri", request.objectUri()).param("sha256", request.sha256()).param("sizeBytes", request.sizeBytes()).query(UUID.class).single();
        });
    }

    @Override
    public UUID startValidation(ProductionRuntimeModels.ValidationRunRequest request) {
        return inTenant(request.tenantId(), () -> {
            assertJob(request.tenantId(), request.jobId());
            return jdbc.sql("insert into validation.validation_runs (tenant_id, job_id, validation_type) values (:tenantId, :jobId, :type) returning id")
                    .param("tenantId", request.tenantId()).param("jobId", request.jobId()).param("type", request.validationType()).query(UUID.class).single();
        });
    }

    @Override
    public void completeValidation(UUID tenantId, UUID validationRunId, long passed, long failed) {
        if (passed < 0 || failed < 0) throw new IllegalArgumentException("validation counts must be non-negative");
        inTenant(tenantId, () -> {
            int updated = jdbc.sql("update validation.validation_runs set status = case when :failed = 0 then 'PASSED' else 'FAILED' end, passed = :passed, failed = :failed, completed_at = now() where tenant_id = :tenantId and id = :id and status = 'CREATED'")
                    .param("failed", failed).param("passed", passed).param("tenantId", tenantId).param("id", validationRunId).update();
            if (updated != 1) throw new ProductionRuntimeException("VALIDATION_STATE_CONFLICT", "validation run is not open");
            return null;
        });
    }

    private void assertProject(UUID tenantId, UUID projectId) { jdbc.sql("select 1 from project.projects where tenant_id = :tenantId and id = :projectId").param("tenantId", tenantId).param("projectId", projectId).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("PROJECT_NOT_FOUND", "project is not owned by tenant")); }
    private void assertJob(UUID tenantId, UUID jobId) { jdbc.sql("select 1 from orchestration.jobs where tenant_id = :tenantId and id = :jobId").param("tenantId", tenantId).param("jobId", jobId).query(Integer.class).optional().orElseThrow(() -> new ProductionRuntimeException("JOB_NOT_FOUND", "job is not owned by tenant")); }
    private <T> T inTenant(UUID tenantId, java.util.function.Supplier<T> body) { return transactions.execute(status -> { jdbc.sql("select set_config('app.tenant_id', :tenantId, true)").param("tenantId", tenantId.toString()).query(String.class).single(); return body.get(); }); }
}
