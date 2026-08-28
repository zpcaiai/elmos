package io.elmos.commercialadapter;

import io.elmos.commercial.PricingPlanCatalog;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnBean(name = "commercialBillingJdbcClient")
public final class BillingDatabaseHealthIndicator implements HealthIndicator {
    private final JdbcClient jdbc;

    public BillingDatabaseHealthIndicator(JdbcClient commercialBillingJdbcClient) {
        this.jdbc = commercialBillingJdbcClient;
    }

    @Override
    public Health health() {
        try {
            boolean ready = jdbc.sql("""
                    select exists(
                        select 1 from self_service_pricing_plan_versions
                         where catalog_version = :catalog
                    ) and to_regprocedure(
                        'elmos_reserve_usage(character varying,character varying,character varying,character varying,character varying,numeric,numeric,timestamp with time zone)'
                    ) is not null
                    """).param("catalog", PricingPlanCatalog.CATALOG_VERSION)
                    .query(Boolean.class).single();
            return ready
                    ? Health.up().withDetail("schema", "self-service-billing-v49").build()
                    : Health.down().withDetail("schema", "missing-or-stale").build();
        } catch (RuntimeException error) {
            return Health.down().withDetail("schema", "unavailable").build();
        }
    }
}
