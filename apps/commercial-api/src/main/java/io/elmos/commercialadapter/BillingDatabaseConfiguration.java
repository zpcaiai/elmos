package io.elmos.commercialadapter;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.persistence.JdbcSelfServiceBillingStore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.sql.DataSource;

@Configuration
@ConditionalOnExpression("'${ELMOS_COMMERCIAL_DATABASE_URL:}' != ''")
public class BillingDatabaseConfiguration {
    @Bean
    DataSource commercialBillingDataSource() {
        HikariConfig config = new HikariConfig();
        config.setDriverClassName("org.postgresql.Driver");
        config.setJdbcUrl(requiredEnvironment("ELMOS_COMMERCIAL_DATABASE_URL"));
        String username = System.getenv("ELMOS_COMMERCIAL_DATABASE_USERNAME");
        String password = System.getenv("ELMOS_COMMERCIAL_DATABASE_PASSWORD");
        if (username != null && !username.isBlank()) config.setUsername(username);
        if (password != null && !password.isBlank()) config.setPassword(password);
        config.setPoolName("elmos-commercial-billing");
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(1);
        config.setConnectionTimeout(5_000);
        config.setValidationTimeout(3_000);
        config.setInitializationFailTimeout(10_000);
        config.setMaxLifetime(30 * 60_000);
        config.setKeepaliveTime(2 * 60_000);
        config.addDataSourceProperty("tcpKeepAlive", "true");
        return new HikariDataSource(config);
    }

    @Bean
    JdbcClient commercialBillingJdbcClient(DataSource commercialBillingDataSource) {
        return JdbcClient.create(commercialBillingDataSource);
    }

    @Bean
    TransactionTemplate commercialBillingTransactions(DataSource commercialBillingDataSource) {
        var transactionManager = new DataSourceTransactionManager(commercialBillingDataSource);
        return new TransactionTemplate(transactionManager);
    }

    @Bean
    SelfServiceBillingPort selfServiceBillingPort(
            JdbcClient commercialBillingJdbcClient,
            TransactionTemplate commercialBillingTransactions
    ) {
        return new JdbcSelfServiceBillingStore(
                commercialBillingJdbcClient,
                commercialBillingTransactions
        );
    }

    private static String requiredEnvironment(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is required");
        }
        return value;
    }
}
