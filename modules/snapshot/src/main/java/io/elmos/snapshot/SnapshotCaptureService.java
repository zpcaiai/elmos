package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;

import java.io.ByteArrayInputStream;
import java.time.Clock;
import java.util.List;
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
        try (EphemeralCredential credential = credentials.issue(
                request.organizationId(), request.repositoryId(),
                request.repositoryExternalId(), request.installationExternalId())) {
            SnapshotPorts.ResolvedRef resolved = refs.resolve(request.repositoryId(), request.requestedRef(), credential);
            if (resolved.commitSha() == null || !resolved.commitSha().matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not resolve an immutable commit SHA");
            var resource = new SnapshotPorts.ArtifactResourceContext(
                    request.organizationId(), request.repositoryId());
            SnapshotModel.RepositorySnapshot reusable = snapshots.findReusable(request.repositoryId(), resolved.commitSha(), SCHEMA_VERSION);
            if (reusable != null) {
                if (reusable.status() != SnapshotModel.Status.AVAILABLE) throw new IllegalStateException("matching snapshot is not available");
                requireOwnedBy(resource, reusable);
                requireArtifactReferences(reusable);
                // Older snapshots may predate the CAS root lifecycle. Re-registering the
                // deterministic owner is idempotent and repairs that reachability gap before the
                // snapshot is handed to a caller.
                artifacts.retainSnapshot(resource, reusable.snapshotId(), references(reusable));
                return reusable;
            }
            try (SnapshotPorts.FetchedSource source = fetcher.fetch(request.repositoryId(), resolved, credential)) {
                String treeSha = source.treeSha() == null ? resolved.treeSha() : source.treeSha();
                if (treeSha == null || !treeSha.matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not prove the snapshot tree SHA");
                var context = new DeterministicSnapshotArchiver.SnapshotContext("GITHUB", request.repositoryId(), request.repositoryFullName(),
                        request.requestedRef(), resolved.commitSha(), treeSha);
                var archive = archiver.archive(source.path(), context);
                byte[] archiveBytes = archive.archive(), manifestBytes = archive.manifest();
                String snapshotId = "snapshot-" + UUID.randomUUID();
                String archiveRef = artifacts.putIfAbsent(resource, archive.archiveSha256(), archiveBytes.length,
                        new ByteArrayInputStream(archiveBytes), "application/zstd");
                String manifestRef = artifacts.putIfAbsent(resource, archive.manifestSha256(), manifestBytes.length,
                        new ByteArrayInputStream(manifestBytes), "application/json");
                var snapshot = new SnapshotModel.RepositorySnapshot(snapshotId, request.organizationId(),
                        request.repositoryId(), request.requestedRef(), resolved.commitSha(), treeSha, archiveRef,
                        archive.archiveSha256(), archiveBytes.length, manifestRef, archive.manifestSha256(), SCHEMA_VERSION,
                        SnapshotModel.Status.AVAILABLE, clock.instant());
                requireArtifactReferences(snapshot);
                List<String> references = references(snapshot);
                // retainSnapshot is an all-or-none contract. A rejected batch leaves no partial
                // roots for the caller to clean up (and therefore cannot accidentally release a
                // pre-existing idempotent root with the same owner).
                artifacts.retainSnapshot(resource, snapshotId, references);

                SnapshotModel.RepositorySnapshot stored;
                try {
                    stored = snapshots.saveAvailable(snapshot);
                } catch (RuntimeException failure) {
                    // A thrown database call does not prove the commit failed: the server may
                    // have committed and the acknowledgement may have been lost. Keep the
                    // provisional root for reconciliation. A bounded storage leak is safer than
                    // making a durable snapshot reference collectable.
                    throw failure;
                }

                requirePersistedEquivalent(snapshot, stored);
                if (!snapshotId.equals(stored.snapshotId())) {
                    // A concurrent capture may have won the immutable snapshot key. Protect the
                    // winner under its durable owner before releasing our provisional owner.
                    // If this step fails, deliberately keep the provisional root: leaking bytes
                    // is safer than allowing GC to delete artifacts now referenced by the DB.
                    artifacts.retainSnapshot(resource, stored.snapshotId(), references(stored));
                    artifacts.releaseSnapshot(resource, snapshotId);
                }
                return stored;
            } catch (RuntimeException failure) { throw failure; }
            catch (Exception failure) { throw new IllegalStateException("snapshot staging cleanup failed", failure); }
        }
    }

    private static List<String> references(SnapshotModel.RepositorySnapshot snapshot) {
        return List.of(snapshot.archiveArtifactRef(), snapshot.manifestArtifactRef());
    }

    private static void requireOwnedBy(SnapshotPorts.ArtifactResourceContext resource,
                                       SnapshotModel.RepositorySnapshot snapshot) {
        if (!resource.organizationId().equals(snapshot.organizationId())
                || !resource.repositoryId().equals(snapshot.repositoryId())) {
            throw new SecurityException("reusable snapshot belongs to another resource context");
        }
    }

    private static void requirePersistedEquivalent(SnapshotModel.RepositorySnapshot intended,
                                                   SnapshotModel.RepositorySnapshot stored) {
        Objects.requireNonNull(stored, "snapshot store returned null");
        requireOwnedBy(new SnapshotPorts.ArtifactResourceContext(
                intended.organizationId(), intended.repositoryId()), stored);
        requireArtifactReferences(stored);
        if (stored.status() != SnapshotModel.Status.AVAILABLE
                || !stored.resolvedCommitSha().equals(intended.resolvedCommitSha())
                || !stored.treeSha().equals(intended.treeSha())
                || stored.snapshotSchemaVersion() != intended.snapshotSchemaVersion()
                || !stored.archiveSha256().equals(intended.archiveSha256())
                || stored.archiveSize() != intended.archiveSize()
                || !stored.manifestSha256().equals(intended.manifestSha256())) {
            throw new SecurityException("snapshot store returned a conflicting immutable snapshot");
        }
    }

    private static void requireArtifactReferences(SnapshotModel.RepositorySnapshot snapshot) {
        requireReferenceIdentity(snapshot.archiveArtifactRef(), snapshot.archiveSha256(),
                snapshot.archiveSize(), "archive");
        requireReferenceIdentity(snapshot.manifestArtifactRef(), snapshot.manifestSha256(),
                -1, "manifest");
    }

    private static void requireReferenceIdentity(String reference,
                                                 String expectedSha256,
                                                 long expectedSize,
                                                 String label) {
        if (reference != null && reference.matches("cas:sha256:[0-9a-f]{64}")) {
            if (!reference.substring("cas:sha256:".length()).equals(expectedSha256)) {
                throw new SecurityException(label + " reference digest conflicts with metadata");
            }
            return;
        }
        if (reference == null || !reference.startsWith("cas://sha256/")) {
            throw new SecurityException(label + " reference scheme is unsupported");
        }
        String[] parts = reference.substring("cas://sha256/".length()).split("/", -1);
        if (parts.length != 2 || !parts[0].matches("[0-9a-f]{64}")
                || !parts[1].matches("0|[1-9][0-9]*")
                || !parts[0].equals(expectedSha256)) {
            throw new SecurityException(label + " CAS reference conflicts with metadata");
        }
        try {
            long referencedSize = Long.parseLong(parts[1]);
            if (expectedSize >= 0 && referencedSize != expectedSize) {
                throw new SecurityException(label + " reference size conflicts with metadata");
            }
        } catch (NumberFormatException invalidSize) {
            throw new SecurityException(label + " reference size is invalid", invalidSize);
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
