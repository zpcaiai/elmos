package io.elmos.controlplane;

import io.elmos.productionruntime.DeploymentProviderRegistry;
import io.elmos.productionruntime.DeploymentToolExecutor;
import io.elmos.productionruntime.JdbcDeploymentToolReceiptLookup;
import io.elmos.productionruntime.ProductionToolCallPort;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/** Composition within the existing billing/tool-call service, with mandatory host policy and evidence ports. */
@Configuration
@ConditionalOnProperty(name = "elmos.release-deployment.runtime-enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing'")
class DeploymentRuntimeConfiguration {
    @Bean
    JdbcDeploymentToolReceiptLookup deploymentReceiptLookup(JdbcClient jdbc, TransactionTemplate transactions) {
        return new JdbcDeploymentToolReceiptLookup(jdbc, transactions);
    }

    @Bean
    DeploymentToolExecutor deploymentExecutor(ProductionToolCallPort calls,
            DeploymentToolExecutor.Authorization authorization, DeploymentToolExecutor.EvidenceVerifier evidence,
            DeploymentProviderRegistry providers, JdbcDeploymentToolReceiptLookup lookup) {
        return new DeploymentToolExecutor(calls, authorization, evidence, providers.providers(), lookup);
    }
}
