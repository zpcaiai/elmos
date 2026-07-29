package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.enterprise.AnthropicModelHealthProbe;
import io.elmos.enterprise.DeepSeekModelHealthProbe;
import io.elmos.enterprise.DoubaoModelHealthProbe;
import io.elmos.enterprise.EnvModelCredentialSource;
import io.elmos.enterprise.ModelHealthProbe;
import io.elmos.enterprise.OpenAiModelHealthProbe;
import io.elmos.enterprise.QwenModelHealthProbe;
import io.elmos.enterprise.XaiModelHealthProbe;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
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
            @Value("${elmos.worker.spring-upgrade.java-homes:}") String additionalJavaHomes,
            @Value("${elmos.worker.spring-upgrade.experimental-routes-enabled:false}") boolean experimentalRoutesEnabled,
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
            SpringUpgradeCodingAgentPort codingAgentPort,
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
                    javaHomes(sourceJavaHome, targetJavaHome, additionalJavaHomes),
                    mavenExecutable,
                    hosts(allowedHosts),
                    allowFileRepositories,
                    false,
                    optionalPath(mavenDependencySeed),
                    experimentalRoutesEnabled,
                    json,
                    codingAgentPort
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
    SpringUpgradeCodingAgentPort springUpgradeCodingAgentPort(
            @Value("${elmos.worker.spring-upgrade.coding-agent-enabled:false}") boolean enabled,
            @Value("${elmos.worker.spring-upgrade.coding-agent-region:global}") String region
    ) {
        if (!enabled) {
            return new DisabledSpringUpgradeCodingAgentPort(
                    "Spring upgrade long-tail Coding Agent model selection is disabled until explicitly enabled; "
                            + "see docs/adr/ADR-0059-coding-agent-model-catalog.md.");
        }
        List<String> candidateModelIds = List.of(
                "gpt-5.6-sol", "claude-opus-5", "grok-4.5", "qwen3.8-max-preview", "deepseek-v4-pro", "doubao-seed-code");
        // Every candidate above now has a real, vendor-specific probe (see ADR-0059). Only
        // DeepSeekModelHealthProbe has actually been exercised against live traffic in this
        // project; the other five are code-complete but unverified until an operator supplies
        // a real credential for that vendor and runs its @EnabledIfEnvironmentVariable test.
        Map<String, ModelHealthProbe> probesByModelId = Map.of(
                "gpt-5.6-sol", new OpenAiModelHealthProbe(),
                "claude-opus-5", new AnthropicModelHealthProbe(),
                "grok-4.5", new XaiModelHealthProbe(),
                "qwen3.8-max-preview", new QwenModelHealthProbe(),
                "doubao-seed-code", new DoubaoModelHealthProbe(),
                "deepseek-v4-pro", new DeepSeekModelHealthProbe(),
                "deepseek-v4-flash", new DeepSeekModelHealthProbe());
        return new EnterpriseGovernanceSpringUpgradeCodingAgentPort(
                candidateModelIds, new EnvModelCredentialSource(), probesByModelId, region);
    }

    @Bean
    SpringUpgradeRunService springUpgradeRunService(
            SpringUpgradeExecutionPort transformer,
            SpringUpgradeIndependentValidationPort verifier,
            @Value("${elmos.worker.spring-upgrade.workspace-root:/tmp/elmos-private-runner}") String workspaceRoot,
            @Value("${elmos.worker.spring-upgrade.queue.global-capacity:2}") int globalCapacity,
            @Value("${elmos.worker.spring-upgrade.queue.tenant-capacity:1}") int tenantCapacity,
            @Value("${elmos.worker.spring-upgrade.queue.ttl-seconds:3600}") long queueTtlSeconds,
            @Value("${elmos.worker.spring-upgrade.queue.lease-seconds:120}") long leaseTtlSeconds,
            ObjectMapper json,
            Clock clock
    ) {
        return new SpringUpgradeRunService(
                transformer, verifier, Path.of(workspaceRoot), json, clock,
                globalCapacity, tenantCapacity, Duration.ofSeconds(queueTtlSeconds),
                Duration.ofSeconds(leaseTtlSeconds));
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

    /**
     * Build the JDK registry the multi-version catalog needs.
     *
     * <p>The legacy {@code source-java-home} and {@code target-java-home}
     * properties stay authoritative for Java 17 and 21 so existing deployments
     * keep working unchanged. {@code java-homes} adds the other releases a
     * legacy estate needs, for example {@code 8=/opt/java/openjdk-8,11=/opt/java/openjdk-11}.
     */
    static Map<String, Path> javaHomes(String sourceJavaHome, String targetJavaHome, String additional) {
        Map<String, Path> homes = new LinkedHashMap<>();
        homes.put("17", Path.of(sourceJavaHome));
        homes.put(SpringRouteCatalog.TARGET_JAVA, Path.of(targetJavaHome));
        if (additional == null || additional.isBlank()) return Map.copyOf(homes);
        for (String entry : additional.split(",")) {
            String candidate = entry.trim();
            if (candidate.isEmpty()) continue;
            int separator = candidate.indexOf('=');
            if (separator <= 0 || separator == candidate.length() - 1) {
                throw new IllegalArgumentException(
                        "elmos.worker.spring-upgrade.java-homes entries must be <release>=<absolute-path>");
            }
            String release = candidate.substring(0, separator).trim();
            Path home = Path.of(candidate.substring(separator + 1).trim());
            if (!home.isAbsolute()) {
                throw new IllegalArgumentException("JAVA_HOME for release " + release + " must be absolute");
            }
            homes.put(release, home);
        }
        return Map.copyOf(homes);
    }
}
