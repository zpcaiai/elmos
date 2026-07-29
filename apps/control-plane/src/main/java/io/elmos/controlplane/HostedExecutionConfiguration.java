package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.identity.AuthenticationService;
import io.elmos.identity.JdbcIdentityStore;
import io.elmos.persistence.JdbcExecutionJobStore;
import io.elmos.persistence.JdbcObjectStorageStore;
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
class ObjectRetentionScheduler {
    private final JdbcObjectStorageStore metadata;
    private final ArtifactController.ObjectStoreFactory stores;

    ObjectRetentionScheduler(
            JdbcObjectStorageStore metadata,
            ArtifactController.ObjectStoreFactory stores
    ) {
        this.metadata = metadata;
        this.stores = stores;
    }

    @Scheduled(fixedDelayString = "${elmos.object-storage.gc-interval-ms:3600000}")
    void collect() {
        metadata.expireArtifacts(
                "gc-" + java.util.UUID.randomUUID(), 500);
        S3ObjectStore store = stores.current();
        for (JdbcObjectStorageStore.PendingPurge purge : metadata.pendingPurges(250)) {
            try {
                store.deleteObject(
                        purge.organizationId(), purge.contentSha256());
                metadata.confirmPurged(
                        purge.organizationId(), purge.contentObjectId());
            } catch (S3ObjectStore.ObjectStorageException ignored) {
                // Unknown provider state remains PURGE_PENDING. The next run
                // retries DELETE idempotently; it never publishes a false purge.
            }
        }
    }
}
