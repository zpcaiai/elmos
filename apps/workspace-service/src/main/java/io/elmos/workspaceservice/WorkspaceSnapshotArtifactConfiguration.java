package io.elmos.workspaceservice;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.DirectoryTenantEncryption;
import io.elmos.cas.JdbcCasCatalog;
import io.elmos.cas.KmsTenantEncryption;
import io.elmos.cas.LocalDiskCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.cas.TenantEncryptedLocalCasStore;
import io.elmos.cas.TenantEncryption;
import io.elmos.integrations.CasBackedArtifactStore;
import io.elmos.integrations.LocalContentAddressedArtifactStore;
import io.elmos.integrations.WorkspaceSnapshotArtifactReader;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Locale;
import java.util.Map;

/**
 * Read-only CAS wiring for workspace snapshot materialization.
 *
 * <p>This configuration intentionally remains {@code SINGLE_HOST / NOT_CERTIFIED}. Enabling it
 * does not provide a multi-host shared tier, production KMS evidence, or independent operational
 * qualification. Legacy reads are absent unless the explicit compatibility property is true.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
class WorkspaceSnapshotArtifactConfiguration {

    record WorkspaceSnapshotReaderStatus(
            String mode,
            String storageScope,
            String catalog,
            String legacyCompatibility,
            String atRestProtection,
            boolean productionCertified
    ) {
    }

    @Bean
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-cas.encryption.enabled",
            havingValue = "false",
            matchIfMissing = true)
    LocalDiskCasStore workspaceSnapshotLocalDiskCasStore(
            @Value("${elmos.workspace.snapshot-cas.root:}") String casRoot,
            @Value("${elmos.workspace.snapshot-cas.store-name:snapshot-local}") String storeName,
            @Value("${elmos.workspace.snapshot-cas.allow-unencrypted-single-host:false}")
            boolean allowUnencryptedSingleHost
    ) {
        if (casRoot.isBlank()) {
            throw new IllegalStateException(
                    "workspace snapshot CAS root is required when Docker workspaces are enabled");
        }
        if (!allowUnencryptedSingleHost) {
            throw new IllegalStateException(
                    "unencrypted single-host workspace snapshot CAS requires an explicit opt-in");
        }
        return new LocalDiskCasStore(
                storeName,
                createAndResolveRealDirectory(
                        Path.of(casRoot), "workspace snapshot CAS root"));
    }

    @Bean
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-cas.encryption.enabled",
            havingValue = "false",
            matchIfMissing = true)
    TenantCasStore workspaceUnencryptedSnapshotTenantCasStore(LocalDiskCasStore store) {
        return TenantCasStore.global(store);
    }

    @Bean
    @ConditionalOnExpression(
            "${elmos.workspace.snapshot-cas.encryption.enabled:false} and "
                    + "'${elmos.workspace.snapshot-cas.encryption.provider:DIRECTORY}' "
                    + "== 'DIRECTORY'")
    DirectoryTenantEncryption workspaceSnapshotTenantEncryption(
            @Value("${elmos.workspace.snapshot-cas.encryption.key-directory:}")
            String keyDirectory
    ) {
        if (keyDirectory.isBlank()) {
            throw new IllegalStateException(
                    "workspace snapshot CAS tenant key directory is required");
        }
        return new DirectoryTenantEncryption(Path.of(keyDirectory));
    }

    @Bean
    @ConditionalOnExpression(
            "${elmos.workspace.snapshot-cas.encryption.enabled:false} and "
                    + "'${elmos.workspace.snapshot-cas.encryption.provider:DIRECTORY}' == 'KMS'")
    KmsTenantEncryption workspaceSnapshotKmsTenantEncryption(
            KmsTenantEncryption.KeyManagementProvider provider
    ) {
        return new KmsTenantEncryption(provider);
    }

    @Bean
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-cas.encryption.enabled",
            havingValue = "true")
    TenantEncryptedLocalCasStore workspaceEncryptedSnapshotTenantCasStore(
            TenantEncryption encryption,
            @Value("${elmos.workspace.snapshot-cas.root:}") String casRoot,
            @Value("${elmos.workspace.snapshot-cas.store-name:snapshot-local}") String storeName,
            @Value("${elmos.workspace.snapshot-cas.encryption.key-directory:}")
            String keyDirectory,
            @Value("${elmos.workspace.snapshot-cas.encryption.provider:DIRECTORY}")
            String provider
    ) {
        if (casRoot.isBlank()) {
            throw new IllegalStateException("workspace snapshot CAS root is required");
        }
        Path storage = createAndResolveRealDirectory(
                Path.of(casRoot), "workspace snapshot ciphertext root");
        if ("DIRECTORY".equals(provider)) {
            Path keys = requireRealDirectory(
                    Path.of(keyDirectory), "workspace snapshot tenant key root");
            if (storage.startsWith(keys) || keys.startsWith(storage)) {
                throw new IllegalStateException(
                        "workspace snapshot CAS key and ciphertext roots must be disjoint");
            }
        } else if (!"KMS".equals(provider)) {
            throw new IllegalStateException(
                    "workspace snapshot CAS encryption provider is invalid");
        }
        return new TenantEncryptedLocalCasStore(storeName, storage, encryption);
    }

    @Bean
    JdbcCasCatalog workspaceSnapshotJdbcCasCatalog(DataSource dataSource) {
        return new JdbcCasCatalog(dataSource);
    }

    @Bean
    @Qualifier("workspaceCasSnapshotArtifactReader")
    CasBackedArtifactStore workspaceCasSnapshotArtifactReader(
            TenantCasStore store,
            JdbcCasCatalog catalog,
            Clock clock,
            @Value("${elmos.workspace.snapshot-cas.data-residency:}") String dataResidency,
            @Value("${elmos.workspace.snapshot-cas.security-tier:CONFIDENTIAL}")
            String securityTier,
            @Value("${elmos.workspace.snapshot-max-artifact-bytes:1073741824}")
            long maximumArtifactBytes
    ) {
        if (dataResidency.isBlank()) {
            throw new IllegalStateException(
                    "workspace snapshot CAS data residency is required");
        }
        CasAccessPolicy.SecurityTier classification;
        try {
            classification = CasAccessPolicy.SecurityTier.valueOf(
                    securityTier.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException invalid) {
            throw new IllegalStateException(
                    "workspace snapshot CAS security tier is invalid", invalid);
        }
        return new CasBackedArtifactStore(
                store, catalog, dataResidency, classification,
                maximumArtifactBytes, clock::millis);
    }

    @Bean
    @Qualifier("workspaceLegacySnapshotArtifactReader")
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-legacy-compatibility-enabled",
            havingValue = "true")
    LocalContentAddressedArtifactStore workspaceLegacySnapshotArtifactReader(
            TenantCasStore initializedCasStore,
            @Value("${elmos.workspace.snapshot-artifact-root:}") String artifactRoot,
            @Value("${elmos.workspace.snapshot-cas.root:}") String casRoot,
            @Value("${elmos.workspace.snapshot-max-artifact-bytes:1073741824}")
            long maximumArtifactBytes
    ) {
        if (artifactRoot.isBlank() || casRoot.isBlank()) {
            throw new IllegalStateException(
                    "legacy and CAS snapshot roots are required by compatibility policy");
        }
        // Constructing the verified legacy reader creates its root; the TenantCasStore parameter
        // ensures the selected CAS root is initialized first. Compare real paths so a parent
        // symlink cannot make two lexical roots alias the same storage.
        Path legacy = createAndResolveRealDirectory(
                Path.of(artifactRoot), "legacy snapshot root");
        LocalContentAddressedArtifactStore legacyStore =
                new LocalContentAddressedArtifactStore(legacy, maximumArtifactBytes);
        Path cas = requireRealDirectory(
                Path.of(casRoot), "workspace snapshot CAS root");
        if (legacy.startsWith(cas) || cas.startsWith(legacy)) {
            throw new IllegalStateException(
                    "legacy snapshot and CAS roots must be disjoint");
        }
        // The dependency is intentionally used as an initialization barrier, not as a legacy
        // backend; legacy bytes never bypass the verified compatibility reader.
        java.util.Objects.requireNonNull(initializedCasStore, "initializedCasStore");
        return legacyStore;
    }

    @Bean
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-legacy-compatibility-enabled",
            havingValue = "false",
            matchIfMissing = true)
    WorkspaceInfrastructurePorts.SnapshotArtifactReader workspaceCasOnlySnapshotArtifactReader(
            @Qualifier("workspaceCasSnapshotArtifactReader")
            CasBackedArtifactStore casReader,
            @Value("${elmos.workspace.snapshot-max-artifact-bytes:1073741824}")
            long maximumArtifactBytes
    ) {
        return new WorkspaceSnapshotArtifactReader(
                casReader,
                null,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.DENY,
                maximumArtifactBytes);
    }

    @Bean
    @ConditionalOnProperty(
            name = "elmos.workspace.snapshot-legacy-compatibility-enabled",
            havingValue = "true")
    WorkspaceInfrastructurePorts.SnapshotArtifactReader
            workspaceLegacyCompatibleSnapshotArtifactReader(
            @Qualifier("workspaceCasSnapshotArtifactReader")
            CasBackedArtifactStore casReader,
            @Qualifier("workspaceLegacySnapshotArtifactReader")
            LocalContentAddressedArtifactStore legacyReader,
            @Value("${elmos.workspace.snapshot-max-artifact-bytes:1073741824}")
            long maximumArtifactBytes
    ) {
        return new WorkspaceSnapshotArtifactReader(
                casReader,
                legacyReader,
                WorkspaceSnapshotArtifactReader.LegacyCompatibilityPolicy.ALLOW_VERIFIED,
                maximumArtifactBytes);
    }

    @Bean
    WorkspaceSnapshotReaderStatus workspaceSnapshotReaderStatus(
            TenantCasStore store,
            @Value("${elmos.workspace.snapshot-legacy-compatibility-enabled:false}")
            boolean legacyCompatibility
    ) {
        return new WorkspaceSnapshotReaderStatus(
                legacyCompatibility ? "CAS_WITH_VERIFIED_LEGACY" : "CAS_ONLY",
                "SINGLE_HOST",
                "JDBC_POSTGRESQL",
                legacyCompatibility ? "EXPLICIT_ENABLED" : "DENIED",
                store.atRestProtection(),
                false);
    }

    @Bean
    InfoContributor workspaceSnapshotReaderInfoContributor(
            WorkspaceSnapshotReaderStatus status
    ) {
        return builder -> builder.withDetail("workspaceSnapshotReader", Map.of(
                "mode", status.mode(),
                "storageScope", status.storageScope(),
                "catalog", status.catalog(),
                "legacyCompatibility", status.legacyCompatibility(),
                "atRestProtection", status.atRestProtection(),
                "productionCertification",
                status.productionCertified() ? "CERTIFIED" : "NOT_CERTIFIED"));
    }

    private static Path createAndResolveRealDirectory(Path path, String label) {
        try {
            Path normalized = path.toAbsolutePath().normalize();
            Files.createDirectories(normalized);
            return requireRealDirectory(normalized, label);
        } catch (IOException error) {
            throw new IllegalStateException(label + " is unavailable", error);
        }
    }

    private static Path requireRealDirectory(Path path, String label) {
        try {
            Path normalized = path.toAbsolutePath().normalize();
            if (Files.isSymbolicLink(normalized)
                    || !Files.isDirectory(normalized, LinkOption.NOFOLLOW_LINKS)) {
                throw new IllegalStateException(label + " must be a real directory");
            }
            return normalized.toRealPath();
        } catch (IOException error) {
            throw new IllegalStateException(label + " is unavailable", error);
        }
    }
}
