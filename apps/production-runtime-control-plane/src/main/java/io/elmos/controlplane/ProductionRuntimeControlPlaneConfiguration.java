package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.HttpProductionWorkerGateway;
import io.elmos.productionruntime.HttpProductionBillingClient;
import io.elmos.productionruntime.HttpTransactionalOutboxTransport;
import io.elmos.productionruntime.ProductionRuntimeCoordinator;
import io.elmos.productionruntime.ProductionRuntimeRecoveryService;
import io.elmos.productionruntime.ProductionRuntimeScheduler;
import io.elmos.productionruntime.ProductionRuntimeSchedulingService;
import io.elmos.productionruntime.ProductionBillingPort;
import io.elmos.productionruntime.ProductionModelCallExecutor;
import io.elmos.productionruntime.ProductionModelCallRecoveryService;
import io.elmos.productionruntime.ProductionModelProviderRegistry;
import io.elmos.productionruntime.ProductionRuntimeSettlementReconciler;
import io.elmos.productionruntime.ProductionRuntimeStore;
import io.elmos.productionruntime.TransactionalOutboxPublisher;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import java.nio.file.Path;
import java.net.URI;
import java.time.Duration;

/** Dedicated scheduler, billing, recovery and projector wiring only. */
@Configuration
@ConditionalOnProperty(prefix = "elmos.production-runtime", name = "enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' != 'migration'")
class ProductionRuntimeControlPlaneConfiguration {
    @Bean("productionDispatchTaskScheduler")
    ThreadPoolTaskScheduler productionDispatchTaskScheduler() {
        return taskScheduler("production-dispatch-loop-", 1);
    }

    @Bean("productionRecoveryTaskScheduler")
    ThreadPoolTaskScheduler productionRecoveryTaskScheduler() {
        return taskScheduler("production-recovery-loop-", 1);
    }

    @Bean("productionMaintenanceTaskScheduler")
    ThreadPoolTaskScheduler productionMaintenanceTaskScheduler() {
        return taskScheduler("production-maintenance-loop-", 2);
    }

    private static ThreadPoolTaskScheduler taskScheduler(String prefix, int poolSize) {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(poolSize);
        scheduler.setThreadNamePrefix(prefix);
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(15);
        return scheduler;
    }

    @Bean
    ProductionRuntimeControlPlaneMetrics productionRuntimeControlPlaneMetrics(
            MeterRegistry meters
    ) {
        return new ProductionRuntimeControlPlaneMetrics(meters);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.gate",
            name = "enabled",
            havingValue = "true")
    ProductionRuntimeGateAuthenticator productionRuntimeGateAuthenticator(
            @Value("${elmos.production-runtime.gate.token-file}") Path tokenFile
    ) {
        return new ProductionRuntimeGateAuthenticator(tokenFile);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.gate",
            name = "enabled",
            havingValue = "true")
    ProductionRuntimeGateFixture productionRuntimeGateFixture(
            @Value("${elmos.production-runtime.gate.fixture-file}") Path fixtureFile,
            ObjectMapper json
    ) {
        return ProductionRuntimeGateFixture.load(fixtureFile, json);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.billing",
            name = "adapter",
            havingValue = "http")
    ProductionBillingPort productionRemoteBillingPort(
            ObjectMapper json,
            ProductionRuntimeInternalAuthenticator authenticator,
            @Value("${elmos.production-runtime.billing.endpoint}") URI endpoint,
            @Value("${elmos.production-runtime.billing.connect-timeout:PT2S}") Duration connectTimeout,
            @Value("${elmos.production-runtime.billing.request-timeout:PT15S}") Duration requestTimeout,
            @Value("${elmos.production-runtime.service-mesh-http:false}") boolean serviceMeshHttp
    ) {
        return new HttpProductionBillingClient(
                endpoint, authenticator::credential, json,
                connectTimeout, requestTimeout, serviceMeshHttp);
    }

