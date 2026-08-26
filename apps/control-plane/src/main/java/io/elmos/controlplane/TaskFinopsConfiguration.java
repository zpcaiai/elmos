package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.persistence.JdbcTaskFinopsOperationsStore;
import io.elmos.persistence.JdbcTaskFinopsStore;
import io.elmos.workflow.TaskFinopsAnalyticsService;
import io.elmos.workflow.TaskFinopsOperationsPort;
import io.elmos.workflow.TaskFinopsPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/** Wires the repository-owned V77 task economics adapters into the control plane. */
@Configuration(proxyBeanMethods = false)
class TaskFinopsConfiguration {

    @Bean
    TaskFinopsPort taskFinopsPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate
    ) {
        return new JdbcTaskFinopsStore(jdbc, billingTransactionTemplate);
    }

    @Bean
    TaskFinopsOperationsPort taskFinopsOperationsPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate,
            ObjectMapper objectMapper
    ) {
        return new JdbcTaskFinopsOperationsStore(
                jdbc, billingTransactionTemplate, objectMapper);
    }

    @Bean
    TaskFinopsAnalyticsService taskFinopsAnalyticsService(
            TaskFinopsOperationsPort operations
    ) {
        return new TaskFinopsAnalyticsService(operations);
    }
}
