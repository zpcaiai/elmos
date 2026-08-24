package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.integrations.*;
import io.elmos.persistence.JdbcGitHubRepositoryAuthorization;
import io.elmos.persistence.JdbcGitHubInstallationStore;
import io.elmos.persistence.JdbcSnapshotStore;
import io.elmos.scm.GitHubInstallationLifecycleService;
import io.elmos.scm.GitHubInstallationTokenBroker;
import io.elmos.snapshot.DeterministicSnapshotArchiver;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
import io.elmos.snapshot.SnapshotPorts;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.client.RestClient;

import java.io.Reader;
import java.net.URI;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.*;

@Configuration
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
class GithubSnapshotConfiguration {
    @Bean GitHubAppJwt gitHubAppJwt(@Value("${elmos.github.app.id:}") String appId,
            @Value("${elmos.github.app.private-key-path:}") String keyPath, Clock clock, ObjectMapper mapper) {
        if (appId.isBlank() || keyPath.isBlank()) throw new IllegalStateException("GitHub App id and private key path are required");
        return new GitHubAppJwt(appId, GitHubPrivateKeyLoader.loadPkcs8(readOwnerOnlySecret(Path.of(keyPath))), clock, mapper);
    }

    @Bean GitHubInstallationTokenBroker.InstallationTokenIssuer installationTokenIssuer(RestClient.Builder builder,
            @Value("${elmos.github.api-base-url:https://api.github.com}") String apiBaseUrl,
            GitHubAppJwt appJwt, Clock clock) {
        URI uri = URI.create(apiBaseUrl);
        if (!"https".equals(uri.getScheme()) || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
            throw new SecurityException("GitHub API base URL must be credential-free HTTPS");
        return new GitHubRestInstallationTokenIssuer(builder, apiBaseUrl, appJwt, clock);
    }

    @Bean GitHubInstallationLifecycleService gitHubInstallationLifecycleService(
            JdbcGitHubInstallationStore store
    ) {
        return new GitHubInstallationLifecycleService(store);
    }

    @Bean JdbcGithubOnboardingStateStore githubOnboardingStateStore(
            JdbcClient jdbc,
            Clock clock
    ) {
        return new JdbcGithubOnboardingStateStore(jdbc, clock);
    }

    @Bean GitHubAppOnboardingClient gitHubAppOnboardingClient(
            RestClient.Builder builder,
            GitHubAppJwt appJwt,
            @Value("${elmos.github.api-base-url:https://api.github.com}") String apiBaseUrl,
            @Value("${elmos.github.web-base-url:https://github.com}") String githubBaseUrl,
            @Value("${elmos.github.api-version:2026-03-10}") String apiVersion,
            @Value("${elmos.github.app.client-id:}") String clientId,
            @Value("${elmos.github.app.client-secret-path:}") String clientSecretPath,
            @Value("${elmos.github.app.callback-url:}") String callbackUrl
    ) {
        if (clientSecretPath.isBlank()) {
            throw new IllegalStateException("GitHub App client secret path is required");
        }
        Path secretPath = Path.of(clientSecretPath);
        return new GitHubAppOnboardingClient(
                builder,
                apiBaseUrl,
                githubBaseUrl,
                apiVersion,
                clientId,
                callbackUrl,
                () -> readOwnerOnlySecret(secretPath),
                appJwt
        );
    }

    @Bean GithubInstallationOnboardingService githubInstallationOnboardingService(
            GitHubAppOnboardingClient github,
            GitHubInstallationLifecycleService lifecycle,
            JdbcGithubOnboardingStateStore states,
            ObjectMapper mapper,
            Clock clock,
            @Value("${elmos.github.app.slug:}") String appSlug,
            @Value("${elmos.github.app.client-id:}") String clientId,
            @Value("${elmos.github.app.callback-url:}") String callbackUrl,
            @Value("${elmos.github.app.success-url:}") String successUrl,
            @Value("${elmos.github.web-base-url:https://github.com}") String githubBaseUrl,
            @Value("${elmos.github.app.onboarding-state-secret-path:}") String stateSecretPath
    ) {
        if (stateSecretPath.isBlank()) {
            throw new IllegalStateException("GitHub App onboarding state secret path is required");
        }
        byte[] stateSecret = readOwnerOnlyBytes(Path.of(stateSecretPath), 4096);
        try {
            return new GithubInstallationOnboardingService(
                    appSlug,
                    clientId,
                    callbackUrl,
                    successUrl,
                    githubBaseUrl,
                    stateSecret,
                    mapper,
                    states,
                    github,
                    lifecycle,
                    clock
            );
        } finally {
            Arrays.fill(stateSecret, (byte) 0);
        }
    }

    @Bean GitHubInstallationTokenBroker installationTokenBroker(JdbcGitHubRepositoryAuthorization authorization,
            GitHubInstallationTokenBroker.InstallationTokenIssuer issuer, JdbcClient jdbc, Clock clock) {
        GitHubInstallationTokenBroker.CredentialLeaseAuditPort audit = metadata -> jdbc.sql("""
                insert into audit_events(audit_id,actor_type,actor_id,action,resource_type,resource_id,
                    after_hash,occurred_at,request_id,policy_decision,result)
                values(:id,'GITHUB_APP',:actor,'INSTALLATION_TOKEN_ISSUED','SCM_REPOSITORY',:resource,
                    :hash,:occurred,:request,'ALLOW','SUCCESS')
                """).param("id", "audit-" + UUID.randomUUID()).param("actor", Long.toString(metadata.installationExternalId()))
                .param("resource", metadata.repositoryId()).param("hash", leaseDigest(metadata)).param("occurred", metadata.issuedAt())
                .param("request", "credential-lease:" + metadata.repositoryId()).update();
        return new GitHubInstallationTokenBroker(authorization, issuer, audit, clock);
    }

    @Bean JGitSnapshotSourceAdapter snapshotSourceAdapter(JdbcClient jdbc,
            @Value("${elmos.snapshot.staging-root:}") String stagingRoot) {
        if (stagingRoot.isBlank()) throw new IllegalStateException("snapshot staging root is required");
        JGitSnapshotSourceAdapter.RepositoryLocationResolver locations = repositoryId -> URI.create(jdbc.sql("""
                select sr.clone_url from scm_repositories sr
                join github_app_installations gi on gi.installation_id=sr.installation_id
                where sr.repository_id=:id and sr.authorization_status='AUTHORIZED' and sr.archived=false
                  and sr.disabled=false and gi.status='ACTIVE'
                """).param("id", repositoryId).query(String.class).single());
        return new JGitSnapshotSourceAdapter(locations, Path.of(stagingRoot));
    }

    @Bean SnapshotCaptureService snapshotCaptureService(GitHubInstallationTokenBroker broker,
            JGitSnapshotSourceAdapter source, SnapshotPorts.ArtifactStore artifacts, JdbcSnapshotStore snapshots, Clock clock) {
        SnapshotPorts.RepositoryCredentialBroker credentials =
                (organizationId, repositoryId, repositoryExternalId, installationExternalId) ->
                broker.issue(organizationId, repositoryId, repositoryExternalId, installationExternalId,
                        GitHubInstallationTokenBroker.Operation.CAPTURE_SNAPSHOT);
        return new SnapshotCaptureService(credentials, source, source, new DeterministicSnapshotArchiver(), artifacts, snapshots, clock);
    }

    @Bean SnapshotMaterializationService snapshotMaterializationService(
            SnapshotPorts.ArtifactReader artifacts,
            ObjectMapper mapper,
            @Value("${elmos.snapshot.materialized-root:}") String materializedRoot
    ) {
        if (materializedRoot.isBlank()) {
            throw new IllegalStateException("snapshot materialized root is required");
        }
        return new SnapshotMaterializationService(
                Path.of(materializedRoot), artifacts, mapper);
    }

    private static char[] readOwnerOnlySecret(Path rawPath) {
        Path path = rawPath.toAbsolutePath().normalize();
        try {
            if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > 65536)
                throw new SecurityException("GitHub App private key file is invalid");
            try {
                Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
                if (permissions.stream().anyMatch(value -> value.name().startsWith("GROUP_") || value.name().startsWith("OTHERS_")))
                    throw new SecurityException("GitHub App private key file must be owner-only");
            } catch (UnsupportedOperationException ignored) { }
            try (Reader reader = Files.newBufferedReader(path)) {
                WipingChars output = new WipingChars(); char[] buffer = new char[4096]; int count;
                try { while ((count = reader.read(buffer)) >= 0) output.write(buffer, 0, count); return output.toCharArray(); }
                finally { Arrays.fill(buffer, '\0'); output.wipe(); }
            }
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("GitHub App private key is unavailable", error); }
    }