    @Bean
    ProductionRuntimeInternalAuthenticator productionRuntimeInternalAuthenticator(
            @Value("${elmos.production-runtime.workload-token-file}") Path tokenFile
    ) {
        return new ProductionRuntimeInternalAuthenticator(tokenFile);
    }

    @Bean
    @ConditionalOnExpression("'${component:scheduler}' == 'billing'")
    ProductionRuntimeTopUpAuthenticator productionRuntimeTopUpAuthenticator(
            @Value("${elmos.production-runtime.topup.token-file}") Path tokenFile
    ) {
        return new ProductionRuntimeTopUpAuthenticator(tokenFile);
    }

    @Bean
    HttpProductionWorkerGateway productionRuntimeWorkerGateway(
            ObjectMapper json,
            ProductionRuntimeInternalAuthenticator authenticator,
            @Value("${elmos.production-runtime.worker-connect-timeout:PT2S}") Duration connectTimeout,
            @Value("${elmos.production-runtime.worker-request-timeout:PT10S}") Duration requestTimeout,
            @Value("${elmos.production-runtime.service-mesh-http:false}") boolean serviceMeshHttp
    ) {
        return new HttpProductionWorkerGateway(
                json, authenticator::credential, connectTimeout, requestTimeout, serviceMeshHttp);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "elmos.production-runtime.outbox",
            name = "enabled",
            havingValue = "true")
    TransactionalOutboxPublisher productionRuntimeOutboxPublisher(
            ProductionRuntimeStore store,
            ObjectMapper json,
            @Value("${elmos.production-runtime.outbox.endpoint}") URI endpoint,
            @Value("${elmos.production-runtime.outbox.token-file}") Path tokenFile,
            @Value("${elmos.production-runtime.outbox.connect-timeout:PT2S}") Duration connectTimeout,
            @Value("${elmos.production-runtime.outbox.request-timeout:PT15S}") Duration requestTimeout,
            @Value("${elmos.production-runtime.service-mesh-http:false}") boolean serviceMeshHttp
    ) {
        var credential = new io.elmos.productionruntime.OwnerOnlyProviderCredentialFile(tokenFile);
        return new TransactionalOutboxPublisher(
                store,
                new HttpTransactionalOutboxTransport(
                        endpoint, credential::read, json,
                        connectTimeout, requestTimeout, serviceMeshHttp));
    }

    @Bean
    ProductionRuntimeLoop productionRuntimeLoop(
            ProductionRuntimeSchedulingService scheduling,
            ProductionRuntimeRecoveryService recovery,
            ProductionRuntimeScheduler scheduler,
            ProductionRuntimeStore store,
            ProductionBillingPort billing,
            ProductionRuntimeSettlementReconciler settlements,
            ProductionModelCallExecutor modelCalls,
            ObjectProvider<ProductionModelProviderRegistry> providerRegistry,
            ObjectProvider<TransactionalOutboxPublisher> outboxPublisher,
            HttpProductionWorkerGateway workers,
            ProductionRuntimeControlPlaneMetrics metrics,
            @Value("${component:scheduler}") String component,
            @Value("${elmos.production-runtime.scheduler-batch-size:64}") int batchSize,
            @Value("${elmos.production-runtime.lease-grace:PT5S}") Duration leaseGrace,
            @Value("${elmos.production-runtime.model-reconcile-max-attempts:20}") int modelReconcileAttempts
    ) {
        ProductionModelProviderRegistry registry = providerRegistry.getIfAvailable();
        ProductionModelCallRecoveryService modelRecovery = registry == null ? null
                : new ProductionModelCallRecoveryService(
                        billing, modelCalls, registry, modelReconcileAttempts);
        return new ProductionRuntimeLoop(
                scheduling, recovery, scheduler, store, billing, settlements,
                modelRecovery, outboxPublisher.getIfAvailable(), workers,
                metrics, component, batchSize, leaseGrace);
    }

