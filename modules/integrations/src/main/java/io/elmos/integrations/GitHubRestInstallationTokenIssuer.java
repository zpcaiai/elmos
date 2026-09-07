package io.elmos.integrations;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.elmos.scm.GitHubInstallationTokenBroker;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.*;

public final class GitHubRestInstallationTokenIssuer implements GitHubInstallationTokenBroker.InstallationTokenIssuer {
    private record TokenRequest(@JsonProperty("repository_ids") List<Long> repositoryIds, Map<String, String> permissions) {}
    private record TokenResponse(String token, @JsonProperty("expires_at") Instant expiresAt, Map<String, String> permissions) {}
    private final RestClient client; private final GitHubAppJwt appJwt; private final java.time.Clock clock;

    public GitHubRestInstallationTokenIssuer(RestClient.Builder builder, String apiBaseUrl, GitHubAppJwt appJwt, java.time.Clock clock) {
        this.client = builder.baseUrl(apiBaseUrl).build(); this.appJwt = Objects.requireNonNull(appJwt); this.clock = Objects.requireNonNull(clock);
    }

    @Override public GitHubInstallationTokenBroker.TokenGrant issue(long installationExternalId, long repositoryExternalId,
                                                                    Set<GitHubInstallationTokenBroker.Permission> requested) {
        Map<String,String> permissions = new TreeMap<>();
        requested.forEach(permission -> permissions.put(permission.name(), permission.access().name().toLowerCase(Locale.ROOT)));
        TokenResponse response = client.post().uri("/app/installations/{installation_id}/access_tokens", installationExternalId)
                .contentType(MediaType.APPLICATION_JSON).accept(MediaType.valueOf("application/vnd.github+json"))
                .header("Authorization", "Bearer " + appJwt.create()).header("X-GitHub-Api-Version", "2022-11-28")
                .body(new TokenRequest(List.of(repositoryExternalId), permissions)).retrieve().body(TokenResponse.class);
        if (response == null || response.token() == null || response.expiresAt() == null) throw new IllegalStateException("GitHub returned an incomplete installation token");
        Set<GitHubInstallationTokenBroker.Permission> granted = new HashSet<>();
        response.permissions().forEach((name, access) -> granted.add(new GitHubInstallationTokenBroker.Permission(name,
                GitHubInstallationTokenBroker.Access.valueOf(access.toUpperCase(Locale.ROOT)))));
        return new GitHubInstallationTokenBroker.TokenGrant(response.token().toCharArray(), clock.instant(), response.expiresAt(), granted);
    }

    @Override public void revoke(char[] token) {
        String authorization = "Bearer " + new String(token);
        try {
            client.delete().uri("/installation/token").accept(MediaType.valueOf("application/vnd.github+json"))
                    .header("Authorization", authorization).header("X-GitHub-Api-Version", "2022-11-28").retrieve().toBodilessEntity();
        } finally { authorization = null; }
    }
}
