package io.elmos.controlplane;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionCacheIndex;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasMetrics;
import io.elmos.cas.CasTelemetry;
import io.elmos.cas.JdbcActionCacheIndex;
import io.elmos.cas.TenantCasStore;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.time.Clock;
import java.util.Map;

/**
 * Wires the durable ActionCache index and its opt-in asynchronous dispatch seam.
 *
 * <p>The dispatcher is deliberately absent unless the deployment explicitly enables it and
 * supplies exactly one current-trust provider, authorizer, typed payload policy and durable job
 * port. This prevents a partially configured cache from silently becoming an execution
 * authority or persisting unsanitized caller payload. The tenant API binding is enabled only
 * alongside that dispatcher and still requires deployment-owned data residency configuration.
 * Runner completion does not carry a signed ActionResult, so completion write-back is deliberately
 * not claimed here.</p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "elmos.action-cache.enabled", havingValue = "true")
class CasActionCacheConfiguration {

    record ActionCacheStatus(String index, String crossInstanceLookup,
                             String executionCaller, String trustDecisionReadback,
                             String completionWriteback,
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
    @ConditionalOnProperty(
            name = "elmos.action-cache.execution-caller-enabled", havingValue = "true")
    ActionCacheExecutionJobDispatcher actionCacheExecutionJobDispatcher(
            ActionCache cache,
            ObjectProvider<ActionCache.TrustRevalidator> trustProviders,
            ObjectProvider<ActionCacheExecutionJobDispatcher.Authorizer> authorizers,
            ObjectProvider<ExecutionJobPort> jobPorts,
            ObjectProvider<ActionCacheExecutionJobDispatcher.PayloadPolicy> payloadPolicies
    ) {
        ActionCache.TrustRevalidator currentTrust = requireSingleDeploymentPort(
                trustProviders, "current ActionCache trust provider");
        requireCurrentTrustMode(currentTrust);
        return new ActionCacheExecutionJobDispatcher(
                cache,
                requireSingleDeploymentPort(jobPorts, "durable execution job port"),
                requireSingleDeploymentPort(authorizers, "ActionCache dispatch authorizer"),
                requireSingleDeploymentPort(payloadPolicies,
                        "ActionCache dispatch payload policy"));
    }

    @Bean
    ActionCacheStatus actionCacheStatus(TenantCasStore store,
                                        ObjectProvider<ActionCache.TrustRevalidator> trustProviders,
                                        ObjectProvider<ActionCacheExecutionJobDispatcher> callers,
                                        ObjectProvider<ActionCacheExecutionController> bindings) {
        ActionCache.TrustRevalidator trustRevalidator =
                resolveTrustRevalidator(trustProviders);
        java.util.List<ActionCacheExecutionJobDispatcher> configuredCallers =
                callers.orderedStream().toList();
        if (configuredCallers.size() > 1) {
            throw new IllegalStateException(
                    "exactly one ActionCache execution caller is permitted");
        }
        java.util.List<ActionCacheExecutionController> configuredBindings =
                bindings.orderedStream().toList();
        if (configuredBindings.size() > 1) {
            throw new IllegalStateException(
                    "exactly one ActionCache tenant execution binding is permitted");
        }
        return new ActionCacheStatus(
                "JDBC_POSTGRESQL", "JDBC_INDEX_CONFIGURED_OBJECT_TIER_DEPENDENT",
                configuredCallers.isEmpty()
                        ? "ASYNC_DISPATCHER_AVAILABLE_NOT_BOUND_TO_TENANT_API"
                        : configuredBindings.isEmpty()
                                ? "OPT_IN_DURABLE_HIT_OR_ENQUEUE_NOT_BOUND_TO_TENANT_API"
                                : configuredBindings.get(0).deploymentPolicyConfigured()
                                        ? "OPT_IN_DURABLE_HIT_OR_ENQUEUE_TENANT_API_BOUND"
                                        : "OPT_IN_DURABLE_HIT_OR_ENQUEUE_TENANT_API_BOUND_"
                                                + "CONFIGURATION_REQUIRED",
                trustRevalidator.mode(),
                "NOT_BOUND_RUNNER_COMPLETION_LACKS_SIGNED_ACTION_RESULT",
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

    private static <T> T requireSingleDeploymentPort(
            ObjectProvider<T> providers, String description
    ) {
        java.util.List<T> candidates = providers.orderedStream().toList();
        if (candidates.size() != 1) {
            throw new IllegalStateException(
                    "exactly one " + description + " is required when the ActionCache "
                            + "execution caller is enabled");
        }
        return candidates.get(0);
    }

    private static void requireCurrentTrustMode(
            ActionCache.TrustRevalidator trustRevalidator
    ) {
        String mode = trustRevalidator.mode();
        if (mode == null || mode.isBlank()
                || "PERSISTED_DECISION_COMPATIBILITY_ONLY".equals(mode)
                || mode.startsWith("FAIL_CLOSED_")) {
            throw new IllegalStateException(
                    "ActionCache execution caller requires a real current trust revalidator; "
                            + "compatibility and fail-closed placeholder modes are not executable");
        }
    }

    @Bean
    InfoContributor actionCacheInfoContributor(ActionCacheStatus status) {
        return builder -> builder.withDetail("actionCache", Map.of(
                "index", status.index(),
                "crossInstanceLookup", status.crossInstanceLookup(),
                "executionCaller", status.executionCaller(),
                "trustDecisionReadback", status.trustDecisionReadback(),
                "completionWriteback", status.completionWriteback(),
                "physicalNamespace", status.physicalNamespace(),
                "atRestProtection", status.atRestProtection(),
                "productionCertification",
                status.productionCertified() ? "CERTIFIED" : "NOT_CERTIFIED"));
    }
}
