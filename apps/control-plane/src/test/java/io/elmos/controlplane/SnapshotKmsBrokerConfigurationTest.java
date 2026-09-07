package io.elmos.controlplane;

import io.elmos.cas.HttpKmsBrokerProvider;
import io.elmos.cas.KmsTenantEncryption;
import org.junit.jupiter.api.Test;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import javax.net.ssl.SSLContext;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.mock;

class SnapshotKmsBrokerConfigurationTest {

    private ApplicationContextRunner configuredRunner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(SnapshotKmsBrokerConfiguration.class)
                .withInitializer(context -> context.getBeanFactory().setConversionService(
                        ApplicationConversionService.getSharedInstance()))
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=true",
                        "elmos.snapshot.cas.encryption.enabled=true",
                        "elmos.snapshot.cas.encryption.provider=KMS",
                        "elmos.snapshot.cas.encryption.kms-broker.endpoint=https://kms.example/v1",
                        "elmos.snapshot.cas.encryption.kms-broker.connect-timeout=2s",
                        "elmos.snapshot.cas.encryption.kms-broker.operation-timeout=4s",
                        "elmos.snapshot.cas.encryption.kms-broker.workload-spiffe-id="
                                + "spiffe://prod.elmos.example/control-plane/cas",
                        "elmos.snapshot.cas.encryption.kms-broker.mtls-secret-reference="
                                + "secret://platform/cas-kms-mtls",
                        "elmos.snapshot.cas.encryption.kms-broker.authorization-secret-reference="
                                + "secret://platform/cas-kms-policy");
    }

    @Test
    void kmsModeBuildsTheBrokerOnlyThroughTheWorkloadIdentityTlsBoundary() {
        configuredRunner()
                .withBean(HttpKmsBrokerProvider.WorkloadSslContextProvider.class,
                        () -> identity -> {
                            try {
                                return SSLContext.getDefault();
                            } catch (Exception unavailable) {
                                throw new IllegalStateException(unavailable);
                            }
                        })
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertInstanceOf(HttpKmsBrokerProvider.class,
                            context.getBean(KmsTenantEncryption.KeyManagementProvider.class));
                });
    }

    @Test
    void kmsModeFailsClosedWithoutAWorkloadIdentityTlsProvider() {
        configuredRunner().run(context -> assertNotNull(context.getStartupFailure()));
    }

    @Test
    void anExplicitExternalProviderOverridesTheBundledBrokerWiring() {
        KmsTenantEncryption.KeyManagementProvider external =
                mock(KmsTenantEncryption.KeyManagementProvider.class);
        new ApplicationContextRunner()
                .withUserConfiguration(SnapshotKmsBrokerConfiguration.class)
                .withPropertyValues(
                        "elmos.snapshot.cas.enabled=true",
                        "elmos.snapshot.cas.encryption.enabled=true",
                        "elmos.snapshot.cas.encryption.provider=KMS")
                .withBean(KmsTenantEncryption.KeyManagementProvider.class, () -> external)
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    org.junit.jupiter.api.Assertions.assertSame(external,
                            context.getBean(KmsTenantEncryption.KeyManagementProvider.class));
                });
    }
}
