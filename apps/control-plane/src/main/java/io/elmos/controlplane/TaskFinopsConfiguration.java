package io.elmos.controlplane;

import io.elmos.persistence.JdbcTaskFinopsStore;
import io.elmos.workflow.TaskFinopsPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/** Wires the repository-owned V73 task economics adapter into the control plane. */
@Configuration(proxyBeanMethods = false)
class TaskFinopsConfiguration {

    @Bean
    TaskFinopsPort taskFinopsPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate
    ) {
        return new JdbcTaskFinopsStore(jdbc, billingTransactionTemplate);
    }
}
