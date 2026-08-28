package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Clock;
import java.time.Duration;

/** Spring wiring shared by the control plane and worker-side adapters. */
@Configuration
public class ProductionRuntimeConfiguration {
    @Bean
    public JdbcProductionRuntimeStore productionRuntimeStore(
            JdbcClient jdbc,
            TransactionTemplate transactionTemplate,
            ObjectMapper objectMapper
    ) {
        return new JdbcProductionRuntimeStore(jdbc, transactionTemplate, objectMapper);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.billing",
            name = "adapter",
            havingValue = "jdbc",
            matchIfMissing = true)
    public JdbcProductionBillingService productionBillingService(
            JdbcClient jdbc,
            TransactionTemplate transactionTemplate,
            ObjectMapper objectMapper
    ) {
        return new JdbcProductionBillingService(jdbc, transactionTemplate, objectMapper);
    }

    @Bean
    public JdbcProductionToolCallService productionToolCallService(
            JdbcClient jdbc,
            TransactionTemplate transactionTemplate,
            ObjectMapper objectMapper
    ) {
        return new JdbcProductionToolCallService(jdbc, transactionTemplate, objectMapper);
    }

    @Bean
    public JdbcProductionRepositoryArtifactService productionRepositoryArtifactService(
            JdbcClient jdbc,
            TransactionTemplate transactionTemplate
    ) {
        return new JdbcProductionRepositoryArtifactService(jdbc, transactionTemplate);
    }

    @Bean
    public JdbcProductionProviderPayloadStore productionProviderPayloadStore(
            JdbcClient jdbc,
            TransactionTemplate transactionTemplate
    ) {
        return new JdbcProductionProviderPayloadStore(jdbc, transactionTemplate);
    }

    @Bean
    public ProductionRuntimeCoordinator productionRuntimeCoordinator(
            ProductionRuntimeStore store,
            ProductionBillingPort billing
    ) {
        return new ProductionRuntimeCoordinator(store, billing);
    }

    @Bean
    public ProductionRuntimeScheduler productionRuntimeScheduler(ProductionRuntimeStore store) {
        return new ProductionRuntimeScheduler(store);
    }

    @Bean
    public ProductionRuntimeRecoveryService productionRuntimeRecoveryService(
            ProductionRuntimeStore store,
            ProductionBillingPort billing,
            ObjectMapper objectMapper
    ) {
        return new ProductionRuntimeRecoveryService(store, billing, objectMapper);
    }

    @Bean
    public ProductionRuntimeSettlementReconciler productionRuntimeSettlementReconciler(
            ProductionRuntimeStore store,
            ProductionBillingPort billing
    ) {
        return new ProductionRuntimeSettlementReconciler(store, billing);
    }

    @Bean
    public ProductionModelCallExecutor productionModelCallExecutor(
            ProductionBillingPort billing
    ) {
        return new ProductionModelCallExecutor(billing);
    }

    @Bean
    public ProductionRuntimeSchedulingService productionRuntimeSchedulingService(
            ProductionRuntimeScheduler scheduler,
            ProductionRuntimeCoordinator coordinator,
            Clock clock
    ) {
        return new ProductionRuntimeSchedulingService(
                scheduler, coordinator, clock, Duration.ofMinutes(15), Duration.ofSeconds(30));
    }
}
