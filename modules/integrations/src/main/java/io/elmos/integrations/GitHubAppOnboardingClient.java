package io.elmos.integrations;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

import java.time.Instant;
import java.util.*;

/**
 * Performs the server-side portion of GitHub App installation onboarding.
 * User and installation access tokens are never returned to callers or persisted.
 */
public final class GitHubAppOnboardingClient {
    public interface ClientSecretProvider {
        char[] load();
    }

    public record Installation(
            long id,
            long accountId,
            String accountLogin,
            String targetType,
            String repositorySelection,
            Map<String, String> permissions,
            Instant installedAt,
            boolean suspended
    ) {
        public Installation {
            permissions = Map.copyOf(permissions);
        }
    }

    public record Repository(
            long id,
            String owner,
            String name,
            String fullName,
            String cloneUrl,
            String htmlUrl,
            String defaultBranch,
            String visibility,
            boolean archived,
            boolean disabled,
            boolean fork,
            Long parentId
    ) {}

    public record Discovery(Installation installation, Set<Repository> repositories) {
        public Discovery {
            repositories = Set.copyOf(repositories);
        }
    }

    private record OAuthToken(
            @JsonProperty("access_token") String accessToken,
            String error,
            @JsonProperty("error_description") String errorDescription
    ) {}

    private record UserInstallation(long id) {}
    private record UserInstallations(List<UserInstallation> installations) {}
    private record Account(long id, String login) {}
    private record InstallationResponse(
            long id,
            Account account,
            @JsonProperty("target_type") String targetType,
            @JsonProperty("repository_selection") String repositorySelection,
            Map<String, String> permissions,
            @JsonProperty("created_at") Instant createdAt,
            @JsonProperty("suspended_at") Instant suspendedAt
    ) {}
    private record InstallationTokenResponse(
            String token,
            @JsonProperty("expires_at") Instant expiresAt,
            Map<String, String> permissions
    ) {}
    private record Owner(String login) {}
    private record Parent(long id) {}
    private record RepositoryResponse(
            long id,
            Owner owner,
            String name,
            @JsonProperty("full_name") String fullName,
            @JsonProperty("clone_url") String cloneUrl,
            @JsonProperty("html_url") String htmlUrl,
            @JsonProperty("default_branch") String defaultBranch,
            String visibility,
            boolean archived,
            boolean disabled,
            boolean fork,
            Parent parent
    ) {}
    private record RepositoryPage(
            @JsonProperty("total_count") int totalCount,
            List<RepositoryResponse> repositories
    ) {}

    private static final MediaType GITHUB_JSON = MediaType.valueOf("application/vnd.github+json");
    private static final int PAGE_SIZE = 100;
    private static final int MAX_PAGES = 10;

    private final RestClient api;
    private final RestClient github;
    private final GitHubAppJwt appJwt;
    private final ClientSecretProvider clientSecretProvider;
    private final String clientId;
    private final String callbackUrl;
    private final String apiVersion;

    public GitHubAppOnboardingClient(
            RestClient.Builder builder,
            String apiBaseUrl,
            String githubBaseUrl,
            String apiVersion,
            String clientId,
            String callbackUrl,
            ClientSecretProvider clientSecretProvider,
            GitHubAppJwt appJwt
    ) {
        this.api = builder.clone().baseUrl(requireHttps(apiBaseUrl)).build();
        this.github = builder.clone().baseUrl(requireHttps(githubBaseUrl)).build();
        this.apiVersion = require(apiVersion, "GitHub API version");
        this.clientId = require(clientId, "GitHub App client id");
        this.callbackUrl = requireHttps(callbackUrl);
        this.clientSecretProvider = Objects.requireNonNull(clientSecretProvider);
        this.appJwt = Objects.requireNonNull(appJwt);
    }

    public Discovery discoverAuthorizedInstallation(
            String authorizationCode,
            String codeVerifier,
            long candidateInstallationId
    ) {
        char[] clientSecret = clientSecretProvider.load();
        char[] userToken = null;
        try {
            OAuthToken token = exchangeCode(authorizationCode, codeVerifier, clientSecret);
            if (token == null || token.accessToken() == null || token.accessToken().isBlank()
                    || token.error() != null) {
                throw new SecurityException("GitHub user authorization failed");
            }
            userToken = token.accessToken().toCharArray();
            requireUserCanAccessInstallation(userToken, candidateInstallationId);
            Installation installation = loadInstallation(candidateInstallationId);
            if (installation.suspended()) {
                throw new SecurityException("GitHub App installation is suspended");
            }
            return new Discovery(installation, loadRepositories(candidateInstallationId));
        } finally {
            Arrays.fill(clientSecret, '\0');
            if (userToken != null) Arrays.fill(userToken, '\0');
        }
    }

    private OAuthToken exchangeCode(String code, String verifier, char[] clientSecret) {
        LinkedMultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("client_id", clientId);
        form.add("client_secret", new String(clientSecret));
        form.add("code", require(code, "GitHub authorization code"));
        form.add("redirect_uri", callbackUrl);
        form.add("code_verifier", require(verifier, "PKCE verifier"));
        return github.post().uri("/login/oauth/access_token")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(GITHUB_JSON)
                .body(form)
                .retrieve()
                .body(OAuthToken.class);
    }

