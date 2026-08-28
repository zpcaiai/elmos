package io.elmos.controlplane;

import io.elmos.productionruntime.ProductionRuntimeConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.scheduling.annotation.EnableScheduling;

import java.time.Clock;

/**
 * Isolated runtime process. Component scanning is intentionally confined to
 * this package and imports only the production-runtime persistence kernel.
 */
@SpringBootApplication
@EnableScheduling
@Import(ProductionRuntimeConfiguration.class)
public class ProductionRuntimeControlPlaneApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProductionRuntimeControlPlaneApplication.class, args);
    }

    @Bean
    Clock productionRuntimeClock() {
        return Clock.systemUTC();
    }
}
