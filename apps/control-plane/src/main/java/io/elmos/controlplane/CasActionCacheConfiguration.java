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
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.time.Clock;
import java.util.Map;

/** Wires the durable ActionCache index without claiming an execution-path caller exists. */
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
            @Value("${elmos.action-cache.sample-recompute-one-in-n:0}") int sampleOneInN
    ) {
        return new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(),
                new ActionCache.SampleRecomputePolicy(sampleOneInN),
                clock::millis, new CasMetrics(), index, CasTelemetry.noop());
    }

    @Bean
    ActionCacheStatus actionCacheStatus(TenantCasStore store) {
        return new ActionCacheStatus(
                "JDBC_POSTGRESQL", "JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT", "NOT_WIRED",
                "PERSISTED_DECISION_NOT_CRYPTOGRAPHICALLY_REVERIFIED",
                store.physicalNamespace(), store.atRestProtection(), false);
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
