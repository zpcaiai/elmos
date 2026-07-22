package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.health.*;
import io.elmos.integrations.OsvVulnerabilityProvider;
import io.elmos.planning.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.nio.file.Path;
import java.time.Clock;

@Configuration
class HealthPlanningConfiguration {
    @Bean Clock engineClock() { return Clock.systemUTC(); }
    @Bean HealthModels.VulnerabilityProvider vulnerabilityProvider(@Value("${elmos.worker.osv.enabled:false}") boolean enabled,
            @Value("${elmos.worker.osv.api-base:https://api.osv.dev/}") String apiBase, ObjectMapper json, Clock clock) {
        return enabled ? OsvVulnerabilityProvider.http(URI.create(apiBase), json, clock) : VulnerabilityProviders.notConfigured(clock);
    }
    @Bean JavaLegacyHealthCheck healthCheck(HealthModels.VulnerabilityProvider provider, Clock clock) { return new JavaLegacyHealthCheck(ScanPolicy.defaults(), provider, clock); }
    @Bean MigrationPlanner migrationPlanner() { return new MigrationPlanner(new CompatibilityMatrix("elmos-matrix-2026-07")); }
    @Bean WorkspacePathResolver workspacePathResolver(@Value("${elmos.worker.workspace-root:/workspace}") String root) { return new WorkspacePathResolver(Path.of(root)); }
}