    private void requireUserCanAccessInstallation(char[] userToken, long installationId) {
        String authorization = "Bearer " + new String(userToken);
        try {
            for (int page = 1; page <= MAX_PAGES; page++) {
                int requestedPage = page;
                UserInstallations response = api.get()
                        .uri(uri -> uri.path("/user/installations")
                                .queryParam("per_page", PAGE_SIZE)
                                .queryParam("page", requestedPage)
                                .build())
                        .accept(GITHUB_JSON)
                        .header("Authorization", authorization)
                        .header("X-GitHub-Api-Version", apiVersion)
                        .retrieve().body(UserInstallations.class);
                List<UserInstallation> values =
                        response == null || response.installations() == null ? List.of() : response.installations();
                if (values.stream().anyMatch(value -> value.id() == installationId)) return;
                if (values.size() < PAGE_SIZE) break;
            }
            throw new SecurityException("GitHub installation is not accessible to the authorizing user");
        } finally {
            authorization = null;
        }
    }

    private Installation loadInstallation(long installationId) {
        InstallationResponse response = api.get()
                .uri("/app/installations/{installation_id}", installationId)
                .accept(GITHUB_JSON)
                .header("Authorization", "Bearer " + appJwt.create())
                .header("X-GitHub-Api-Version", apiVersion)
                .retrieve().body(InstallationResponse.class);
        if (response == null || response.id() != installationId || response.account() == null
                || response.account().id() <= 0 || response.account().login() == null
                || response.createdAt() == null || response.permissions() == null) {
            throw new SecurityException("GitHub returned incomplete installation identity");
        }
        return new Installation(response.id(), response.account().id(), response.account().login(),
                response.targetType(), response.repositorySelection(), response.permissions(),
                response.createdAt(), response.suspendedAt() != null);
    }

    private Set<Repository> loadRepositories(long installationId) {
        char[] installationToken = issueRepositoryDiscoveryToken(installationId);
        String authorization = "Bearer " + new String(installationToken);
        try {
            Set<Repository> output = new LinkedHashSet<>();
            int declaredTotal = -1;
            for (int page = 1; page <= MAX_PAGES; page++) {
                int requestedPage = page;
                RepositoryPage response = api.get()
                        .uri(uri -> uri.path("/installation/repositories")
                                .queryParam("per_page", PAGE_SIZE)
                                .queryParam("page", requestedPage)
                                .build())
                        .accept(GITHUB_JSON)
                        .header("Authorization", authorization)
                        .header("X-GitHub-Api-Version", apiVersion)
                        .retrieve().body(RepositoryPage.class);
                if (response == null || response.repositories() == null) {
                    throw new SecurityException("GitHub returned an incomplete repository page");
                }
                declaredTotal = response.totalCount();
                for (RepositoryResponse repository : response.repositories()) {
                    output.add(normalize(repository));
                }
                if (response.repositories().size() < PAGE_SIZE) break;
            }
            if (declaredTotal < 0 || output.size() != declaredTotal) {
                throw new SecurityException("GitHub repository discovery exceeded the bounded complete result");
            }
            return output;
        } finally {
            try {
                api.delete().uri("/installation/token")
                        .accept(GITHUB_JSON)
                        .header("Authorization", authorization)
                        .header("X-GitHub-Api-Version", apiVersion)
                        .retrieve().toBodilessEntity();
            } finally {
                authorization = null;
                Arrays.fill(installationToken, '\0');
            }
        }
    }

    private char[] issueRepositoryDiscoveryToken(long installationId) {
        InstallationTokenResponse response = api.post()
                .uri("/app/installations/{installation_id}/access_tokens", installationId)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(GITHUB_JSON)
                .header("Authorization", "Bearer " + appJwt.create())
                .header("X-GitHub-Api-Version", apiVersion)
                .body(Map.of("permissions", Map.of("contents", "read", "metadata", "read")))
                .retrieve().body(InstallationTokenResponse.class);
        if (response == null || response.token() == null || response.token().isBlank()
                || response.expiresAt() == null) {
            throw new SecurityException("GitHub returned an incomplete installation token");
        }
        return response.token().toCharArray();
    }

    private static Repository normalize(RepositoryResponse value) {
        if (value == null || value.id() <= 0 || value.owner() == null
                || blank(value.owner().login()) || blank(value.name()) || blank(value.fullName())
                || !value.fullName().equals(value.owner().login() + "/" + value.name())
                || blank(value.cloneUrl()) || blank(value.htmlUrl()) || blank(value.defaultBranch())
                || blank(value.visibility())) {
            throw new SecurityException("GitHub repository identity is incomplete");
        }
        if (!value.cloneUrl().startsWith("https://github.com/")
                || value.cloneUrl().contains("@") || !value.cloneUrl().endsWith(".git")) {
            throw new SecurityException("GitHub repository clone URL is not approved credential-free HTTPS");
        }
        return new Repository(value.id(), value.owner().login(), value.name(), value.fullName(),
                value.cloneUrl(), value.htmlUrl(), value.defaultBranch(), value.visibility(),
                value.archived(), value.disabled(), value.fork(),
                value.parent() == null ? null : value.parent().id());
    }

    private static String requireHttps(String raw) {
        String value = require(raw, "HTTPS URL");
        java.net.URI uri = java.net.URI.create(value);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null) {
            throw new SecurityException("GitHub endpoint must be credential-free HTTPS");
        }
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private static String require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
        return value;
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
