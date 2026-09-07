package io.elmos.liveworkbench;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("liveWorkbenchProvider")
public final class LiveWorkbenchProviderHealth implements HealthIndicator {
    private final SandboxProviderPort provider;
    public LiveWorkbenchProviderHealth(SandboxProviderPort provider) { this.provider = provider; }
    @Override public Health health() {
        if (!provider.configured())
            return Health.down().withDetail("reason", "QUALIFIED_SANDBOX_PROVIDER_NOT_CONFIGURED").build();
        return provider.ready()
                ? Health.up().withDetail("boundary", "configured-and-reachable").build()
                : Health.down().withDetail("reason", "QUALIFIED_SANDBOX_PROVIDER_UNAVAILABLE").build();
    }
}
