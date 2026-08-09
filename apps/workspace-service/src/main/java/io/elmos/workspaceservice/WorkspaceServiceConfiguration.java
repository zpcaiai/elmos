package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.core.DefaultDockerClientConfig;
import com.github.dockerjava.core.DockerClientImpl;
import com.github.dockerjava.httpclient5.ApacheDockerHttpClient;
import io.elmos.persistence.JdbcSecretLeaseStore;
import io.elmos.persistence.JdbcWorkspaceLifecycleStore;
import io.elmos.secret.SecretInjectionService;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceProvisioningPort;
import io.elmos.workspace.WorkspaceSecurityPolicy;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.io.IOException;
import java.time.Clock;

@Configuration
class WorkspaceServiceConfiguration {
    @Bean Clock workspaceClock() { return Clock.systemUTC(); }
    @Bean WorkspaceSecurityPolicy workspaceSecurityPolicy() { return new WorkspaceSecurityPolicy(); }
    @Bean WorkspaceOwnership workspaceOwnership(JdbcClient jdbc) { return new JdbcWorkspaceOwnership(jdbc); }

    @Bean(destroyMethod = "close") @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    DockerClient dockerClient() {
        var config = DefaultDockerClientConfig.createDefaultConfigBuilder().build();
        var http = new ApacheDockerHttpClient.Builder().dockerHost(config.getDockerHost()).sslConfig(config.getSSLConfig()).build();
        return DockerClientImpl.getInstance(config, http);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceProvisioningPort dockerWorkspaceProvisioner(DockerClient docker, WorkspaceSecurityPolicy policy,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer snapshots,
            WorkspaceInfrastructurePorts.CommandOutputSanitizer sanitizer,
            WorkspaceInfrastructurePorts.CommandArtifactStore artifacts,
            WorkspaceInfrastructurePorts.NetworkPolicyEnforcer networkPolicies,
            WorkspaceInfrastructurePorts.WorkspaceLifecycleStore lifecycle,
            WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer secrets, Clock clock) {
        return new DockerWorkspaceProvisioner(docker, policy, images, snapshots, sanitizer, artifacts, networkPolicies, lifecycle, secrets, clock);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceInfrastructurePorts.WorkspaceLifecycleStore workspaceLifecycle(JdbcClient jdbc, ObjectMapper json, Clock clock) {
        return new JdbcWorkspaceLifecycleStore(jdbc, json, clock);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceSecretRegistry workspaceSecretRegistry() { return new WorkspaceSecretRegistry(); }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceInfrastructurePorts.CommandArtifactStore commandArtifacts(JdbcClient jdbc,
            @Value("${elmos.workspace.command-artifact-root:}") String root) {
        if (root.isBlank()) throw new IllegalStateException("command artifact root is required");
        return new FileCommandArtifactStore(Path.of(root), jdbc);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer snapshotMaterializer(DockerClient docker, JdbcClient jdbc,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            @Value("${elmos.workspace.snapshot-artifact-root:}") String root,
            @Value("${elmos.workspace.snapshot-helper-image-digest:}") String digest) {
        if (root.isBlank()) throw new IllegalStateException("snapshot artifact root is required");
        return new DockerSnapshotVolumeMaterializer(docker, jdbc, Path.of(root), digest, images);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceInfrastructurePorts.NetworkPolicyEnforcer networkPolicyEnforcer(DockerClient docker, JdbcClient jdbc,
            ObjectMapper json, WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            @Value("${elmos.workspace.egress-proxy-image-digest:}") String digest) {
        return new DockerNetworkPolicyEnforcer(docker, jdbc, json, digest, images);
    }

    @Bean @ConditionalOnProperty(name = {"elmos.workspace.docker.enabled", "elmos.workspace.secrets.enabled"}, havingValue = "true")
    SecretInjectionService secretInjectionService(DockerClient docker, WorkspaceSecretRegistry registry, JdbcClient jdbc, Clock clock,
            @Value("${elmos.workspace.provider-secret-root:}") String root) {
        if (root.isBlank()) throw new IllegalStateException("provider secret root is required");
        return new SecretInjectionService(new DirectorySecretProvider(Path.of(root), clock),
                new DockerTmpfsSecretMaterializer(docker, registry), new JdbcSecretLeaseStore(jdbc), clock);
    }

    @Bean @ConditionalOnProperty(name = {"elmos.workspace.docker.enabled", "elmos.workspace.secrets.enabled"}, havingValue = "true")
    WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer workspaceSecretFinalizer(JdbcClient jdbc, SecretInjectionService secrets,
            WorkspaceSecretRegistry registry) { return new JdbcWorkspaceSecretFinalizer(jdbc, secrets, registry); }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.secrets.enabled", havingValue = "false", matchIfMissing = true)
    WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer disabledSecretFinalizer() { return workspaceId -> {}; }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "false", matchIfMissing = true)
    WorkspaceProvisioningPort disabledWorkspaceProvisioner() { return new DisabledWorkspaceProvisioner(); }

    @Bean
    @ConditionalOnProperty(name = {
            "elmos.workspace.docker.enabled",
            "elmos.workspace.spring-runtime.enabled"
    }, havingValue = "true")
    RootlessSpringRuntimeService rootlessSpringRuntimeService(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            ObjectMapper json,
            Clock clock,
            @Value("${elmos.workspace.spring-runtime.image-digest:}") String imageDigest,
            @Value("${elmos.workspace.spring-runtime.service-artifact-root:}") String serviceArtifactRoot,
            @Value("${elmos.workspace.spring-runtime.host-artifact-root:}") String hostArtifactRoot,
            @Value("${elmos.workspace.spring-runtime.hmac-secret-file:}") String secretFile,
            @Value("${elmos.workspace.spring-runtime.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceArtifactRoot.isBlank() || hostArtifactRoot.isBlank() || secretFile.isBlank()) {
            throw new IllegalStateException("Spring runtime roots and HMAC secret file are required");
        }
        return new RootlessSpringRuntimeService(
                docker,
                images,
                imageDigest,
                Path.of(serviceArtifactRoot),
                Path.of(hostArtifactRoot),
                new SpringRuntimeAuthentication(readSecret(Path.of(secretFile)), clock, authWindowSeconds),
                json
        );
    }

    @Bean
    @ConditionalOnProperty(name = {
            "elmos.workspace.docker.enabled",
            "elmos.workspace.spring-verifier.enabled"
    }, havingValue = "true")
    EphemeralSpringVerifierBroker ephemeralSpringVerifierBroker(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            ObjectMapper json,
            Clock clock,
            @Value("${elmos.workspace.spring-verifier.image-digest:}") String imageDigest,
            @Value("${elmos.workspace.spring-verifier.id:}") String verifierId,
            @Value("${elmos.workspace.spring-verifier.internal-network-name:}") String networkName,
            @Value("${elmos.workspace.spring-verifier.egress-proxy-url:}") String egressProxyUrl,
            @Value("${elmos.workspace.spring-verifier.service-input-root:}") String serviceInputRoot,
            @Value("${elmos.workspace.spring-verifier.host-input-root:}") String hostInputRoot,
            @Value("${elmos.workspace.spring-verifier.service-evidence-root:}") String serviceEvidenceRoot,
            @Value("${elmos.workspace.spring-verifier.host-evidence-root:}") String hostEvidenceRoot,
            @Value("${elmos.workspace.spring-verifier.hmac-secret-file:}") String hmacSecretFile,
            @Value("${elmos.workspace.spring-verifier.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceInputRoot.isBlank()
                || hostInputRoot.isBlank()
                || serviceEvidenceRoot.isBlank()
                || hostEvidenceRoot.isBlank()
                || hmacSecretFile.isBlank()) {
            throw new IllegalStateException("Ephemeral Spring verifier roots and HMAC secret are required");
        }
        return new EphemeralSpringVerifierBroker(
                docker,
                images,
                imageDigest,
                verifierId,
                networkName,
                egressProxyUrl,
                Path.of(serviceInputRoot),
                Path.of(hostInputRoot),
                Path.of(serviceEvidenceRoot),
                Path.of(hostEvidenceRoot),
                new SpringRuntimeAuthentication(
                        readSecret(Path.of(hmacSecretFile)),
                        clock,
                        authWindowSeconds
                ),
                json,
                clock
        );
    }

    @Bean
    @ConditionalOnProperty(name = {
            "elmos.workspace.docker.enabled",
            "elmos.workspace.spring-transformer.enabled"
    }, havingValue = "true")
    EphemeralSpringTransformerBroker ephemeralSpringTransformerBroker(
            DockerClient docker,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            ObjectMapper json,
            Clock clock,
            @Value("${elmos.workspace.spring-transformer.image-digest:}") String imageDigest,
            @Value("${elmos.workspace.spring-transformer.internal-network-name:}") String networkName,
            @Value("${elmos.workspace.spring-transformer.egress-proxy-url:}") String egressProxyUrl,
            @Value("${elmos.workspace.spring-transformer.allowed-git-hosts:}") String allowedGitHosts,
            @Value("${elmos.workspace.spring-transformer.service-run-root:}") String serviceRunRoot,
            @Value("${elmos.workspace.spring-transformer.host-run-root:}") String hostRunRoot,
            @Value("${elmos.workspace.spring-transformer.hmac-secret-file:}") String hmacSecretFile,
            @Value("${elmos.workspace.spring-transformer.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceRunRoot.isBlank() || hostRunRoot.isBlank() || hmacSecretFile.isBlank()) {
            throw new IllegalStateException("Ephemeral Spring transformer roots and HMAC secret are required");
        }
        return new EphemeralSpringTransformerBroker(
                docker,
                images,
                imageDigest,
                networkName,
                egressProxyUrl,
                allowedGitHosts,
                Path.of(serviceRunRoot),
                Path.of(hostRunRoot),
                new SpringRuntimeAuthentication(
                        readSecret(Path.of(hmacSecretFile)),
                        clock,
                        authWindowSeconds
                ),
                json,
                clock
        );
    }

    private static byte[] readSecret(Path path) {
        try {
            if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
                throw new IllegalStateException("Spring runtime HMAC secret file is unavailable");
            }
            byte[] raw = Files.readAllBytes(path);
            if (raw.length > 4096) throw new IllegalStateException("Spring runtime HMAC secret file is too large");
            byte[] value = new String(raw, StandardCharsets.UTF_8).trim().getBytes(StandardCharsets.UTF_8);
            if (value.length < 32) throw new IllegalStateException("Spring runtime HMAC secret must contain at least 32 bytes");
            return value;
        } catch (IOException error) {
            throw new IllegalStateException("Spring runtime HMAC secret file could not be read", error);
        }
    }
}
