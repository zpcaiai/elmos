package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;

import java.io.ByteArrayInputStream;
import java.time.Clock;
import java.util.Objects;
import java.util.UUID;

public final class SnapshotCaptureService {
    public record CaptureRequest(String organizationId, String repositoryId, long repositoryExternalId,
                                 long installationExternalId, String repositoryFullName, String requestedRef,
                                 String correlationId, String idempotencyKey) {}
    private static final int SCHEMA_VERSION = 1;
    private final SnapshotPorts.RepositoryCredentialBroker credentials; private final SnapshotPorts.RefResolver refs;
    private final SnapshotPorts.SourceFetcher fetcher; private final DeterministicSnapshotArchiver archiver;
    private final SnapshotPorts.ArtifactStore artifacts; private final SnapshotPorts.SnapshotStore snapshots; private final Clock clock;

    public SnapshotCaptureService(SnapshotPorts.RepositoryCredentialBroker credentials, SnapshotPorts.RefResolver refs,
            SnapshotPorts.SourceFetcher fetcher, DeterministicSnapshotArchiver archiver,
            SnapshotPorts.ArtifactStore artifacts, SnapshotPorts.SnapshotStore snapshots, Clock clock) {
        this.credentials = Objects.requireNonNull(credentials); this.refs = Objects.requireNonNull(refs); this.fetcher = Objects.requireNonNull(fetcher);
        this.archiver = Objects.requireNonNull(archiver); this.artifacts = Objects.requireNonNull(artifacts);
        this.snapshots = Objects.requireNonNull(snapshots); this.clock = Objects.requireNonNull(clock);
    }

    public SnapshotModel.RepositorySnapshot capture(CaptureRequest request) {
        validate(request);
        try (EphemeralCredential credential = credentials.issue(request.repositoryId(), request.repositoryExternalId(), request.installationExternalId())) {
            SnapshotPorts.ResolvedRef resolved = refs.resolve(request.repositoryId(), request.requestedRef(), credential);
            if (resolved.commitSha() == null || !resolved.commitSha().matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not resolve an immutable commit SHA");
            SnapshotModel.RepositorySnapshot reusable = snapshots.findReusable(request.repositoryId(), resolved.commitSha(), SCHEMA_VERSION);
            if (reusable != null) {
                if (reusable.status() != SnapshotModel.Status.AVAILABLE) throw new IllegalStateException("matching snapshot is not available");
                return reusable;
            }
            try (SnapshotPorts.FetchedSource source = fetcher.fetch(request.repositoryId(), resolved, credential)) {
                String treeSha = source.treeSha() == null ? resolved.treeSha() : source.treeSha();
                if (treeSha == null || !treeSha.matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not prove the snapshot tree SHA");
                var context = new DeterministicSnapshotArchiver.SnapshotContext("GITHUB", request.repositoryId(), request.repositoryFullName(),
                        request.requestedRef(), resolved.commitSha(), treeSha);
                var archive = archiver.archive(source.path(), context);
                byte[] archiveBytes = archive.archive(), manifestBytes = archive.manifest();
                String archiveRef = artifacts.putIfAbsent(archive.archiveSha256(), archiveBytes.length,
                        new ByteArrayInputStream(archiveBytes), "application/zstd");
                String manifestRef = artifacts.putIfAbsent(archive.manifestSha256(), manifestBytes.length,
                        new ByteArrayInputStream(manifestBytes), "application/json");
                var snapshot = new SnapshotModel.RepositorySnapshot("snapshot-" + UUID.randomUUID(), request.organizationId(),
                        request.repositoryId(), request.requestedRef(), resolved.commitSha(), treeSha, archiveRef,
                        archive.archiveSha256(), archiveBytes.length, manifestRef, archive.manifestSha256(), SCHEMA_VERSION,
                        SnapshotModel.Status.AVAILABLE, clock.instant());
                return snapshots.saveAvailable(snapshot);
            } catch (RuntimeException failure) { throw failure; }
            catch (Exception failure) { throw new IllegalStateException("snapshot staging cleanup failed", failure); }
        }
    }

    private static void validate(CaptureRequest request) {
        Objects.requireNonNull(request);
        if (request.organizationId() == null || request.organizationId().isBlank() || request.repositoryId() == null || request.repositoryId().isBlank()
                || request.repositoryFullName() == null || !request.repositoryFullName().matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
                || request.requestedRef() == null || request.requestedRef().isBlank() || request.correlationId() == null || request.correlationId().isBlank()
                || request.idempotencyKey() == null || request.idempotencyKey().isBlank()) throw new IllegalArgumentException("snapshot capture identity is incomplete");
    }
}
