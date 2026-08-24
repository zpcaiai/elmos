package io.elmos.controlplane;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionCacheIndex;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.JdbcActionCacheIndex;
import io.elmos.cas.TenantCasStore;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import javax.sql.DataSource;
import java.time.Clock;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;

class CasActionCacheConfigurationTest {

    @Test void explicitEnablementWiresTheJdbcIndexButReportsTheMissingExecutionCaller() {
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withPropertyValues("elmos.action-cache.enabled=true")
                .run(context -> {
                    assertNotNull(context.getBean(ActionCache.class));
                    assertInstanceOf(JdbcActionCacheIndex.class,
                            context.getBean(ActionCacheIndex.class));
                    var status = context.getBean(
                            CasActionCacheConfiguration.ActionCacheStatus.class);
                    assertEquals("JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT",
                            status.crossInstanceLookup());
                    assertEquals("NOT_WIRED", status.executionCaller());
                    assertEquals("PERSISTED_DECISION_NOT_CRYPTOGRAPHICALLY_REVERIFIED",
                            status.trustDecisionReadback());
                    assertEquals("GLOBAL_DIGEST", status.physicalNamespace());
                    assertEquals("NOT_CONFIGURED", status.atRestProtection());
                    assertFalse(status.productionCertified());

                    Info.Builder builder = new Info.Builder();
                    context.getBean(InfoContributor.class).contribute(builder);
                    Map<?, ?> info = (Map<?, ?>) builder.build().getDetails().get("actionCache");
                    assertEquals("JDBC_POSTGRESQL", info.get("index"));
                    assertEquals("JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT",
                            info.get("crossInstanceLookup"));
                    assertEquals("NOT_WIRED", info.get("executionCaller"));
                    assertEquals("PERSISTED_DECISION_NOT_CRYPTOGRAPHICALLY_REVERIFIED",
                            info.get("trustDecisionReadback"));
                    assertEquals("GLOBAL_DIGEST", info.get("physicalNamespace"));
                    assertEquals("NOT_CONFIGURED", info.get("atRestProtection"));
                    assertEquals("NOT_CERTIFIED", info.get("productionCertification"));
                });
    }
}
