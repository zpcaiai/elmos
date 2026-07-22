package io.elmos.persistence;

import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotPorts;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;

@Repository
public final class JdbcSnapshotStore implements SnapshotPorts.SnapshotStore {
    private final JdbcClient jdbc;
    public JdbcSnapshotStore(JdbcClient jdbc) { this.jdbc = jdbc; }

    @Override public SnapshotModel.RepositorySnapshot findReusable(String repositoryId, String commitSha, int schemaVersion) {
        return jdbc.sql("""
                select snapshot_id, organization_id, repository_id, requested_ref, commit_sha, tree_sha,
                       archive_artifact_ref, archive_sha256, archive_size, manifest_artifact_ref, manifest_sha256,
                       snapshot_schema_version, status, captured_at
                from repository_snapshots where repository_id = :repository and commit_sha = :commit and snapshot_schema_version = :version
                """).param("repository", repositoryId).param("commit", commitSha).param("version", schemaVersion)
                .query(JdbcSnapshotStore::map).optional().orElse(null);
    }

    @Override @Transactional public SnapshotModel.RepositorySnapshot saveAvailable(SnapshotModel.RepositorySnapshot snapshot) {
        if (snapshot.status() != SnapshotModel.Status.AVAILABLE) throw new IllegalArgumentException("only available immutable snapshots may be stored");
        jdbc.sql("""
                insert into repository_snapshots(snapshot_id, organization_id, repository_id, commit_sha, requested_ref,
                    captured_at, build_files_hash, archive_artifact_ref, tree_sha, archive_sha256, archive_size,
                    manifest_artifact_ref, manifest_sha256, snapshot_schema_version, status)
                values (:id, :organization, :repository, :commit, :ref, :captured, :buildHash, :archiveRef, :tree,
                    :archiveHash, :archiveSize, :manifestRef, :manifestHash, :version, 'AVAILABLE')
                on conflict (repository_id, commit_sha, snapshot_schema_version) do nothing
                """).param("id", snapshot.snapshotId()).param("organization", snapshot.organizationId())
                .param("repository", snapshot.repositoryId()).param("commit", snapshot.resolvedCommitSha())
                .param("ref", snapshot.requestedRef()).param("captured", snapshot.capturedAt())
                .param("buildHash", "sha256:" + snapshot.manifestSha256()).param("archiveRef", snapshot.archiveArtifactRef())
                .param("tree", snapshot.treeSha()).param("archiveHash", snapshot.archiveSha256()).param("archiveSize", snapshot.archiveSize())
                .param("manifestRef", snapshot.manifestArtifactRef()).param("manifestHash", snapshot.manifestSha256())
                .param("version", snapshot.snapshotSchemaVersion()).update();
        SnapshotModel.RepositorySnapshot stored = findReusable(snapshot.repositoryId(), snapshot.resolvedCommitSha(), snapshot.snapshotSchemaVersion());
        if (stored == null || !stored.archiveSha256().equals(snapshot.archiveSha256()) || !stored.manifestSha256().equals(snapshot.manifestSha256()))
            throw new SecurityException("snapshot content conflict for immutable commit identity");
        return stored;
    }

    private static SnapshotModel.RepositorySnapshot map(ResultSet result, int row) throws SQLException {
        return new SnapshotModel.RepositorySnapshot(result.getString("snapshot_id"), result.getString("organization_id"),
                result.getString("repository_id"), result.getString("requested_ref"), result.getString("commit_sha"),
                result.getString("tree_sha"), result.getString("archive_artifact_ref"), result.getString("archive_sha256"),
                result.getLong("archive_size"), result.getString("manifest_artifact_ref"), result.getString("manifest_sha256"),
                result.getInt("snapshot_schema_version"), SnapshotModel.Status.valueOf(result.getString("status")),
                result.getObject("captured_at", OffsetDateTime.class).toInstant());
    }
}
