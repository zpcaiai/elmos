package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.core.DefaultDockerClientConfig;
import com.github.dockerjava.core.DockerClientImpl;
import com.github.dockerjava.httpclient5.ApacheDockerHttpClient;
import io.elmos.persistence.JdbcApprovedImageRegistry;
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
import java.time.Clock;

@Configuration
class WorkspaceServiceConfiguration {
    @Bean Clock workspaceClock() { return Clock.systemUTC(); }
    @Bean WorkspaceSecurityPolicy workspaceSecurityPolicy() { return new WorkspaceSecurityPolicy(); }

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
    WorkspaceInfrastructurePorts.ApprovedImageRegistry approvedImages(JdbcClient jdbc) { return new JdbcApprovedImageRegistry(jdbc); }

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
}
