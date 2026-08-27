package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

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
}
