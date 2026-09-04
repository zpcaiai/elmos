package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.security.FileNonceStore;
import io.elmos.security.SpringHmacProtocol;
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

import javax.sql.DataSource;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
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
    WorkspaceInfrastructurePorts.SnapshotArtifactResolver workspaceSnapshotArtifactResolver(
            DataSource dataSource
    ) {
        return new JdbcWorkspaceSnapshotArtifactResolver(dataSource);
    }

    @Bean @ConditionalOnProperty(name = "elmos.workspace.docker.enabled", havingValue = "true")
    WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer snapshotMaterializer(
            DockerClient docker,
            WorkspaceInfrastructurePorts.SnapshotArtifactResolver snapshots,
            WorkspaceInfrastructurePorts.SnapshotArtifactReader artifacts,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            @Value("${elmos.workspace.snapshot-helper-image-digest:}") String digest) {
        return new DockerSnapshotVolumeMaterializer(
                docker, snapshots, artifacts, digest, images);
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
            @Value("${elmos.workspace.spring-runtime.replay-root:}") String replayRoot,
            @Value("${elmos.workspace.spring-runtime.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceArtifactRoot.isBlank() || hostArtifactRoot.isBlank()
                || secretFile.isBlank() || replayRoot.isBlank()) {
            throw new IllegalStateException(
                    "Spring runtime roots, HMAC secret file and replay root are required");
        }
        return new RootlessSpringRuntimeService(
                docker,
                images,
                imageDigest,
                Path.of(serviceArtifactRoot),
                Path.of(hostArtifactRoot),
                new SpringRuntimeAuthentication(
                        readSecret(Path.of(secretFile), "Spring runtime"),
                        SpringHmacProtocol.Role.RUNTIME,
                        clock,
                        authWindowSeconds,
                        new FileNonceStore(Path.of(replayRoot), clock)),
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
            @Value("${elmos.workspace.spring-verifier.replay-root:}") String replayRoot,
            @Value("${elmos.workspace.spring-verifier.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceInputRoot.isBlank()
                || hostInputRoot.isBlank()
                || serviceEvidenceRoot.isBlank()
                || hostEvidenceRoot.isBlank()
                || hmacSecretFile.isBlank()
                || replayRoot.isBlank()) {
            throw new IllegalStateException(
                    "Ephemeral Spring verifier roots, HMAC secret and replay root are required");
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
                        readSecret(Path.of(hmacSecretFile), "Spring verifier"),
                        SpringHmacProtocol.Role.VERIFIER,
                        clock,
                        authWindowSeconds,
                        new FileNonceStore(Path.of(replayRoot), clock)
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
            @Value("${elmos.workspace.spring-transformer.replay-root:}") String replayRoot,
            @Value("${elmos.workspace.spring-transformer.auth-window-seconds:90}") long authWindowSeconds
    ) {
        if (serviceRunRoot.isBlank() || hostRunRoot.isBlank()
                || hmacSecretFile.isBlank() || replayRoot.isBlank()) {
            throw new IllegalStateException(
                    "Ephemeral Spring transformer roots, HMAC secret and replay root are required");
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
                        readSecret(Path.of(hmacSecretFile), "Spring transformer"),
                        SpringHmacProtocol.Role.TRANSFORMER,
                        clock,
                        authWindowSeconds,
                        new FileNonceStore(Path.of(replayRoot), clock)
                ),
                json,
                clock
        );
    }

    private static byte[] readSecret(Path path, String label) {
        return SpringHmacProtocol.readSecret(path, label);
    }
}
