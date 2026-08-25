package io.elmos.controlplane;

import io.elmos.cas.JdbcCasCatalog;
import io.elmos.cas.KmsTenantEncryption;
import io.elmos.cas.LocalDiskCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.cas.TenantEncryptedLocalCasStore;
import io.elmos.integrations.CasBackedArtifactStore;
import io.elmos.integrations.CompatibleSnapshotArtifactStore;
import io.elmos.integrations.LocalContentAddressedArtifactStore;
import io.elmos.snapshot.SnapshotPorts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import javax.sql.DataSource;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class SnapshotArtifactConfigurationTest {

    @TempDir
    Path temporary;

    private ApplicationContextRunner contextRunner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(SnapshotArtifactConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, () -> Clock.fixed(
                        Instant.parse("2026-08-20T00:00:00Z"), ZoneOffset.UTC))
                .withPropertyValues("elmos.github.app.enabled=true");
    }

    @Test
    void legacyStoreRemainsTheDefaultAndReportsItsActualBoundary() {
        contextRunner()
                .withPropertyValues(
                        "elmos.snapshot.artifact-root=" + temporary.resolve("legacy"),
                        "elmos.snapshot.max-artifact-bytes=1048576")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    SnapshotPorts.ArtifactStore writer =
                            context.getBean(SnapshotPorts.ArtifactStore.class);
                    SnapshotPorts.ArtifactReader reader =
                            context.getBean(SnapshotPorts.ArtifactReader.class);
                    assertInstanceOf(LocalContentAddressedArtifactStore.class, writer);
                    assertSame(writer, reader);
                    assertTrue(context.getBeansOfType(LocalDiskCasStore.class).isEmpty());
                    assertTrue(context.getBeansOfType(JdbcCasCatalog.class).isEmpty());

                    var status = context.getBean(
                            SnapshotArtifactConfiguration.SnapshotArtifactStoreStatus.class);
                    assertEquals("LEGACY_COMPATIBILITY", status.status());
                    assertEquals("SINGLE_HOST", status.storageScope());
                    assertEquals("GLOBAL_DIGEST", status.physicalNamespace());
                    assertEquals("LEGACY_ONLY", status.readers());
                    assertEquals("NOT_CONFIGURED", status.migrationState());
                    assertEquals("NOT_CONFIGURED", status.atRestTenantEncryption());
                    assertEquals("NOT_CONFIGURED", status.snapshotReferenceRoots());
                    assertEquals("LEGACY_DIGEST_ONLY", status.readAuthorization());
                    assertFalse(status.casReaderTenantCatalogAuthorization());
                    assertFalse(status.productionCertified());
                    assertAccurateInfo(context.getBean(InfoContributor.class),
                            "LEGACY_COMPATIBILITY", "SINGLE_HOST", "LEGACY_ONLY",
                            "NOT_CONFIGURED", "GLOBAL_DIGEST", "NOT_CONFIGURED",
                            "NOT_CONFIGURED", false);
                });
    }

    @Test
    void explicitCasConfigurationWiresLocalDiskJdbcCatalogAndTenantAwareAdapter() {
        Path casRoot = temporary.resolve("cas");
        contextRunner()
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=true",
                        "elmos.snapshot.artifact-root=" + temporary.resolve("legacy"),
                        "elmos.snapshot.cas.root=" + casRoot,
                        "elmos.snapshot.cas.store-name=snapshot-test",
                        "elmos.snapshot.cas.data-residency=cn-east",
                        "elmos.snapshot.cas.security-tier=CONFIDENTIAL",
                        "elmos.snapshot.max-artifact-bytes=1048576")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    SnapshotPorts.ArtifactStore writer =
                            context.getBean(SnapshotPorts.ArtifactStore.class);
                    SnapshotPorts.ArtifactReader reader =
                            context.getBean(SnapshotPorts.ArtifactReader.class);
                    var compatible = assertInstanceOf(
                            CompatibleSnapshotArtifactStore.class, writer);
                    assertEquals(CompatibleSnapshotArtifactStore.WriterMode.CAS,
                            compatible.writerMode());
                    assertSame(writer, reader);
                    assertEquals(1, context.getBeansOfType(
                            LocalContentAddressedArtifactStore.class).size());
                    assertEquals(1, context.getBeansOfType(CasBackedArtifactStore.class).size());
                    assertEquals(casRoot, context.getBean(LocalDiskCasStore.class).root());
                    assertNotNull(context.getBean(JdbcCasCatalog.class));

                    var status = context.getBean(
                            SnapshotArtifactConfiguration.SnapshotArtifactStoreStatus.class);
                    assertEquals("CONFIGURED_LOCAL_ONLY", status.status());
                    assertEquals("CAS_WRITE_DUAL_READ", status.mode());
                    assertEquals("JDBC_POSTGRESQL", status.catalog());
                    assertEquals("SINGLE_HOST", status.storageScope());
                    assertEquals("GLOBAL_DIGEST", status.physicalNamespace());
                    assertEquals("LEGACY_AND_CAS", status.readers());
                    assertEquals("ACTIVE_DUAL_READ", status.migrationState());
                    assertEquals("NOT_CONFIGURED", status.atRestTenantEncryption());
                    assertEquals("CAPTURE_ARCHIVE_RECONCILIATION_WIRED",
                            status.snapshotReferenceRoots());
                    assertEquals("MIXED_LEGACY_UNSCOPED", status.readAuthorization());
                    assertTrue(status.casReaderTenantCatalogAuthorization());
                    assertFalse(status.productionCertified());
                    assertAccurateInfo(context.getBean(InfoContributor.class),
                            "CONFIGURED_LOCAL_ONLY", "SINGLE_HOST", "LEGACY_AND_CAS",
                            "ACTIVE_DUAL_READ", "GLOBAL_DIGEST", "NOT_CONFIGURED",
                            "CAPTURE_ARCHIVE_RECONCILIATION_WIRED", true);
                });
    }

    @Test
    void explicitTenantEncryptionUsesCiphertextNamespacesAndReportsTheExactMode() throws Exception {
        Path casRoot = temporary.resolve("encrypted-cas");
        Path keyRoot = temporary.resolve("tenant-keys");
        java.nio.file.Files.createDirectory(keyRoot);
        contextRunner()
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=true",
                        "elmos.snapshot.artifact-root=" + temporary.resolve("encrypted-legacy"),
                        "elmos.snapshot.cas.root=" + casRoot,
                        "elmos.snapshot.cas.store-name=snapshot-encrypted-test",
                        "elmos.snapshot.cas.data-residency=cn-east",
                        "elmos.snapshot.cas.security-tier=CONFIDENTIAL",
                        "elmos.snapshot.cas.encryption.enabled=true",
                        "elmos.snapshot.cas.encryption.key-directory=" + keyRoot,
                        "elmos.snapshot.max-artifact-bytes=1048576")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertTrue(context.getBeansOfType(LocalDiskCasStore.class).isEmpty());
                    TenantCasStore tenantStore = context.getBean(TenantCasStore.class);
                    assertInstanceOf(TenantEncryptedLocalCasStore.class, tenantStore);
                    assertEquals("TENANT_NAMESPACED_CIPHERTEXT", tenantStore.physicalNamespace());
                    assertEquals("TENANT_AES_256_GCM", tenantStore.atRestProtection());

                    var status = context.getBean(
                            SnapshotArtifactConfiguration.SnapshotArtifactStoreStatus.class);
                    assertEquals("TENANT_NAMESPACED_CIPHERTEXT", status.physicalNamespace());
                    assertEquals("TENANT_AES_256_GCM", status.atRestTenantEncryption());
                    assertFalse(status.productionCertified());
                    assertAccurateInfo(context.getBean(InfoContributor.class),
                            "CONFIGURED_LOCAL_ONLY", "SINGLE_HOST", "LEGACY_AND_CAS",
                            "ACTIVE_DUAL_READ", "TENANT_NAMESPACED_CIPHERTEXT",
                            "TENANT_AES_256_GCM",
                            "CAPTURE_ARCHIVE_RECONCILIATION_WIRED", true);
                });
    }

    @Test
    void kmsEnvelopeModeRequiresAnExplicitProviderAndReportsItsExactBoundary() {
        Path casRoot = temporary.resolve("kms-encrypted-cas");
        ApplicationContextRunner kmsRunner = contextRunner()
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=true",
                        "elmos.snapshot.artifact-root=" + temporary.resolve("kms-legacy"),
                        "elmos.snapshot.cas.root=" + casRoot,
                        "elmos.snapshot.cas.store-name=snapshot-kms-test",
                        "elmos.snapshot.cas.data-residency=cn-east",
                        "elmos.snapshot.cas.security-tier=CONFIDENTIAL",
                        "elmos.snapshot.cas.encryption.enabled=true",
                        "elmos.snapshot.cas.encryption.provider=KMS",
                        "elmos.snapshot.max-artifact-bytes=1048576");

        kmsRunner.run(context -> assertNotNull(context.getStartupFailure(),
                "KMS mode must fail closed without an operator-supplied provider bean"));

        kmsRunner
                .withBean(KmsTenantEncryption.KeyManagementProvider.class,
                        () -> mock(KmsTenantEncryption.KeyManagementProvider.class))
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertNotNull(context.getBean(KmsTenantEncryption.class));
                    TenantCasStore tenantStore = context.getBean(TenantCasStore.class);
                    assertEquals("TENANT_KMS_ENVELOPE_AES_256_GCM",
                            tenantStore.atRestProtection());
                    var status = context.getBean(
                            SnapshotArtifactConfiguration.SnapshotArtifactStoreStatus.class);
                    assertEquals("SINGLE_HOST", status.storageScope());
                    assertEquals("TENANT_KMS_ENVELOPE_AES_256_GCM",
                            status.atRestTenantEncryption());
                    assertFalse(status.productionCertified());
                });
    }

    @Test
    void explicitRollbackModeWritesLegacyButKeepsVerifiedCasReadsAndRoots() {
        Path casRoot = temporary.resolve("rollback-cas");
        contextRunner()
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=false",
                        "elmos.snapshot.cas.compatibility-read-enabled=true",
                        "elmos.snapshot.artifact-root=" + temporary.resolve("rollback-legacy"),
                        "elmos.snapshot.cas.root=" + casRoot,
                        "elmos.snapshot.cas.store-name=snapshot-rollback-test",
                        "elmos.snapshot.cas.data-residency=cn-east",
                        "elmos.snapshot.cas.security-tier=CONFIDENTIAL",
                        "elmos.snapshot.max-artifact-bytes=1048576")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    SnapshotPorts.ArtifactStore writer =
                            context.getBean(SnapshotPorts.ArtifactStore.class);
                    SnapshotPorts.ArtifactReader reader =
                            context.getBean(SnapshotPorts.ArtifactReader.class);
                    var compatible = assertInstanceOf(
                            CompatibleSnapshotArtifactStore.class, writer);
                    assertEquals(CompatibleSnapshotArtifactStore.WriterMode.LEGACY,
                            compatible.writerMode());
                    assertSame(writer, reader);
                    assertEquals(casRoot, context.getBean(LocalDiskCasStore.class).root());
                    assertNotNull(context.getBean(JdbcCasCatalog.class));

                    var status = context.getBean(
                            SnapshotArtifactConfiguration.SnapshotArtifactStoreStatus.class);
                    assertEquals("ROLLBACK_COMPATIBILITY", status.status());
                    assertEquals("LEGACY_WRITE_DUAL_READ", status.mode());
                    assertEquals("LEGACY_AND_CAS", status.readers());
                    assertEquals("CAS_ROLLBACK_DUAL_READ", status.migrationState());
                    assertEquals("CAPTURE_ARCHIVE_RECONCILIATION_WIRED",
                            status.snapshotReferenceRoots());
                    assertEquals("MIXED_LEGACY_UNSCOPED", status.readAuthorization());
                    assertTrue(status.casReaderTenantCatalogAuthorization());
                    assertFalse(status.productionCertified());
                    assertAccurateInfo(context.getBean(InfoContributor.class),
                            "ROLLBACK_COMPATIBILITY", "SINGLE_HOST", "LEGACY_AND_CAS",
                            "CAS_ROLLBACK_DUAL_READ", "GLOBAL_DIGEST", "NOT_CONFIGURED",
                            "CAPTURE_ARCHIVE_RECONCILIATION_WIRED", true);
                });
    }

    private static void assertAccurateInfo(
            InfoContributor contributor,
            String expectedStatus,
            String expectedScope,
            String expectedReaders,
            String expectedMigration,
            String expectedPhysicalNamespace,
            String expectedEncryption,
            String expectedRoots,
            boolean tenantAuthorization
    ) {
        Info.Builder builder = new Info.Builder();
        contributor.contribute(builder);
        Object detail = builder.build().getDetails().get("snapshotArtifactStore");
        assertInstanceOf(Map.class, detail);
        Map<?, ?> values = (Map<?, ?>) detail;
        assertEquals(expectedStatus, values.get("status"));
        assertEquals(expectedScope, values.get("storageScope"));
        assertEquals(expectedPhysicalNamespace, values.get("physicalNamespace"));
        assertEquals(expectedReaders, values.get("readers"));
        assertEquals(expectedMigration, values.get("migrationState"));
        assertEquals(expectedEncryption, values.get("atRestTenantEncryption"));
        assertEquals(expectedRoots, values.get("snapshotReferenceRoots"));
        assertEquals(tenantAuthorization, values.get("casReaderTenantCatalogAuthorization"));
        assertEquals("LEGACY_ONLY".equals(expectedReaders)
                        ? "LEGACY_DIGEST_ONLY" : "MIXED_LEGACY_UNSCOPED",
                values.get("readAuthorization"));
        assertEquals("NOT_CERTIFIED", values.get("productionCertification"));
    }
}
