package io.elmos.snapshot;

import io.elmos.scm.EphemeralCredential;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
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
    private final SnapshotPorts.ArtifactStore artifacts; private final SnapshotPorts.SnapshotStore snapshots;
    private final SnapshotLifecyclePorts.SnapshotCommitCoordinator commits;
    private final SnapshotLifecyclePorts.RootReconciliationJournal reconciliations;
    private final boolean requireAuthoritativeSourceLease;
    private final Clock clock;

    public SnapshotCaptureService(SnapshotPorts.RepositoryCredentialBroker credentials, SnapshotPorts.RefResolver refs,
            SnapshotPorts.SourceFetcher fetcher, DeterministicSnapshotArchiver archiver,
            SnapshotPorts.ArtifactStore artifacts, SnapshotPorts.SnapshotStore snapshots,
            SnapshotLifecyclePorts.SnapshotCommitCoordinator commits,
            SnapshotLifecyclePorts.RootReconciliationJournal reconciliations,
            Clock clock) {
        this(credentials, refs, fetcher, archiver, artifacts, snapshots, commits,
                reconciliations, false, clock);
    }

    public SnapshotCaptureService(SnapshotPorts.RepositoryCredentialBroker credentials,
            SnapshotPorts.RefResolver refs, SnapshotPorts.SourceFetcher fetcher,
            DeterministicSnapshotArchiver archiver,
            SnapshotPorts.ArtifactStore artifacts, SnapshotPorts.SnapshotStore snapshots,
            SnapshotLifecyclePorts.SnapshotCommitCoordinator commits,
            SnapshotLifecyclePorts.RootReconciliationJournal reconciliations,
            boolean requireAuthoritativeSourceLease,
            Clock clock) {
        this.credentials = Objects.requireNonNull(credentials); this.refs = Objects.requireNonNull(refs); this.fetcher = Objects.requireNonNull(fetcher);
        this.archiver = Objects.requireNonNull(archiver); this.artifacts = Objects.requireNonNull(artifacts);
        this.snapshots = Objects.requireNonNull(snapshots);
        this.commits = Objects.requireNonNull(commits);
        this.reconciliations = Objects.requireNonNull(reconciliations);
        this.requireAuthoritativeSourceLease = requireAuthoritativeSourceLease;
        this.clock = Objects.requireNonNull(clock);
    }

    public SnapshotModel.RepositorySnapshot capture(CaptureRequest request) {
        validate(request);
        var resource = new SnapshotPorts.ArtifactResourceContext(
                request.organizationId(), request.repositoryId());
        try (EphemeralCredential credential = credentials.issue(
                request.organizationId(), request.repositoryId(),
                request.repositoryExternalId(), request.installationExternalId())) {
            SnapshotPorts.ResolvedRef resolved = refs.resolve(
                    resource, request.requestedRef(), credential);
            if (resolved.commitSha() == null || !resolved.commitSha().matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not resolve an immutable commit SHA");
            SnapshotModel.RepositorySnapshot reusable = snapshots.findReusable(
                    request.organizationId(), request.repositoryId(),
                    resolved.commitSha(), SCHEMA_VERSION);
            if (reusable != null) {
                if (requireAuthoritativeSourceLease) {
                    // The current snapshot schema predates durable source-lease provenance.
                    // Treat every existing row as UNKNOWN instead of laundering a historical
                    // local self-attestation through the production reuse path.
                    throw new SecurityException(
                            "reusable snapshot lacks authoritative source lease provenance");
                }
                if (reusable.status() != SnapshotModel.Status.AVAILABLE) throw new IllegalStateException("matching snapshot is not available");
                requireOwnedBy(resource, reusable);
                requireArtifactReferences(reusable);
                // Older snapshots may predate the CAS root lifecycle. Re-registering the
                // deterministic owner is idempotent and repairs that reachability gap before the
                // snapshot is handed to a caller.
                artifacts.retainSnapshotGeneration(
                        resource, reusable.snapshotId(), references(reusable));
                return reusable;
            }
            try (SnapshotPorts.FetchedSource source = fetcher.fetch(
                    resource, resolved, credential)) {
                String treeSha = source.treeSha() == null ? resolved.treeSha() : source.treeSha();
                if (treeSha == null || !treeSha.matches("[0-9a-f]{40}")) throw new SecurityException("SCM did not prove the snapshot tree SHA");
                var context = new DeterministicSnapshotArchiver.SnapshotContext("GITHUB", request.repositoryId(), request.repositoryFullName(),
                        request.requestedRef(), resolved.commitSha(), treeSha);
                var archive = requireAuthoritativeSourceLease
                        ? archiver.archive(source.path(), context, source.sourceLease())
                        : archiver.archive(source.path(), context);
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
                SnapshotPorts.ArtifactRetention retention = artifacts.retainSnapshotGeneration(
                        resource, snapshotId, references);
                SnapshotRootReconciliation reconciliation =
                        new SnapshotRootReconciliation(
                                reconciliationId(resource, snapshotId),
                                logicalOperationId(request),
                                SnapshotRootReconciliation.Kind.CAPTURE_COMMIT,
                                SnapshotRootReconciliation.Phase.PENDING,
                                snapshot, retention, null, clock.instant());
                try {
                    reconciliations.recordPending(reconciliation);
                } catch (RuntimeException journalFailure) {
                    try {
                        artifacts.releaseSnapshotGeneration(resource, retention);
                    } catch (RuntimeException releaseFailure) {
                        journalFailure.addSuppressed(releaseFailure);
                    }
                    throw journalFailure;
                }

                SnapshotModel.RepositorySnapshot stored;
                try {
                    // The coordinator must persist the snapshot and advance the journal to
                    // DATABASE_COMMITTED in one transaction. A timeout can therefore be resolved
                    // from the journal without guessing whether the database committed.
                    stored = commits.saveAvailable(reconciliation);
                } catch (RuntimeException failure) {
                    try {
                        // This conditional transition serializes with the coordinator's journal
                        // update. A committed database transaction wins; a rolled-back one becomes
                        // explicitly releasable by the reconciler.
                        reconciliations.markCommitFailed(
                                resource.organizationId(), reconciliation.reconciliationId());
                    } catch (RuntimeException journalFailure) {
                        failure.addSuppressed(journalFailure);
                    }
                    throw failure;
                }

                requirePersistedEquivalent(snapshot, stored);
                if (!snapshotId.equals(stored.snapshotId())) {
                    // A concurrent capture may have won the immutable snapshot key. Protect the
                    // winner under its durable owner before releasing our provisional owner.
                    // If this step fails, deliberately keep the provisional root: leaking bytes
                    // is safer than allowing GC to delete artifacts now referenced by the DB.
                    artifacts.retainSnapshotGeneration(
                            resource, stored.snapshotId(), references(stored));
                    artifacts.releaseSnapshotGeneration(resource, retention);
                }
                reconciliations.markResolved(
                        resource.organizationId(), reconciliation.reconciliationId());
                return stored;
            } catch (RuntimeException failure) { throw failure; }
            catch (Exception failure) { throw new IllegalStateException("snapshot staging cleanup failed", failure); }
        }
    }

    static List<String> references(SnapshotModel.RepositorySnapshot snapshot) {
        return List.of(snapshot.archiveArtifactRef(), snapshot.manifestArtifactRef());
    }

    static String reconciliationId(SnapshotPorts.ArtifactResourceContext resource,
                                   String snapshotId) {
        String preimage = "elmos-snapshot-root-reconciliation/1\n"
                + resource.organizationId() + "\n" + resource.repositoryId() + "\n"
                + snapshotId;
        return "snapshot-root-" + UUID.nameUUIDFromBytes(
                preimage.getBytes(StandardCharsets.UTF_8));
    }

    static String logicalOperationId(CaptureRequest request) {
        String preimage = "elmos-snapshot-capture-operation/1\n"
                + request.organizationId() + "\n" + request.repositoryId() + "\n"
                + request.idempotencyKey();
        return "snapshot-capture-" + UUID.nameUUIDFromBytes(
                preimage.getBytes(StandardCharsets.UTF_8));
    }

    static void requireOwnedBy(SnapshotPorts.ArtifactResourceContext resource,
                               SnapshotModel.RepositorySnapshot snapshot) {
        if (!resource.organizationId().equals(snapshot.organizationId())
                || !resource.repositoryId().equals(snapshot.repositoryId())) {
            throw new SecurityException("reusable snapshot belongs to another resource context");
        }
    }

    static void requirePersistedEquivalent(SnapshotModel.RepositorySnapshot intended,
                                           SnapshotModel.RepositorySnapshot stored) {
        requirePersistedContentEquivalent(intended, stored);
        if (stored.status() != SnapshotModel.Status.AVAILABLE) {
            throw new SecurityException("snapshot store returned a non-available snapshot");
        }
    }

    static void requirePersistedContentEquivalent(
            SnapshotModel.RepositorySnapshot intended,
            SnapshotModel.RepositorySnapshot stored
    ) {
        Objects.requireNonNull(stored, "snapshot store returned null");
        requireOwnedBy(new SnapshotPorts.ArtifactResourceContext(
                intended.organizationId(), intended.repositoryId()), stored);
        requireArtifactReferences(stored);
        if ((stored.status() != SnapshotModel.Status.AVAILABLE
                && stored.status() != SnapshotModel.Status.ARCHIVED)
                || !stored.resolvedCommitSha().equals(intended.resolvedCommitSha())
                || !Objects.equals(stored.treeSha(), intended.treeSha())
                || stored.snapshotSchemaVersion() != intended.snapshotSchemaVersion()
                || !stored.archiveSha256().equals(intended.archiveSha256())
                || stored.archiveSize() != intended.archiveSize()
                || !stored.manifestSha256().equals(intended.manifestSha256())) {
            throw new SecurityException("snapshot store returned a conflicting immutable snapshot");
        }
    }

    static void requireArtifactReferences(SnapshotModel.RepositorySnapshot snapshot) {
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
        // Validate the trusted tenant/resource binding before issuing a credential lease.
        new SnapshotPorts.ArtifactResourceContext(
                request.organizationId(), request.repositoryId());
    }
}
