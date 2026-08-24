package io.elmos.controlplane;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.DirectoryTenantEncryption;
import io.elmos.cas.JdbcCasCatalog;
import io.elmos.cas.LocalDiskCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.cas.TenantEncryptedLocalCasStore;
import io.elmos.integrations.CasBackedArtifactStore;
import io.elmos.integrations.CompatibleSnapshotArtifactStore;
import io.elmos.integrations.LocalContentAddressedArtifactStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import javax.sql.DataSource;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Locale;
import java.util.Map;

/** Selects the snapshot artifact implementation without implying remote or certified storage. */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
class SnapshotArtifactConfiguration {

    record SnapshotArtifactStoreStatus(
            String status,
            String mode,
            String catalog,
            String storageScope,
            String physicalNamespace,
            String readers,
            String readAuthorization,
            String migrationState,
            String atRestTenantEncryption,
            String snapshotReferenceRoots,
            boolean casReaderTenantCatalogAuthorization,
            boolean productionCertified
    ) {
    }

    @Bean
    @Qualifier("legacySnapshotArtifactBackend")
    LocalContentAddressedArtifactStore legacySnapshotArtifactStore(
            @Value("${elmos.snapshot.artifact-root:}") String artifactRoot,
            @Value("${elmos.snapshot.max-artifact-bytes:1073741824}") long maxArtifactBytes
    ) {
        if (artifactRoot.isBlank()) {
            throw new IllegalStateException("snapshot artifact root is required");
        }
        return new LocalContentAddressedArtifactStore(Path.of(artifactRoot), maxArtifactBytes);
    }

    @Bean
    @ConditionalOnExpression(
            "(${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}) and not "
                    + "${elmos.snapshot.cas.encryption.enabled:false}")
    LocalDiskCasStore snapshotLocalDiskCasStore(
            @Value("${elmos.snapshot.cas.root:}") String casRoot,
            @Value("${elmos.snapshot.cas.store-name:snapshot-local}") String storeName
    ) {
        if (casRoot.isBlank()) {
            throw new IllegalStateException(
                    "snapshot CAS root is required when snapshot CAS is enabled");
        }
        return new LocalDiskCasStore(storeName, Path.of(casRoot));
    }

    @Bean
    @ConditionalOnExpression(
            "(${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}) and not "
                    + "${elmos.snapshot.cas.encryption.enabled:false}")
    TenantCasStore unencryptedSnapshotTenantCasStore(LocalDiskCasStore store) {
        return TenantCasStore.global(store);
    }

    @Bean
    @ConditionalOnExpression(
            "(${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}) and "
                    + "${elmos.snapshot.cas.encryption.enabled:false}")
    DirectoryTenantEncryption snapshotTenantEncryption(
            @Value("${elmos.snapshot.cas.encryption.key-directory:}") String keyDirectory
    ) {
        if (keyDirectory.isBlank()) {
            throw new IllegalStateException(
                    "snapshot CAS tenant key directory is required when encryption is enabled");
        }
        return new DirectoryTenantEncryption(Path.of(keyDirectory));
    }

    @Bean
    @ConditionalOnExpression(
            "(${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}) and "
                    + "${elmos.snapshot.cas.encryption.enabled:false}")
    TenantEncryptedLocalCasStore encryptedSnapshotTenantCasStore(
            DirectoryTenantEncryption encryption,
            @Value("${elmos.snapshot.cas.root:}") String casRoot,
            @Value("${elmos.snapshot.cas.store-name:snapshot-local}") String storeName,
            @Value("${elmos.snapshot.cas.encryption.key-directory:}") String keyDirectory
    ) {
        if (casRoot.isBlank()) {
            throw new IllegalStateException(
                    "snapshot CAS root is required when snapshot CAS encryption is enabled");
        }
        Path storage = Path.of(casRoot).toAbsolutePath().normalize();
        Path keys = Path.of(keyDirectory).toAbsolutePath().normalize();
        if (storage.startsWith(keys) || keys.startsWith(storage)) {
            throw new IllegalStateException(
                    "snapshot CAS key directory and ciphertext root must be disjoint");
        }
        return new TenantEncryptedLocalCasStore(storeName, storage, encryption);
    }

    @Bean
    @ConditionalOnExpression(
            "${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}")
    JdbcCasCatalog snapshotJdbcCasCatalog(DataSource dataSource) {
        return new JdbcCasCatalog(dataSource);
    }

