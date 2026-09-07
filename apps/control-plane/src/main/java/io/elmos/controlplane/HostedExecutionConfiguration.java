package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.identity.AuthenticationService;
import io.elmos.identity.JdbcIdentityStore;
import io.elmos.integrations.TrustedTranslationAdmissionRunner;
import io.elmos.persistence.JdbcExecutionJobStore;
import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.persistence.JdbcTenantObjectRetentionStore;
import io.elmos.persistence.JdbcOrganizationSelfServiceStore;
import io.elmos.persistence.JdbcRunnerRegistrationStore;
import io.elmos.storage.S3ObjectStore;
import io.elmos.storage.SigV4Presigner;
import io.elmos.workflow.ExecutionJobPort;
import io.elmos.workflow.RunnerRegistrationPort;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.scheduling.annotation.Scheduled;

import javax.sql.DataSource;
import java.time.Clock;

/** Wires the durable hosted-execution and optional local-identity adapters. */
@Configuration
class HostedExecutionConfiguration {
    @Bean
    TrustedTranslationAdmissionRunner trustedTranslationAdmissionRunner() {
        return new TrustedTranslationAdmissionRunner();
    }

    @Bean
    ExecutionJobPort executionJobPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate,
            ObjectMapper json
    ) {
        return new JdbcExecutionJobStore(jdbc, billingTransactionTemplate, json);
    }

    @Bean
    RunnerRegistrationPort runnerRegistrationPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate
    ) {
        return new JdbcRunnerRegistrationStore(jdbc, billingTransactionTemplate);
    }

    @Bean
    JdbcOrganizationSelfServiceStore organizationSelfServiceStore(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate
    ) {
        return new JdbcOrganizationSelfServiceStore(jdbc, billingTransactionTemplate);
    }

    @Bean
    JdbcObjectStorageStore objectStorageStore(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate,
            @Value("${elmos.object-storage.credential-reference:}") String configuredReference,
            @Value("${elmos.object-storage.access-key-id-file:}") String accessKeyFile,
            @Value("${elmos.object-storage.secret-access-key-file:}") String secretKeyFile,
            @Value("${elmos.object-storage.session-token-file:}") String sessionTokenFile
    ) {
        JdbcObjectStorageStore.SecretResolver resolver = reference -> {
            if (reference == null || reference.isBlank()
                    || configuredReference.isBlank()
                    || !configuredReference.equals(reference)) {
                throw new S3ObjectStore.ObjectStorageException(
                        "OBJECT_STORAGE_SECRET_REFERENCE_NOT_AUTHORIZED");
            }
            String accessKey = OwnerOnlySecretFile.readRequired(
                    accessKeyFile, 16, 256, "OBJECT_STORAGE_ACCESS_KEY_FILE_INVALID");
            String secretKey = OwnerOnlySecretFile.readRequired(
                    secretKeyFile, 32, 4096, "OBJECT_STORAGE_SECRET_KEY_FILE_INVALID");
            String sessionToken = OwnerOnlySecretFile.readOptional(
                    sessionTokenFile, 16, 4096, "OBJECT_STORAGE_SESSION_TOKEN_FILE_INVALID");
            return new SigV4Presigner.Credentials(accessKey, secretKey, sessionToken);
        };
        return new JdbcObjectStorageStore(
                jdbc, billingTransactionTemplate, resolver);
    }

    @Bean
    ArtifactController.ObjectStoreFactory objectStoreFactory(
            JdbcObjectStorageStore metadata,
            Clock clock
    ) {
        return () -> new S3ObjectStore(metadata.activeBackend(), metadata, clock);
    }

    @Bean
    JdbcTenantObjectRetentionStore tenantObjectRetentionStore(
            JdbcClient jdbc, TransactionTemplate billingTransactionTemplate) {
        return new JdbcTenantObjectRetentionStore(jdbc, billingTransactionTemplate);
    }

    @Bean
    ArtifactController.TenantContext artifactTenantContext() {
        return new ArtifactController.TenantContext() {
            @Override
            public String organizationId() {
                return ControlPlanePrincipal.current()
                        .orElseThrow(() -> new org.springframework.security.access.AccessDeniedException(
                                "CONTROL_PLANE_AUTH_REQUIRED"))
                        .organizationId();
            }

            @Override
            public String actorId() {
                return ControlPlanePrincipal.current()
                        .orElseThrow(() -> new org.springframework.security.access.AccessDeniedException(
                                "CONTROL_PLANE_AUTH_REQUIRED"))
                        .actorId();
            }
        };
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.identity.local",
            name = "enabled",
            havingValue = "true")
    AuthenticationService localAuthenticationService(
            DataSource dataSource,
            @Value("${elmos.identity.local.pepper-file:}") String pepperFile
    ) {
        String pepper = OwnerOnlySecretFile.readRequired(
                pepperFile, 32, 4096, "ELMOS_IDENTITY_PEPPER_FILE_INVALID");
        return new AuthenticationService(
                new JdbcIdentityStore(dataSource::getConnection),
                AuthenticationService.UNCONFIGURED_SENDER,
                pepper);
    }
}

/**
 * Retention worker. Metadata first becomes non-downloadable, then each object is
 * physically deleted, and only a confirmed 2xx/404 advances it to PURGED.
 */
@org.springframework.stereotype.Component
@ConditionalOnProperty(prefix = "elmos.object-storage", name = "host-gc-enabled", havingValue = "true")
class ObjectRetentionScheduler {
    private final JdbcObjectStorageStore metadata;
    private final JdbcTenantObjectRetentionStore retention;
    private final Clock clock;

    ObjectRetentionScheduler(
            JdbcObjectStorageStore metadata,
            JdbcTenantObjectRetentionStore retention,
            Clock clock
    ) {
        // Fail during enabled-bean construction, BEFORE reading metadata,
        // changing retention state, or invoking a provider. A caller flag,
        // tenant role, backend row or URL timeout cannot supply this proof.
        S3ObjectStore.hostedPhysicalGcCapability().requireWriterQuiescence();
        this.metadata = metadata;
        this.retention = retention;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${elmos.object-storage.gc-interval-ms:3600000}")
    void collect() {
        retention.collect(new JdbcTenantObjectRetentionStore.ConfirmedDeleter() {
            private S3ObjectStore.Backend backend;
            private S3ObjectStore provider;

            @Override public void delete(JdbcTenantObjectRetentionStore.Purge purge) {
                // Capture once per round, after the metadata connection has
                // been returned. Reuse one bounded HTTP client for the round.
                if (backend == null) {
                    backend = metadata.activeBackend();
                    provider = new S3ObjectStore(backend, metadata, clock);
                }
                validateBinding(backend, purge);
                provider.deleteObject(purge.organizationId(), purge.contentSha256());
            }
        });
    }

    /** Pure tuple validation only; this helper cannot authorize or perform deletion. */
    static void validateBinding(S3ObjectStore.Backend backend, JdbcTenantObjectRetentionStore.Purge purge) {
        if (!purge.backendId().equals(backend.backendId())
                || !purge.storageKey().equals(S3ObjectStore.storageKey(
                        purge.organizationId(), purge.contentSha256()))) {
            throw new S3ObjectStore.ObjectStorageException("OBJECT_GC_PROVIDER_BINDING_MISMATCH");
        }
    }
}
