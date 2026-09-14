package io.elmos.controlplane;

import io.elmos.secret.DeploymentSecretSession;
import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.TmpfsSecretMaterializer;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Installs the actual tmpfs port; the canonical provider/store/authorization are mandatory. */
@Configuration
@ConditionalOnProperty(name = {"elmos.release-deployment.runtime-enabled", "elmos.release-deployment.secret-enabled"}, havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing'")
@EnableConfigurationProperties(DeploymentSecretConfiguration.Settings.class)
class DeploymentSecretConfiguration {
    @ConfigurationProperties(prefix = "elmos.release-deployment.secrets")
    public record Settings(Map<String, String> workspaces) {}

    @Bean
    SecretInjectionService deploymentSecretInjection(SecretInjectionService.SecretProviderPort provider,
            SecretInjectionService.SecretLeaseStore store, Settings settings) {
        if (settings.workspaces() == null || settings.workspaces().isEmpty()) {
            throw new IllegalStateException("DEPLOYMENT_SECRET_WORKSPACES_REQUIRED");
        }
        Map<String, Path> roots = settings.workspaces().entrySet().stream()
                .collect(Collectors.toUnmodifiableMap(Map.Entry::getKey, entry -> Path.of(entry.getValue())));
        return new SecretInjectionService(provider, new TmpfsSecretMaterializer(roots), store, Clock.systemUTC());
    }

    @Bean
    DeploymentSecretSession deploymentSecretSession(SecretInjectionService injection,
            DeploymentSecretSession.Authorization authorization) {
        return new DeploymentSecretSession(injection, authorization, Clock.systemUTC());
    }
}