    @Bean
    @Qualifier("casSnapshotArtifactBackend")
    @ConditionalOnExpression(
            "${elmos.snapshot.cas.enabled:false} or "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}")
    CasBackedArtifactStore casSnapshotArtifactStore(
            TenantCasStore store,
            JdbcCasCatalog catalog,
            Clock clock,
            @Value("${elmos.snapshot.cas.data-residency:}") String dataResidency,
            @Value("${elmos.snapshot.cas.security-tier:CONFIDENTIAL}") String securityTier,
            @Value("${elmos.snapshot.max-artifact-bytes:1073741824}") long maxArtifactBytes
    ) {
        if (dataResidency.isBlank()) {
            throw new IllegalStateException(
                    "snapshot CAS data residency is required when snapshot CAS is enabled");
        }
        CasAccessPolicy.SecurityTier classification;
        try {
            classification = CasAccessPolicy.SecurityTier.valueOf(
                    securityTier.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException("snapshot CAS security tier is invalid", error);
        }
        return new CasBackedArtifactStore(store, catalog, dataResidency,
                classification, maxArtifactBytes, clock::millis);
    }

    @Bean
    @Primary
    @ConditionalOnProperty(name = "elmos.snapshot.cas.enabled", havingValue = "true")
    CompatibleSnapshotArtifactStore casWriteCompatibleSnapshotArtifactStore(
            @Qualifier("legacySnapshotArtifactBackend")
            LocalContentAddressedArtifactStore legacy,
            @Qualifier("casSnapshotArtifactBackend") CasBackedArtifactStore cas
    ) {
        return new CompatibleSnapshotArtifactStore(
                CompatibleSnapshotArtifactStore.WriterMode.CAS,
                legacy, legacy, cas, cas);
    }

    @Bean
    @Primary
    @ConditionalOnExpression(
            "not ${elmos.snapshot.cas.enabled:false} and "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}")
    CompatibleSnapshotArtifactStore legacyWriteCompatibleSnapshotArtifactStore(
            @Qualifier("legacySnapshotArtifactBackend")
            LocalContentAddressedArtifactStore legacy,
            @Qualifier("casSnapshotArtifactBackend") CasBackedArtifactStore cas
    ) {
        return new CompatibleSnapshotArtifactStore(
                CompatibleSnapshotArtifactStore.WriterMode.LEGACY,
                legacy, legacy, cas, cas);
    }

    @Bean
    @ConditionalOnExpression(
            "not ${elmos.snapshot.cas.enabled:false} and not "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}")
    SnapshotArtifactStoreStatus legacySnapshotArtifactStoreStatus() {
        return new SnapshotArtifactStoreStatus(
                "LEGACY_COMPATIBILITY", "LEGACY_WRITE", "NONE",
                "SINGLE_HOST", "GLOBAL_DIGEST", "LEGACY_ONLY", "LEGACY_DIGEST_ONLY",
                "NOT_CONFIGURED",
                "NOT_CONFIGURED", "NOT_CONFIGURED",
                false, false);
    }

    @Bean
    @ConditionalOnProperty(name = "elmos.snapshot.cas.enabled", havingValue = "true")
    SnapshotArtifactStoreStatus casSnapshotArtifactStoreStatus(TenantCasStore store) {
        return new SnapshotArtifactStoreStatus(
                "CONFIGURED_LOCAL_ONLY", "CAS_WRITE_DUAL_READ", "JDBC_POSTGRESQL",
                "SINGLE_HOST", store.physicalNamespace(), "LEGACY_AND_CAS",
                "MIXED_LEGACY_UNSCOPED", "ACTIVE_DUAL_READ",
                store.atRestProtection(), "CAPTURE_REGISTERED_DELETE_RELEASE_NOT_WIRED",
                true, false);
    }

    @Bean
    @ConditionalOnExpression(
            "not ${elmos.snapshot.cas.enabled:false} and "
                    + "${elmos.snapshot.cas.compatibility-read-enabled:false}")
    SnapshotArtifactStoreStatus rollbackCompatibleSnapshotArtifactStoreStatus(TenantCasStore store) {
        return new SnapshotArtifactStoreStatus(
                "ROLLBACK_COMPATIBILITY", "LEGACY_WRITE_DUAL_READ", "JDBC_POSTGRESQL",
                "SINGLE_HOST", store.physicalNamespace(), "LEGACY_AND_CAS",
                "MIXED_LEGACY_UNSCOPED", "CAS_ROLLBACK_DUAL_READ",
                store.atRestProtection(), "CAPTURE_REGISTERED_DELETE_RELEASE_NOT_WIRED",
                true, false);
    }

    @Bean
    InfoContributor snapshotArtifactStoreInfoContributor(
            SnapshotArtifactStoreStatus artifactStatus
    ) {
        return builder -> builder.withDetail("snapshotArtifactStore", Map.ofEntries(
                Map.entry("status", artifactStatus.status()),
                Map.entry("mode", artifactStatus.mode()),
                Map.entry("catalog", artifactStatus.catalog()),
                Map.entry("storageScope", artifactStatus.storageScope()),
                Map.entry("physicalNamespace", artifactStatus.physicalNamespace()),
                Map.entry("readers", artifactStatus.readers()),
                Map.entry("readAuthorization", artifactStatus.readAuthorization()),
                Map.entry("migrationState", artifactStatus.migrationState()),
                Map.entry("atRestTenantEncryption", artifactStatus.atRestTenantEncryption()),
                Map.entry("snapshotReferenceRoots", artifactStatus.snapshotReferenceRoots()),
                Map.entry("casReaderTenantCatalogAuthorization",
                        artifactStatus.casReaderTenantCatalogAuthorization()),
                Map.entry("productionCertification",
                        artifactStatus.productionCertified() ? "CERTIFIED" : "NOT_CERTIFIED")));
    }
}
