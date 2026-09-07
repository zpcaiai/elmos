package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.time.Clock;

@Configuration(proxyBeanMethods = false)
final class ServerOperationAuditConfiguration implements WebMvcConfigurer {
    private final ServerOperationAuditInterceptor interceptor;

    ServerOperationAuditConfiguration(
            JdbcUserActivityStore store,
            Clock clock,
            @Value("${elmos.operations.organization-id:}") String organizationId,
            @Value("${elmos.operations.actor-id:}") String actorId
    ) {
        this.interceptor = new ServerOperationAuditInterceptor(
                store, clock, organizationId, actorId);
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/v1/**", "/api/webhooks/**");
    }
}
