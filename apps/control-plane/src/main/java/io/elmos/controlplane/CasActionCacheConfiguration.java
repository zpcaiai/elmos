package io.elmos.controlplane;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionCacheIndex;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasMetrics;
import io.elmos.cas.CasTelemetry;
import io.elmos.cas.JdbcActionCacheIndex;
import io.elmos.cas.TenantCasStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.time.Clock;
import java.util.Map;

/** Wires the durable ActionCache index and current-trust port without claiming caller binding. */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "elmos.action-cache.enabled", havingValue = "true")
class CasActionCacheConfiguration {

    record ActionCacheStatus(String index, String crossInstanceLookup,
                             String executionCaller, String trustDecisionReadback,
                             String physicalNamespace, String atRestProtection,
                             boolean productionCertified) {
    }

    @Bean
    ActionCacheIndex actionCacheIndex(DataSource dataSource) {
        return new JdbcActionCacheIndex(dataSource);
    }

    @Bean
    ActionCache actionCache(
            TenantCasStore store,
            ActionCacheIndex index,
            Clock clock,
            ObjectProvider<ActionCache.TrustRevalidator> trustProviders,
            @Value("${elmos.action-cache.sample-recompute-one-in-n:0}") int sampleOneInN
    ) {
        return new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(),
                new ActionCache.SampleRecomputePolicy(sampleOneInN),
                clock::millis, new CasMetrics(), index, CasTelemetry.noop(),
                resolveTrustRevalidator(trustProviders));
    }

    @Bean
    ActionCacheStatus actionCacheStatus(TenantCasStore store,
                                        ObjectProvider<ActionCache.TrustRevalidator> trustProviders) {
        ActionCache.TrustRevalidator trustRevalidator =
                resolveTrustRevalidator(trustProviders);
        return new ActionCacheStatus(
                "JDBC_POSTGRESQL", "JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT",
                "TYPED_CALLER_AVAILABLE_NOT_BOUND_TO_EXECUTION_SERVICE",
                trustRevalidator.mode(),
                store.physicalNamespace(), store.atRestProtection(), false);
    }

    private static ActionCache.TrustRevalidator resolveTrustRevalidator(
            ObjectProvider<ActionCache.TrustRevalidator> providers
    ) {
        java.util.List<ActionCache.TrustRevalidator> candidates =
                providers.orderedStream().toList();
        if (candidates.isEmpty()) {
            return ActionCache.TrustRevalidator.failClosedNotConfigured();
        }
        if (candidates.size() != 1) {
            throw new IllegalStateException(
                    "exactly one current ActionCache trust provider is required");
        }
        return candidates.get(0);
    }

    @Bean
    InfoContributor actionCacheInfoContributor(ActionCacheStatus status) {
        return builder -> builder.withDetail("actionCache", Map.of(
                "index", status.index(),
                "crossInstanceLookup", status.crossInstanceLookup(),
                "executionCaller", status.executionCaller(),
                "trustDecisionReadback", status.trustDecisionReadback(),
                "physicalNamespace", status.physicalNamespace(),
                "atRestProtection", status.atRestProtection(),
                "productionCertification",
                status.productionCertified() ? "CERTIFIED" : "NOT_CERTIFIED"));
    }
}
