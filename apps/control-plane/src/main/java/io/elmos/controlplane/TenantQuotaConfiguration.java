package io.elmos.controlplane;

import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.persistence.JdbcSelfServiceBillingStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Binds the billing store into the control plane so an operator can review and
 * adjust a tenant's allowance from the operations console.
 *
 * <p>The store is constructed here rather than imported from
 * {@code apps/commercial-api}. Bean definitions do not cross application
 * boundaries: {@code BillingDatabaseConfiguration} lives in the commercial API's
 * context and nothing in it is visible to this one. Declaring a required
 * dependency on a bean that is defined in another application would compile
 * cleanly, pass every unit test, and then fail at startup with
 * {@code NoSuchBeanDefinitionException} -- a failure mode that only a real boot
 * catches.
 *
 * <p>Both collaborators the store needs are already available here:
 * {@code JdbcClient} comes from Spring Boot's auto-configuration over the
 * control plane's own DataSource, and the transaction manager likewise. The
 * store binds the tenant to each transaction itself, so sharing the connection
 * pool with the rest of the control plane does not widen anyone's data access.
 */
@Configuration
class TenantQuotaConfiguration {

    /**
     * Spring Boot auto-configures a {@link PlatformTransactionManager} but not a
     * {@link TransactionTemplate}. The store needs the template because it binds
     * {@code app.organization_id} inside the same transaction as the query --
     * a connection-scoped setting is worthless if the query runs on a different
     * connection.
     */
    @Bean
    TransactionTemplate billingTransactionTemplate(PlatformTransactionManager transactionManager) {
        return new TransactionTemplate(transactionManager);
    }

    @Bean
    SelfServiceBillingPort selfServiceBillingPort(
            JdbcClient jdbc,
            TransactionTemplate billingTransactionTemplate
    ) {
        return new JdbcSelfServiceBillingStore(jdbc, billingTransactionTemplate);
    }
}
