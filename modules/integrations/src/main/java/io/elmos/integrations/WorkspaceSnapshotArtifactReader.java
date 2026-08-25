package io.elmos.integrations;

import io.elmos.cas.CasDigest;
import io.elmos.snapshot.SnapshotPorts;
import io.elmos.workspace.WorkspaceInfrastructurePorts;

import java.io.InputStream;
import java.util.Objects;

/**
 * Read-only workspace adapter for catalog-authorized snapshot artifacts.
 *
 * <p>Complete {@code cas://sha256/<hex>/<size>} references are always routed through the CAS
 * reader, which verifies the tenant/repository catalogue binding and the stored bytes. The
 * historical size-less {@code cas:sha256:<hex>} form is denied unless the deployment selects the
 * explicit verified-legacy compatibility policy. A sized CAS identity is matched to the
 * immutable database digest and size before backend access. A legacy reference has no size, so
 * its digest is matched here and the materializer independently enforces the database size while
 * consuming the already digest-verified legacy stream.
 */
public final class WorkspaceSnapshotArtifactReader
        implements WorkspaceInfrastructurePorts.SnapshotArtifactReader {

    public enum LegacyCompatibilityPolicy {
        DENY,
        ALLOW_VERIFIED
    }

    private static final String LEGACY_PREFIX = "cas:sha256:";

    private final SnapshotPorts.ArtifactReader casReader;
    private final SnapshotPorts.ArtifactReader legacyReader;
    private final LegacyCompatibilityPolicy legacyPolicy;
    private final long maximumArtifactBytes;

    public WorkspaceSnapshotArtifactReader(
            SnapshotPorts.ArtifactReader casReader,
            SnapshotPorts.ArtifactReader legacyReader,
            LegacyCompatibilityPolicy legacyPolicy,
            long maximumArtifactBytes
    ) {
        this.casReader = Objects.requireNonNull(casReader, "casReader");
        this.legacyPolicy = Objects.requireNonNull(legacyPolicy, "legacyPolicy");
        if (legacyPolicy == LegacyCompatibilityPolicy.ALLOW_VERIFIED
                && legacyReader == null) {
            throw new IllegalArgumentException(
                    "verified legacy compatibility requires a legacy reader");
        }
        this.legacyReader = legacyReader;
        if (maximumArtifactBytes < 1 || maximumArtifactBytes > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "workspace snapshot artifact limit is outside policy");
        }
        this.maximumArtifactBytes = maximumArtifactBytes;
    }

    @Override
    public InputStream open(WorkspaceInfrastructurePorts.SnapshotArtifact artifact) {
        Objects.requireNonNull(artifact, "artifact");
        if (artifact.sizeBytes() > maximumArtifactBytes) {
            throw unavailable();
        }
        SnapshotPorts.ArtifactResourceContext resource =
                new SnapshotPorts.ArtifactResourceContext(
                        artifact.organizationId(), artifact.repositoryId());
        String reference = artifact.reference();
        if (reference.startsWith(CasBackedArtifactStore.SCHEME)) {
            CasDigest digest = parseCas(reference);
            requireDatabaseIdentity(artifact, digest.hex(), digest.sizeBytes());
            return casReader.open(resource, reference);
        }
        if (reference.matches(LEGACY_PREFIX + "[0-9a-f]{64}")) {
            if (legacyPolicy != LegacyCompatibilityPolicy.ALLOW_VERIFIED) {
                throw unavailable();
            }
            requireDatabaseIdentity(
                    artifact, reference.substring(LEGACY_PREFIX.length()),
                    artifact.sizeBytes());
            return Objects.requireNonNull(legacyReader, "legacyReader")
                    .open(resource, reference);
        }
        throw unavailable();
    }

    private static CasDigest parseCas(String reference) {
        try {
            return CasBackedArtifactStore.parse(reference);
        } catch (IllegalArgumentException malformed) {
            throw unavailable();
        }
    }

    private static void requireDatabaseIdentity(
            WorkspaceInfrastructurePorts.SnapshotArtifact artifact,
            String referenceSha256,
            long referenceSize
    ) {
        if (!artifact.sha256().equals(referenceSha256)
                || artifact.sizeBytes() != referenceSize) {
            throw unavailable();
        }
    }

    private static SecurityException unavailable() {
        return new SecurityException(
                "snapshot artifact is unavailable for workspace resource context");
    }
}
