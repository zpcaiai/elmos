package io.elmos.controlplane;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionCacheIndex;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.JdbcActionCacheIndex;
import io.elmos.cas.TenantCasStore;
import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.time.Clock;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;

class CasActionCacheConfigurationTest {

    @Test void explicitEnablementWiresJdbcAndFailsClosedWithoutACurrentTrustProvider() {
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
                    assertEquals("ASYNC_DISPATCHER_AVAILABLE_NOT_BOUND_TO_TENANT_API",
                            status.executionCaller());
                    assertEquals("FAIL_CLOSED_CURRENT_TRUST_NOT_CONFIGURED",
                            status.trustDecisionReadback());
                    assertEquals("NOT_BOUND_RUNNER_COMPLETION_LACKS_SIGNED_ACTION_RESULT",
                            status.completionWriteback());
                    assertEquals("GLOBAL_DIGEST", status.physicalNamespace());
                    assertEquals("NOT_CONFIGURED", status.atRestProtection());
                    assertFalse(status.productionCertified());

                    Info.Builder builder = new Info.Builder();
                    context.getBean(InfoContributor.class).contribute(builder);
                    Map<?, ?> info = (Map<?, ?>) builder.build().getDetails().get("actionCache");
                    assertEquals("JDBC_POSTGRESQL", info.get("index"));
                    assertEquals("JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT",
                            info.get("crossInstanceLookup"));
                    assertEquals("ASYNC_DISPATCHER_AVAILABLE_NOT_BOUND_TO_TENANT_API",
                            info.get("executionCaller"));
                    assertEquals("FAIL_CLOSED_CURRENT_TRUST_NOT_CONFIGURED",
                            info.get("trustDecisionReadback"));
                    assertEquals("NOT_BOUND_RUNNER_COMPLETION_LACKS_SIGNED_ACTION_RESULT",
                            info.get("completionWriteback"));
                    assertEquals("GLOBAL_DIGEST", info.get("physicalNamespace"));
                    assertEquals("NOT_CONFIGURED", info.get("atRestProtection"));
                    assertEquals("NOT_CERTIFIED", info.get("productionCertification"));
                });
    }

    @Test void anExplicitCurrentTrustProviderReplacesTheFailClosedDefault() {
        ActionCache.TrustRevalidator currentTrust = currentTrust();
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withBean(ActionCache.TrustRevalidator.class, () -> currentTrust)
                .withPropertyValues("elmos.action-cache.enabled=true")
                .run(context -> {
                    assertEquals(currentTrust,
                            context.getBean(ActionCache.TrustRevalidator.class));
                    assertEquals("CURRENT_TRUST_TEST_PROVIDER", context.getBean(
                                    CasActionCacheConfiguration.ActionCacheStatus.class)
                            .trustDecisionReadback());
                });
    }

    @Test void peerConfigurationOrderCannotCreateADefaultTrustCollision() {
        new ApplicationContextRunner()
                .withUserConfiguration(
                        CasActionCacheConfiguration.class, PeerTrustConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withPropertyValues("elmos.action-cache.enabled=true")
                .run(context -> {
                    assertEquals(1,
                            context.getBeansOfType(ActionCache.TrustRevalidator.class).size());
                    assertEquals("CURRENT_TRUST_TEST_PROVIDER", context.getBean(
                                    CasActionCacheConfiguration.ActionCacheStatus.class)
                            .trustDecisionReadback());
                });
    }

    @Test void executionCallerEnablementFailsClosedWithoutDeploymentPorts() {
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withBean(ExecutionJobPort.class, () -> mock(ExecutionJobPort.class))
                .withBean(ActionCacheExecutionJobDispatcher.Authorizer.class,
                        () -> CasActionCacheConfigurationTest::allow)
                .withPropertyValues(
                        "elmos.action-cache.enabled=true",
                        "elmos.action-cache.execution-caller-enabled=true")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                    assertEquals(
                            "exactly one current ActionCache trust provider is required when "
                                    + "the ActionCache execution caller is enabled",
                            rootCause(context.getStartupFailure()).getMessage());
                });
    }

    @Test void executionCallerBindsOnlyWithExactTrustAuthorizationAndDurableJobPort() {
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class,
                        ActionCacheExecutionController.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withBean(ActionCache.TrustRevalidator.class,
                        CasActionCacheConfigurationTest::currentTrust)
                .withBean(ActionCacheExecutionJobDispatcher.Authorizer.class,
                        () -> CasActionCacheConfigurationTest::allow)
                .withBean(ActionCacheExecutionJobDispatcher.PayloadPolicy.class,
                        CasActionCacheConfigurationTest::payloadPolicy)
                .withBean(ExecutionJobPort.class, () -> mock(ExecutionJobPort.class))
                .withPropertyValues(
                        "elmos.action-cache.enabled=true",
                        "elmos.action-cache.execution-caller-enabled=true",
                        "elmos.action-cache.data-residency=eu-west")
                .run(context -> {
                    assertNotNull(context.getBean(ActionCacheExecutionJobDispatcher.class));
                    assertEquals("OPT_IN_DURABLE_HIT_OR_ENQUEUE_TENANT_API_BOUND",
                            context.getBean(CasActionCacheConfiguration.ActionCacheStatus.class)
                                    .executionCaller());
                    assertFalse(context.getBean(
                            CasActionCacheConfiguration.ActionCacheStatus.class)
                            .productionCertified());
                });
    }

    @Test void executionCallerFailsClosedWithoutExactlyOnePayloadPolicy() {
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withBean(ActionCache.TrustRevalidator.class,
                        CasActionCacheConfigurationTest::currentTrust)
                .withBean(ActionCacheExecutionJobDispatcher.Authorizer.class,
                        () -> CasActionCacheConfigurationTest::allow)
                .withBean(ExecutionJobPort.class, () -> mock(ExecutionJobPort.class))
                .withPropertyValues(
                        "elmos.action-cache.enabled=true",
                        "elmos.action-cache.execution-caller-enabled=true")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                    assertEquals(
                            "exactly one ActionCache dispatch payload policy is required when "
                                    + "the ActionCache execution caller is enabled",
                            rootCause(context.getStartupFailure()).getMessage());
                });
    }

    @Test void executionCallerRejectsPersistedDecisionCompatibilityAsCurrentTrust() {
        new ApplicationContextRunner()
                .withUserConfiguration(CasActionCacheConfiguration.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(Clock.class, Clock::systemUTC)
                .withBean(TenantCasStore.class,
                        () -> TenantCasStore.global(new InMemoryCasStore("action-output")))
                .withBean(ActionCache.TrustRevalidator.class,
                        ActionCache.TrustRevalidator::persistedDecisionCompatibility)
                .withBean(ActionCacheExecutionJobDispatcher.Authorizer.class,
                        () -> CasActionCacheConfigurationTest::allow)
                .withBean(ActionCacheExecutionJobDispatcher.PayloadPolicy.class,
                        CasActionCacheConfigurationTest::payloadPolicy)
                .withBean(ExecutionJobPort.class, () -> mock(ExecutionJobPort.class))
                .withPropertyValues(
                        "elmos.action-cache.enabled=true",
                        "elmos.action-cache.execution-caller-enabled=true")
                .run(context -> {
                    assertNotNull(context.getStartupFailure());
                    assertEquals(
                            "ActionCache execution caller requires a real current trust "
                                    + "revalidator; compatibility and fail-closed placeholder "
                                    + "modes are not executable",
                            rootCause(context.getStartupFailure()).getMessage());
                });
    }

    private static ActionCacheExecutionJobDispatcher.AuthorizationDecision allow(
            ActionCacheExecutionJobDispatcher.Request request,
            ActionCacheExecutionJobDispatcher.Operation operation
    ) {
        return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                "TEST_" + operation.name(),
                new ActionCacheExecutionJobDispatcher.AuthorizationGrant(
                        request.reader().tenantId(), request.dispatch().actorId(),
                        request.key().components().get("project_id"),
                        "decision-test", "policy-v1"));
    }

    private static ActionCacheExecutionJobDispatcher.PayloadPolicy payloadPolicy() {
        return context -> new ActionCacheExecutionJobDispatcher.SanitizedPayload(
                "TEST_PAYLOAD_ALLOWLIST", "v1", context.request().dispatch().payload());
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    private static ActionCache.TrustRevalidator currentTrust() {
        return new ActionCache.TrustRevalidator() {
            @Override
            public ActionCache.TrustDecision revalidate(ActionCache.Entry entry,
                                                         long nowEpochMillis) {
                return ActionCache.TrustDecision.trusted("TEST_CURRENT_TRUST");
            }

            @Override
            public String mode() {
                return "CURRENT_TRUST_TEST_PROVIDER";
            }
        };
    }

    @Configuration(proxyBeanMethods = false)
    static class PeerTrustConfiguration {
        @Bean
        ActionCache.TrustRevalidator peerTrustRevalidator() {
            return currentTrust();
        }
    }
}
