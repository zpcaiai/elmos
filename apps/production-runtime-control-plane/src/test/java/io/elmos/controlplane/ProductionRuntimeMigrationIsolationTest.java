package io.elmos.controlplane;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionRuntimeMigrationIsolationTest {
    private final ApplicationContextRunner context = new ApplicationContextRunner()
            .withUserConfiguration(ProductionRuntimeControlPlaneConfiguration.class)
            .withPropertyValues(
                    "elmos.production-runtime.enabled=true",
                    "component=migration");

    @Test
    void migrationComponentDoesNotStartRuntimeLoopsOrAuthenticators() {
        context.run(application -> {
            assertThat(application).hasNotFailed();
            assertThat(application).doesNotHaveBean(
                    ProductionRuntimeControlPlaneConfiguration.ProductionRuntimeLoop.class);
            assertThat(application).doesNotHaveBean(
                    ProductionRuntimeInternalAuthenticator.class);
        });
    }
}
