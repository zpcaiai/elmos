package io.elmos.controlplane;

import org.flywaydb.core.Flyway;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.ConfigurableApplicationContext;

import javax.sql.DataSource;

/** Runs the dedicated runtime schema in its own immutable Flyway history namespace. */
@Configuration
@ConditionalOnProperty(
        prefix = "elmos.production-runtime.migration",
        name = "enabled",
        havingValue = "true")
class ProductionRuntimeMigrationConfiguration {
    @Bean
    InitializingBean productionRuntimeSchemaMigrator(DataSource dataSource) {
        return () -> Flyway.configure()
                .dataSource(dataSource)
                .locations("classpath:db/production-runtime")
                .table("flyway_production_runtime_history")
                .validateMigrationNaming(true)
                .failOnMissingLocations(true)
                .cleanDisabled(true)
                .load()
                .migrate();
    }

    /** Makes the same immutable image usable as a bounded Helm migration Job. */
    @Bean
    @DependsOn("productionRuntimeSchemaMigrator")
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.migration",
            name = "exit-after-run",
            havingValue = "true")
    ApplicationRunner productionRuntimeMigrationExit(
            ConfigurableApplicationContext context
    ) {
        return ignored -> {
            int code = SpringApplication.exit(context, () -> 0);
            context.close();
            if (code != 0) {
                throw new IllegalStateException("production runtime migration exit failed");
            }
        };
    }
}