    static final class ProductionRuntimeLoop {
        private final ProductionRuntimeSchedulingService scheduling;
        private final ProductionRuntimeRecoveryService recovery;
        private final ProductionRuntimeScheduler scheduler;
        private final ProductionRuntimeStore store;
        private final ProductionBillingPort billing;
        private final ProductionRuntimeSettlementReconciler settlements;
        private final ProductionModelCallRecoveryService modelRecovery;
        private final TransactionalOutboxPublisher outboxPublisher;
        private final HttpProductionWorkerGateway workers;
        private final ProductionRuntimeControlPlaneMetrics metrics;
        private final String component;
        private final int batchSize;
        private final Duration leaseGrace;

        ProductionRuntimeLoop(
                ProductionRuntimeSchedulingService scheduling,
                ProductionRuntimeRecoveryService recovery,
                ProductionRuntimeScheduler scheduler,
                ProductionRuntimeStore store,
                ProductionBillingPort billing,
                ProductionRuntimeSettlementReconciler settlements,
                ProductionModelCallRecoveryService modelRecovery,
                TransactionalOutboxPublisher outboxPublisher,
                HttpProductionWorkerGateway workers,
                ProductionRuntimeControlPlaneMetrics metrics,
                String component,
                int batchSize,
                Duration leaseGrace
        ) {
            if (batchSize < 1 || batchSize > 1000) {
                throw new IllegalArgumentException("scheduler batch size must be between 1 and 1000");
            }
            this.scheduling = scheduling;
            this.recovery = recovery;
            this.scheduler = scheduler;
            this.store = store;
            this.billing = billing;
            this.settlements = settlements;
            this.modelRecovery = modelRecovery;
            this.outboxPublisher = outboxPublisher;
            this.workers = workers;
            this.metrics = metrics;
            this.component = component;
            this.batchSize = batchSize;
            this.leaseGrace = leaseGrace;
        }

        @Scheduled(
                fixedDelayString = "${elmos.production-runtime.scheduler-interval-ms:1000}",
                scheduler = "productionDispatchTaskScheduler")
        void schedule() {
            if ("scheduler".equals(component)) {
                metrics.record(component, "schedule", () -> scheduling.schedule(batchSize, workers));
            }
        }

        @Scheduled(
                fixedDelayString = "${elmos.production-runtime.recovery-interval-ms:5000}",
                scheduler = "productionRecoveryTaskScheduler")
        void recover() {
            if (!"scheduler".equals(component)) return;
            metrics.record(component, "recover", () -> {
                scheduler.expireLeases(leaseGrace);
                recovery.recover(batchSize, workers);
            });
        }

        @Scheduled(
                fixedDelayString = "${elmos.production-runtime.billing-recovery-interval-ms:5000}",
                scheduler = "productionMaintenanceTaskScheduler")
        void recoverBilling() {
            if (!"billing".equals(component)) return;
            metrics.record(component, "billing-recovery", () -> {
                billing.expireReservations(batchSize);
                for (var tenantId : store.pendingSettlementTenants(batchSize)) {
                    settlements.reconcile(tenantId, batchSize);
                }
                if (modelRecovery != null) modelRecovery.recover(batchSize);
            });
        }

        @Scheduled(
                fixedDelayString = "${elmos.production-runtime.projector-interval-ms:1000}",
                scheduler = "productionMaintenanceTaskScheduler")
        void rebuildProjections() {
            if (!"projector".equals(component)) return;
            metrics.record(component, "projection", () -> {
                for (var candidate : store.projectionCandidates(batchSize)) {
                    scheduler.rebuildProgress(candidate.tenantId(), candidate.jobId());
                }
            });
        }

        @Scheduled(
                fixedDelayString = "${elmos.production-runtime.outbox.interval-ms:1000}",
                scheduler = "productionMaintenanceTaskScheduler")
        void publishOutbox() {
            if (!"projector".equals(component) || outboxPublisher == null) return;
            metrics.record(component, "outbox", () ->
                    outboxPublisher.publish(batchSize, Duration.ofSeconds(30)));
        }
    }
}
