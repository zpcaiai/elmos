package io.elmos.integrations;

import io.elmos.cas.CasDigest;
import io.elmos.snapshot.SnapshotPorts;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class WorkspaceSnapshotArtifactReaderTest {

    private static final byte[] CONTENT =
            "verified workspace snapshot".getBytes(StandardCharsets.UTF_8);
    private static final CasDigest DIGEST = CasDigest.of(CONTENT);
    private static final String CAS_REFERENCE = CasBackedArtifactStore.reference(DIGEST);
    private static final String LEGACY_REFERENCE = "cas:sha256:" + DIGEST.hex();

    @Test
    void sizedCasReferenceCarriesExactTenantAndRepositoryToCasReader() throws Exception {
        AtomicReference<SnapshotPorts.ArtifactResourceContext> observed =
                new AtomicReference<>();
        SnapshotPorts.ArtifactReader cas = (resource, reference) -> {
            observed.set(resource);
            assertEquals(CAS_REFERENCE, reference);
            return new ByteArrayInputStream(CONTENT);
        };
        var reader = new WorkspaceSnapshotArtifactReader(
                cas, null,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                1024);

        assertArrayEquals(CONTENT, reader.open(artifact(CAS_REFERENCE)).readAllBytes());
        assertEquals("tenant-a", observed.get().organizationId());
        assertEquals("repo-a", observed.get().repositoryId());
    }

    @Test
    void casReferenceMustMatchImmutableDatabaseDigestAndSize() {
        SnapshotPorts.ArtifactReader cas = (resource, reference) -> {
            throw new AssertionError("mismatched identity must fail before backend access");
        };
        var reader = new WorkspaceSnapshotArtifactReader(
                cas, null,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                1024);

        assertThrows(SecurityException.class,
                () -> reader.open(new WorkspaceInfrastructurePorts.SnapshotArtifact(
                        "tenant-a", "repo-a", "run-a", "snapshot-a", CAS_REFERENCE,
                        "f".repeat(64), DIGEST.sizeBytes())));
        String wrongSize = "cas://sha256/" + DIGEST.hex() + "/" + (DIGEST.sizeBytes() + 1);
        assertThrows(SecurityException.class, () -> reader.open(artifact(wrongSize)));
    }

    @Test
    void legacyReferenceIsDeniedUnlessVerifiedCompatibilityIsExplicit() throws Exception {
        SnapshotPorts.ArtifactReader legacy = (resource, reference) ->
                new ByteArrayInputStream(CONTENT);
        var denied = new WorkspaceSnapshotArtifactReader(
                (resource, reference) -> {
                    throw new AssertionError("legacy reference cannot reach CAS backend");
                }, legacy, WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                1024);
        assertThrows(SecurityException.class,
                () -> denied.open(artifact(LEGACY_REFERENCE)));

        AtomicReference<SnapshotPorts.ArtifactResourceContext> observed =
                new AtomicReference<>();
        var allowed = new WorkspaceSnapshotArtifactReader(
                (resource, reference) -> {
                    throw new AssertionError("legacy reference cannot reach CAS backend");
                }, (resource, reference) -> {
                    observed.set(resource);
                    assertEquals(LEGACY_REFERENCE, reference);
                    return new ByteArrayInputStream(CONTENT);
                }, WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.ALLOW_VERIFIED,
                1024);
        assertArrayEquals(CONTENT,
                allowed.open(artifact(LEGACY_REFERENCE)).readAllBytes());
        assertEquals("tenant-a", observed.get().organizationId());
        assertEquals("repo-a", observed.get().repositoryId());
    }

    @Test
    void malformedOrUnknownReferencesFailBeforeBackendAccess() {
        SnapshotPorts.ArtifactReader backend = (resource, reference) -> {
            throw new AssertionError("malformed reference must fail before backend access");
        };
        var reader = new WorkspaceSnapshotArtifactReader(
                backend, null,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                1024);

        assertThrows(SecurityException.class,
                () -> reader.open(artifact("cas://sha256/" + DIGEST.hex())));
        assertThrows(SecurityException.class,
                () -> reader.open(artifact("file:///tmp/archive")));
    }

    @Test
    void artifactLargerThanWorkspaceReadPolicyFailsBeforeBackendAccess() {
        SnapshotPorts.ArtifactReader backend = (resource, reference) -> {
            throw new AssertionError("oversized artifact must fail before backend access");
        };
        var reader = new WorkspaceSnapshotArtifactReader(
                backend, null,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                CONTENT.length - 1L);

        assertThrows(SecurityException.class,
                () -> reader.open(artifact(CAS_REFERENCE)));
    }

    @Test
    void emptyArchiveIdentityIsRejectedBeforeAnyReaderCanOpenIt() {
        assertThrows(IllegalArgumentException.class,
                () -> new WorkspaceInfrastructurePorts.SnapshotArtifact(
                        "tenant-a", "repo-a", "run-a", "snapshot-a",
                        "cas://sha256/" + "0".repeat(64) + "/0",
                        "0".repeat(64), 0));
    }

    @Test
    void allowingLegacyWithoutVerifiedReaderFailsConfiguration() {
        assertThrows(IllegalArgumentException.class,
                () -> new WorkspaceSnapshotArtifactReader(
                        (resource, reference) -> new ByteArrayInputStream(CONTENT),
                        null,
                        WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.ALLOW_VERIFIED,
                        1024));
    }

    private static WorkspaceInfrastructurePorts.SnapshotArtifact artifact(String reference) {
        return new WorkspaceInfrastructurePorts.SnapshotArtifact(
                "tenant-a", "repo-a", "run-a", "snapshot-a", reference,
                DIGEST.hex(), DIGEST.sizeBytes());
    }
}
