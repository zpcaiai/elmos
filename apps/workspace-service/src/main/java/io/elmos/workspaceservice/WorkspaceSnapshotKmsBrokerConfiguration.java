package io.elmos.workspaceservice;

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
 * KMS broker reader wiring. An external workload-identity provider is mandatory; repository
 * configuration never receives a private key, token, PIN or raw broker authorization secret.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnExpression(
        "${elmos.workspace.docker.enabled:false} and "
                + "${elmos.workspace.snapshot-cas.encryption.enabled:false} and "
                + "'${elmos.workspace.snapshot-cas.encryption.provider:DIRECTORY}' == 'KMS'")
class WorkspaceSnapshotKmsBrokerConfiguration {

    @Bean
    @ConditionalOnMissingBean(KmsTenantEncryption.KeyManagementProvider.class)
    KmsTenantEncryption.KeyManagementProvider workspaceSnapshotHttpKmsBrokerProvider(
            HttpKmsBrokerProvider.WorkloadSslContextProvider workloadSslContexts,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.endpoint}")
            URI endpoint,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.connect-timeout:5s}")
            Duration connectTimeout,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.operation-timeout:15s}")
            Duration operationTimeout,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.workload-spiffe-id}")
            String workloadSpiffeId,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.mtls-secret-reference}")
            String mtlsSecretReference,
            @Value("${elmos.workspace.snapshot-cas.encryption.kms-broker.authorization-secret-reference}")
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
