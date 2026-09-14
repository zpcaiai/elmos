package io.elmos.controlplane;

import io.elmos.secret.DeploymentSecretSession;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import static org.assertj.core.api.Assertions.assertThat;

class DeploymentSecretConfigurationTest {
    private final ApplicationContextRunner context = new ApplicationContextRunner()
            .withUserConfiguration(DeploymentSecretConfiguration.class);

    @Test void disabledInstallationDoesNotCreateSecretAuthority() {
        context.run(application -> assertThat(application).doesNotHaveBean(DeploymentSecretSession.class));
    }

    @Test void enabledInstallationRequiresCanonicalProvider() {
        context.withPropertyValues("component=billing", "elmos.release-deployment.runtime-enabled=true",
                "elmos.release-deployment.secret-enabled=true").run(application -> {
            assertThat(application).hasFailed();
            assertThat(application.getStartupFailure()).hasStackTraceContaining("SecretProviderPort");
        });
    }
}