    private static byte[] readOwnerOnlyBytes(Path rawPath, long maximumBytes) {
        Path path = rawPath.toAbsolutePath().normalize();
        try {
            if (Files.isSymbolicLink(path)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || Files.size(path) < 32
                    || Files.size(path) > maximumBytes) {
                throw new SecurityException("GitHub App secret file is invalid");
            }
            try {
                Set<PosixFilePermission> permissions =
                        Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
                if (permissions.stream().anyMatch(value ->
                        value.name().startsWith("GROUP_")
                                || value.name().startsWith("OTHERS_"))) {
                    throw new SecurityException("GitHub App secret file must be owner-only");
                }
            } catch (UnsupportedOperationException ignored) { }
            return Files.readAllBytes(path);
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GitHub App secret is unavailable", error);
        }
    }

    private static String leaseDigest(GitHubInstallationTokenBroker.LeaseMetadata metadata) {
        try {
            String value = metadata.organizationId() + ":" + metadata.repositoryExternalId()
                    + ":" + metadata.installationExternalId() + ":" +
                    metadata.operation() + ":" + metadata.expiresAt() + ":" + new TreeSet<>(metadata.permissions().stream()
                    .map(permission -> permission.name() + "=" + permission.access()).toList());
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        } catch (Exception error) { throw new IllegalStateException(error); }
    }

    private static final class WipingChars extends java.io.CharArrayWriter {
        void wipe() { Arrays.fill(buf, '\0'); reset(); }
    }
}
