package io.elmos.workspaceservice;

import io.elmos.cas.TenantCasStore;
import io.elmos.cas.TenantEncryptedLocalCasStore;
import io.elmos.integrations.LocalContentAddressedArtifactStore;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import javax.sql.DataSource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class WorkspaceSnapshotArtifactConfigurationTest {

    @TempDir
    Path temporary;

    @Test
    void dockerWorkspaceDefaultsToOneCasOnlyReader() {
        runner(false).run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(1, context.getBeansOfType(
                    WorkspaceInfrastructurePorts.SnapshotArtifactReader.class).size());
            assertTrue(context.getBeansOfType(
                    LocalContentAddressedArtifactStore.class).isEmpty());
            var status = context.getBean(
                    WorkspaceSnapshotArtifactConfiguration.WorkspaceSnapshotReaderStatus.class);
            assertEquals("CAS_ONLY", status.mode());
            assertEquals("SINGLE_HOST", status.storageScope());
            assertFalse(status.productionCertified());
        });
    }

    @Test
    void legacyReaderExistsOnlyUnderExplicitCompatibilityProperty() {
        runner(true).run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(1, context.getBeansOfType(
                    WorkspaceInfrastructurePorts.SnapshotArtifactReader.class).size());
            assertEquals(1, context.getBeansOfType(
                    LocalContentAddressedArtifactStore.class).size());
            var status = context.getBean(
                    WorkspaceSnapshotArtifactConfiguration.WorkspaceSnapshotReaderStatus.class);
            assertEquals("CAS_WITH_VERIFIED_LEGACY", status.mode());
            assertEquals("EXPLICIT_ENABLED", status.legacyCompatibility());
            assertFalse(status.productionCertified());
        });
    }

    @Test
    void dockerWorkspaceFailsClosedWhenCasRootIsMissing() {
        new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.data-residency=cn-north")
                .run(context -> assertNotNull(context.getStartupFailure()));
    }

    @Test
    void plaintextSingleHostStoreRequiresExplicitDeploymentAcknowledgement() {
        new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root="
                                + temporary.resolve("implicit-plaintext"),
                        "elmos.workspace.snapshot-cas.data-residency=cn-north")
                .run(context -> assertNotNull(context.getStartupFailure()));
    }

    @Test
    void legacyCompatibilityRejectsOverlappingCasAndLegacyRoots() {
        Path shared = temporary.resolve("overlap");
        new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root=" + shared,
                        "elmos.workspace.snapshot-cas.data-residency=cn-north",
                        "elmos.workspace.snapshot-cas.allow-unencrypted-single-host=true",
                        "elmos.workspace.snapshot-legacy-compatibility-enabled=true",
                        "elmos.workspace.snapshot-artifact-root=" + shared.resolve("legacy"))
                .run(context -> assertNotNull(context.getStartupFailure()));
    }

    @Test
    void legacyCompatibilityRejectsParentSymlinkAliases() throws Exception {
        Path real = temporary.resolve("real-storage");
        Files.createDirectories(real.resolve("cas"));
        Path alias = temporary.resolve("storage-alias");
        Files.createSymbolicLink(alias, real);
        new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root=" + real.resolve("cas"),
                        "elmos.workspace.snapshot-cas.data-residency=cn-north",
                        "elmos.workspace.snapshot-cas.allow-unencrypted-single-host=true",
                        "elmos.workspace.snapshot-legacy-compatibility-enabled=true",
                        "elmos.workspace.snapshot-artifact-root="
                                + alias.resolve("cas/legacy"))
                .run(context -> assertNotNull(context.getStartupFailure()));
    }

    @Test
    void directoryEncryptionCreatesOneTenantCiphertextStoreAndReportsProtection()
            throws Exception {
        Path cas = temporary.resolve("encrypted-cas");
        Path keys = temporary.resolve("tenant-keys");
        Files.createDirectory(keys);
        new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root=" + cas,
                        "elmos.workspace.snapshot-cas.data-residency=cn-north",
                        "elmos.workspace.snapshot-cas.encryption.enabled=true",
                        "elmos.workspace.snapshot-cas.encryption.provider=DIRECTORY",
                        "elmos.workspace.snapshot-cas.encryption.key-directory=" + keys)
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertEquals(1, context.getBeansOfType(TenantCasStore.class).size());
                    assertTrue(context.getBean(TenantCasStore.class)
                            instanceof TenantEncryptedLocalCasStore);
                    assertEquals("TENANT_AES_256_GCM", context.getBean(
                                    WorkspaceSnapshotArtifactConfiguration
                                            .WorkspaceSnapshotReaderStatus.class)
                            .atRestProtection());
                });
    }

    @Test
    void kmsModeFailsClosedWithoutAWorkloadMtlsProvider() {
        new ApplicationContextRunner()
                .withUserConfiguration(
                        WorkspaceSnapshotArtifactConfiguration.class,
                        WorkspaceSnapshotKmsBrokerConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root="
                                + temporary.resolve("kms-cas"),
                        "elmos.workspace.snapshot-cas.data-residency=cn-north",
                        "elmos.workspace.snapshot-cas.encryption.enabled=true",
                        "elmos.workspace.snapshot-cas.encryption.provider=KMS",
                        "elmos.workspace.snapshot-cas.encryption.kms-broker.endpoint=https://kms.example",
                        "elmos.workspace.snapshot-cas.encryption.kms-broker.workload-spiffe-id=spiffe://example/elmos/workspace",
                        "elmos.workspace.snapshot-cas.encryption.kms-broker.mtls-secret-reference=secretref://kms/mtls",
                        "elmos.workspace.snapshot-cas.encryption.kms-broker.authorization-secret-reference=secretref://kms/auth")
                .run(context -> assertNotNull(context.getStartupFailure()));
    }

    private ApplicationContextRunner runner(boolean legacyCompatibility) {
        Path cas = temporary.resolve(legacyCompatibility ? "cas-with-legacy" : "cas-only");
        Path legacy = temporary.resolve("legacy");
        return new ApplicationContextRunner()
                .withUserConfiguration(WorkspaceSnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withPropertyValues(
                        "elmos.workspace.docker.enabled=true",
                        "elmos.workspace.snapshot-cas.root=" + cas,
                        "elmos.workspace.snapshot-cas.data-residency=cn-north",
                        "elmos.workspace.snapshot-cas.allow-unencrypted-single-host=true",
                        "elmos.workspace.snapshot-legacy-compatibility-enabled="
                                + legacyCompatibility,
                        "elmos.workspace.snapshot-artifact-root=" + legacy);
    }
}
