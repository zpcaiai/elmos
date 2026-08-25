package io.elmos.controlplane;

import io.elmos.cas.HttpKmsBrokerProvider;
import io.elmos.cas.KmsTenantEncryption;
import io.elmos.cas.WorkloadIdentity;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.time.Duration;

/**
 * Production-facing KMS broker wiring for snapshot CAS encryption.
 *
 * <p>The repository never reads a private key, client certificate, PIN, bearer token or broker
 * authorization secret. An external workload-identity integration must resolve the two opaque
 * {@code secret://} references into an mTLS {@link javax.net.ssl.SSLContext}. Missing identity
 * integration or incomplete broker configuration prevents startup when KMS mode is selected.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "(${elmos.snapshot.cas.enabled:false} or "
                + "${elmos.snapshot.cas.compatibility-read-enabled:false}) and "
                + "${elmos.snapshot.cas.encryption.enabled:false} and "
                + "'${elmos.snapshot.cas.encryption.provider:DIRECTORY}' == 'KMS'")
class SnapshotKmsBrokerConfiguration {

    @Bean
    @ConditionalOnMissingBean(KmsTenantEncryption.KeyManagementProvider.class)
    KmsTenantEncryption.KeyManagementProvider snapshotHttpKmsBrokerProvider(
            HttpKmsBrokerProvider.WorkloadSslContextProvider workloadSslContexts,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.endpoint}") URI endpoint,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.connect-timeout:5s}")
            Duration connectTimeout,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.operation-timeout:15s}")
            Duration operationTimeout,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.workload-spiffe-id}")
            String workloadSpiffeId,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.mtls-secret-reference}")
            String mtlsSecretReference,
            @Value("${elmos.snapshot.cas.encryption.kms-broker.authorization-secret-reference}")
            String authorizationSecretReference
    ) {
        HttpKmsBrokerProvider.IdentityBinding identity =
                new HttpKmsBrokerProvider.IdentityBinding(
                        WorkloadIdentity.SpiffeId.parse(workloadSpiffeId),
                        HttpKmsBrokerProvider.SecretReference.parse(mtlsSecretReference),
                        HttpKmsBrokerProvider.SecretReference.parse(
                                authorizationSecretReference));
        HttpKmsBrokerProvider.Config config = new HttpKmsBrokerProvider.Config(
                endpoint, connectTimeout, operationTimeout, identity);
        return HttpKmsBrokerProvider.usingMtls(config, workloadSslContexts);
    }
}
