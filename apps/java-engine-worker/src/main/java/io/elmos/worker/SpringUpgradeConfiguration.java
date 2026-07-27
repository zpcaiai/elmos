package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.nio.file.Path;
import java.time.Clock;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

@Configuration
class SpringUpgradeConfiguration {
    @Bean
    SpringUpgradeExecutionPort springUpgradeExecutionPort(
            @Value("${elmos.worker.spring-upgrade.enabled:false}") boolean enabled,
            @Value("${elmos.worker.spring-upgrade.rootless-runner-attested:false}") boolean rootlessRunnerAttested,
            @Value("${elmos.worker.spring-upgrade.default-deny-network-attested:false}") boolean networkPolicyAttested,
            @Value("${elmos.worker.spring-upgrade.workspace-root:/tmp/elmos-private-runner}") String workspaceRoot,
            @Value("${elmos.worker.spring-upgrade.source-java-home:/opt/java/openjdk-17}") String sourceJavaHome,
            @Value("${elmos.worker.spring-upgrade.target-java-home:/opt/java/openjdk-21}") String targetJavaHome,
            @Value("${elmos.worker.spring-upgrade.maven-executable:mvn}") String mavenExecutable,
            @Value("${elmos.worker.spring-upgrade.maven-dependency-seed:}") String mavenDependencySeed,
            @Value("${elmos.worker.spring-upgrade.allowed-git-hosts:github.com}") String allowedHosts,
            @Value("${elmos.worker.spring-upgrade.allow-file-repositories:false}") boolean allowFileRepositories,
            @Value("${elmos.worker.spring-upgrade.transformer-broker-enabled:false}") boolean transformerBrokerEnabled,
            @Value("${elmos.worker.spring-upgrade.transformer-broker-base-url:http://workspace-service:8082}") String transformerBrokerBaseUrl,
            @Value("${elmos.worker.spring-upgrade.transformer-broker-secret-file:/run/secrets/elmos_transformer_hmac}") String transformerBrokerSecretFile,
            @Value("${elmos.worker.spring-upgrade.local-engineering-enabled:false}") boolean localEngineeringEnabled,
            @Value("${elmos.worker.spring-upgrade.runtime-runner-enabled:false}") boolean runtimeRunnerEnabled,
            @Value("${elmos.worker.spring-upgrade.runtime-runner-base-url:http://workspace-service:8082}") String runtimeRunnerBaseUrl,
            @Value("${elmos.worker.spring-upgrade.runtime-runner-secret-file:/run/secrets/elmos_runtime_hmac}") String runtimeRunnerSecretFile,
            ObjectMapper json,
            Clock clock
    ) {
        if (!enabled) {
            return new DisabledSpringUpgradeExecutionPort(
                    "Spring upgrade execution is disabled until an approved private Runner is configured.");
        }
        if (localEngineeringEnabled && transformerBrokerEnabled) {
            throw new IllegalArgumentException(
                    "Local engineering and the rootless Transformer broker cannot both be enabled.");
        }
        SpringUpgradeExecutionPort transformer;
        if (localEngineeringEnabled) {
            transformer = new LocalSpringUpgradeExecutionPort(
                    Path.of(workspaceRoot),
                    Path.of(sourceJavaHome),
                    Path.of(targetJavaHome),
                    mavenExecutable,
                    hosts(allowedHosts),
                    allowFileRepositories,
                    false,
                    optionalPath(mavenDependencySeed),
                    json
            );
        } else {
            if (!rootlessRunnerAttested) {
                return new DisabledSpringUpgradeExecutionPort(
                        "The private Runner has no verified rootless isolation attestation.");
            }
            if (!networkPolicyAttested) {
                return new DisabledSpringUpgradeExecutionPort(
                        "The private Runner has no verified default-deny network policy and audited egress path.");
            }
            if (!transformerBrokerEnabled) {
                return new DisabledSpringUpgradeExecutionPort(
                        "A per-run rootless transformation broker is required; local execution is engineering-only and disabled.");
            }
            transformer = new EphemeralSpringTransformationExecutionPort(
                    Path.of(workspaceRoot),
                    URI.create(transformerBrokerBaseUrl),
                    Path.of(transformerBrokerSecretFile),
                    json,
                    clock
            );
        }
        if (!runtimeRunnerEnabled) return transformer;
        if (!rootlessRunnerAttested || !networkPolicyAttested) {
            return transformer;
        }
        return new IsolatedSpringRuntimeExecutionPort(
                transformer,
                Path.of(workspaceRoot),
                URI.create(runtimeRunnerBaseUrl),
                Path.of(runtimeRunnerSecretFile),
                json,
                clock
        );
    }

    @Bean
    SpringUpgradeIndependentValidationPort springUpgradeIndependentValidationPort(
            @Value("${elmos.worker.spring-upgrade.enabled:false}") boolean enabled,
            @Value("${elmos.worker.spring-upgrade.rootless-runner-attested:false}") boolean rootlessRunnerAttested,
            @Value("${elmos.worker.spring-upgrade.default-deny-network-attested:false}") boolean networkPolicyAttested,
            @Value("${elmos.worker.spring-upgrade.independent-verifier-enabled:false}") boolean verifierEnabled,
            @Value("${elmos.worker.spring-upgrade.local-engineering-enabled:false}") boolean localEngineeringEnabled,
            @Value("${elmos.worker.spring-upgrade.workspace-root:/tmp/elmos-private-runner}") String workspaceRoot,
            @Value("${elmos.worker.spring-upgrade.independent-verifier-base-url:http://java-engine-verifier:8082}") String verifierBaseUrl,
            @Value("${elmos.worker.spring-upgrade.independent-verifier-secret-file:/run/secrets/elmos_verifier_hmac}") String verifierSecretFile,
            @Value("${elmos.worker.spring-upgrade.independent-verifier-id:private-runner-verifier}") String verifierId,
            ObjectMapper json,
            Clock clock
    ) {
        if (!enabled || !verifierEnabled
                || (!localEngineeringEnabled && (!rootlessRunnerAttested || !networkPolicyAttested))) {
            return new DisabledSpringUpgradeIndependentValidationPort(
                    "An independently identified verifier in the approved rootless Runner is required.");
        }
        return new HttpSpringUpgradeIndependentValidator(
                Path.of(workspaceRoot),
                URI.create(verifierBaseUrl),
                Path.of(verifierSecretFile),
                verifierId,
                json,
                clock
        );
    }

    @Bean
    SpringUpgradeRunService springUpgradeRunService(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier,
            @Value("${elmos.worker.spring-upgrade.workspace-root:/tmp/elmos-private-runner}") String workspaceRoot,
            ObjectMapper json,
            Clock clock
    ) {
        return new SpringUpgradeRunService(transformer, verifier, Path.of(workspaceRoot), json, clock);
    }

    private static Set<String> hosts(String value) {
        return Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(host -> !host.isBlank())
                .map(host -> host.toLowerCase(Locale.ROOT))
                .collect(Collectors.toUnmodifiableSet());
    }

    private static Path optionalPath(String value) {
        return value == null || value.isBlank() ? null : Path.of(value);
    }
}
