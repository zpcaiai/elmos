package io.elmos.productionworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import io.micrometer.core.instrument.MeterRegistry;

import java.net.URI;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;

@Configuration
class ProductionWorkerConfiguration {
    @Bean
    UUID productionWorkerId(
            @Value("${elmos.production-worker.worker-id:}") String configured,
            @Value("${elmos.production-worker.identity-namespace}") UUID identityNamespace,
            @Value("${elmos.production-worker.worker-name}") String workerName
    ) {
        if (configured != null && !configured.isBlank()) return UUID.fromString(configured);
        if (workerName == null || workerName.isBlank() || workerName.length() > 160) {
            throw new IllegalArgumentException("workerName is required for stable worker identity");
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                    (identityNamespace + ":" + workerName).getBytes(StandardCharsets.UTF_8));
            digest[6] = (byte) ((digest[6] & 0x0f) | 0x50);
            digest[8] = (byte) ((digest[8] & 0x3f) | 0x80);
            long high = 0;
            long low = 0;
            for (int i = 0; i < 8; i++) high = (high << 8) | (digest[i] & 0xffL);
            for (int i = 8; i < 16; i++) low = (low << 8) | (digest[i] & 0xffL);
            return new UUID(high, low);
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    @Bean
    OwnerOnlyProviderCredentialFile productionWorkerCredential(
            @Value("${elmos.production-worker.workload-token-file}") Path path
    ) {
        return new OwnerOnlyProviderCredentialFile(path);
    }

    @Bean
    ProductionWorkerRouteCatalog productionWorkerRouteCatalog(
            @Value("${elmos.production-worker.route-catalog-file}") Path path,
            ObjectMapper json,
            @Value("${elmos.production-worker.service-mesh-http:false}") boolean meshHttp
    ) {
        return new ProductionWorkerRouteCatalog(path, json, meshHttp);
    }

    @Bean
    ProductionWorkerAttemptService productionWorkerAttemptService(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            @Qualifier("productionWorkerId") UUID workerId,
            @Value("${elmos.production-worker.control-plane-url}") URI controlPlane,
            @Value("${elmos.production-worker.max-concurrent-attempts:4}") int concurrency,
            @Value("${elmos.production-worker.max-retained-attempts:10000}") int retained,
            @Value("${elmos.production-worker.state-directory}") Path stateDirectory,
            @Value("${elmos.production-worker.service-mesh-http:false}") boolean meshHttp
    ) {
        return new ProductionWorkerAttemptService(
                json, routes, credential, workerId, controlPlane, concurrency, retained,
                stateDirectory, meshHttp);
    }

    @Bean
    ProductionWorkerRegistrationLoop productionWorkerRegistrationLoop(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            @Qualifier("productionWorkerId") UUID workerId,
            @Value("${elmos.production-worker.worker-name}") String workerName,
            @Value("${elmos.production-worker.worker-type}") String workerType,
            @Value("${elmos.production-worker.advertised-endpoint}") URI endpoint,
            @Value("${elmos.production-worker.control-plane-url}") URI controlPlane,
            @Value("${elmos.production-worker.region:}") String region,
            @Value("${elmos.production-worker.zone:}") String zone,
            @Value("${elmos.production-worker.max-concurrent-attempts:4}") int maxConcurrent,
            ProductionWorkerAttemptService attempts,
            @Value("${elmos.production-worker.service-mesh-http:false}") boolean meshHttp
    ) {
        return new ProductionWorkerRegistrationLoop(
                json, routes, credential, workerId, workerName, workerType, endpoint,
                controlPlane, region, zone, maxConcurrent, attempts, meshHttp);
    }

    @Bean(name = "productionWorkerJournal")
    HealthIndicator productionWorkerJournalHealth(
            ProductionWorkerAttemptService attempts
    ) {
        return () -> attempts.journalHealthy()
                ? Health.up().build()
                : Health.down().withDetail("code", "WORKER_DURABLE_JOURNAL_FAILURE").build();
    }

    @Bean
    ProductionWorkerMetrics productionWorkerMetrics(
            MeterRegistry meters,
            ProductionWorkerAttemptService attempts
    ) {
        return new ProductionWorkerMetrics(meters, attempts);
    }
}
