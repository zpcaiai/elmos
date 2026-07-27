package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.integrations.GitHubAppOnboardingClient;
import io.elmos.scm.GitHubInstallationLifecycleService;
import org.springframework.web.util.UriComponentsBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

final class GithubInstallationOnboardingService {
    enum Stage { INSTALL, OAUTH }

    record Claims(
            int version,
            Stage stage,
            String organizationId,
            String connectionId,
            String nonce,
            Long installationId,
            Instant expiresAt
    ) {}

    record BeginResult(String status, String installationUrl, Instant expiresAt) {}
    record SetupResult(String authorizationUrl, Instant expiresAt) {}
    record Completion(
            String status,
            String organizationId,
            String connectionId,
            long installationId,
            int authorizedRepositoryCount,
            String redirectUrl
    ) {}

    interface StateStore {
        String begin(String organizationId, String requestedConnectionId, String nonce, Instant expiresAt);
        boolean advanceToOauth(String organizationId, String connectionId, String nonce,
                               long installationId, Instant expiresAt, Instant now);
        boolean consumeOauth(String organizationId, String connectionId, String nonce,
                             long installationId, Instant now);
    }

    private static final Duration STATE_TTL = Duration.ofMinutes(10);
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL = Base64.getUrlEncoder().withoutPadding();

    private final String appSlug;
    private final String clientId;
    private final String callbackUrl;
    private final String successUrl;
    private final String githubBaseUrl;
    private final StateCodec states;
    private final StateStore store;
    private final GitHubAppOnboardingClient github;
    private final GitHubInstallationLifecycleService lifecycle;
    private final Clock clock;

    GithubInstallationOnboardingService(
            String appSlug,
            String clientId,
            String callbackUrl,
            String successUrl,
            String githubBaseUrl,
            byte[] stateSecret,
            ObjectMapper mapper,
            StateStore store,
            GitHubAppOnboardingClient github,
            GitHubInstallationLifecycleService lifecycle,
            Clock clock
    ) {
        if (appSlug == null || !appSlug.matches("[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?")) {
            throw new IllegalArgumentException("GitHub App slug is invalid");
        }
        this.appSlug = appSlug;
        this.clientId = requireIdentifier(clientId, "client id", 128);
        this.callbackUrl = requireHttps(callbackUrl);
        this.successUrl = requireHttps(successUrl);
        this.githubBaseUrl = requireHttps(githubBaseUrl);
        this.states = new StateCodec(stateSecret, mapper, clock);
        this.store = Objects.requireNonNull(store);
        this.github = Objects.requireNonNull(github);
        this.lifecycle = Objects.requireNonNull(lifecycle);
        this.clock = Objects.requireNonNull(clock);
    }

    BeginResult begin(String organizationId, String requestedConnectionId) {
        String organization = requireIdentifier(organizationId, "organization id", 64);
        String requested = requestedConnectionId == null || requestedConnectionId.isBlank()
                ? null : requireIdentifier(requestedConnectionId, "connection id", 64);
        Instant expiresAt = clock.instant().plus(STATE_TTL);
        String nonce = nonce();
        String connectionId = store.begin(organization, requested, nonce, expiresAt);
        Claims claims = new Claims(1, Stage.INSTALL, organization, connectionId, nonce, null, expiresAt);
        String state = states.encode(claims);
        String installationUrl = UriComponentsBuilder.fromUriString(githubBaseUrl)
                .pathSegment("apps", appSlug, "installations", "new")
                .queryParam("state", state)
                .build().encode().toUriString();
        return new BeginResult("AWAITING_GITHUB_INSTALLATION", installationUrl, expiresAt);
    }

    SetupResult setup(String state, long installationId) {
        if (installationId <= 0) throw new SecurityException("GitHub installation id is invalid");
        Claims install = states.decode(state, Stage.INSTALL);
        Instant now = clock.instant();
        Instant expiresAt = now.plus(STATE_TTL);
        if (!store.advanceToOauth(install.organizationId(), install.connectionId(), install.nonce(),
                installationId, expiresAt, now)) {
            throw new SecurityException("GitHub installation state was expired, replayed, or mismatched");
        }
        Claims oauth = new Claims(1, Stage.OAUTH, install.organizationId(), install.connectionId(),
                install.nonce(), installationId, expiresAt);
        String oauthState = states.encode(oauth);
        String verifier = states.pkceVerifier(install.nonce());
        String challenge = URL.encodeToString(sha256(verifier.getBytes(StandardCharsets.US_ASCII)));
        String authorizationUrl = UriComponentsBuilder.fromUriString(githubBaseUrl)
                .path("/login/oauth/authorize")
                .queryParam("client_id", clientId)
                .queryParam("redirect_uri", callbackUrl)
                .queryParam("state", oauthState)
                .queryParam("code_challenge", challenge)
                .queryParam("code_challenge_method", "S256")
                .queryParam("allow_signup", "false")
                .build().encode().toUriString();
        return new SetupResult(authorizationUrl, expiresAt);
    }

    Completion complete(String state, String authorizationCode) {
        Claims oauth = states.decode(state, Stage.OAUTH);
        long installationId = Objects.requireNonNull(oauth.installationId(),
                "OAuth state is missing installation identity");
        Instant now = clock.instant();
        if (!store.consumeOauth(oauth.organizationId(), oauth.connectionId(), oauth.nonce(),
                installationId, now)) {
            throw new SecurityException("GitHub OAuth state was expired, replayed, or mismatched");
        }
        GitHubAppOnboardingClient.Discovery discovery = github.discoverAuthorizedInstallation(
                authorizationCode, states.pkceVerifier(oauth.nonce()), installationId);
        GitHubAppOnboardingClient.Installation remote = discovery.installation();
        GitHubInstallationLifecycleService.Installation installation =
                new GitHubInstallationLifecycleService.Installation(
                        "ghi-" + remote.id(),
                        oauth.connectionId(),
                        oauth.organizationId(),
                        remote.id(),
                        remote.accountId(),
                        remote.accountLogin(),
                        remote.targetType(),
                        remote.repositorySelection(),
                        remote.permissions(),
                        GitHubInstallationLifecycleService.Status.ACTIVE,
                        remote.installedAt(),
                        now
                );
        GitHubInstallationLifecycleService.Installation bound = lifecycle.bind(installation);
        Set<GitHubInstallationLifecycleService.Repository> repositories = new LinkedHashSet<>();
        for (GitHubAppOnboardingClient.Repository repository : discovery.repositories()) {
            repositories.add(new GitHubInstallationLifecycleService.Repository(
                    "ghr-" + repository.id(),
                    repository.id(),
                    repository.owner(),
                    repository.name(),
                    repository.fullName(),
                    repository.cloneUrl(),
                    repository.htmlUrl(),
                    repository.defaultBranch(),
                    repository.visibility(),
                    repository.archived(),
                    repository.disabled(),
                    repository.fork(),
                    repository.parentId()
            ));
        }
        lifecycle.synchronize(bound.githubInstallationId(), repositories, now);
        String redirect = UriComponentsBuilder.fromUriString(successUrl)
                .queryParam("github", "connected")
                .queryParam("repositories", repositories.size())
                .build().encode().toUriString();
        return new Completion("CONNECTED", oauth.organizationId(), bound.connectionId(),
                bound.githubInstallationId(), repositories.size(), redirect);
    }

    static final class StateCodec {
        private final byte[] secret;
        private final ObjectMapper mapper;
        private final Clock clock;

        StateCodec(byte[] secret, ObjectMapper mapper, Clock clock) {
            if (secret == null || secret.length < 32) {
                throw new IllegalArgumentException("GitHub onboarding state secret must contain at least 32 bytes");
            }
            this.secret = secret.clone();
            this.mapper = Objects.requireNonNull(mapper);
            this.clock = Objects.requireNonNull(clock);
        }

        String encode(Claims claims) {
            validate(claims);
            try {
                String payload = URL.encodeToString(mapper.writeValueAsBytes(claims));
                return payload + "." + URL.encodeToString(hmac(payload.getBytes(StandardCharsets.US_ASCII)));
            } catch (Exception error) {
                throw new IllegalStateException("Unable to create GitHub onboarding state", error);
            }
        }

        Claims decode(String value, Stage expectedStage) {
            if (value == null || value.length() > 4096) throw new SecurityException("GitHub state is invalid");
            String[] parts = value.split("\\.", -1);
            if (parts.length != 2) throw new SecurityException("GitHub state is invalid");
            byte[] supplied;
            try {
                supplied = Base64.getUrlDecoder().decode(parts[1]);
            } catch (IllegalArgumentException error) {
                throw new SecurityException("GitHub state signature is invalid");
            }
            byte[] expected = hmac(parts[0].getBytes(StandardCharsets.US_ASCII));
            if (!MessageDigest.isEqual(expected, supplied)) {
                throw new SecurityException("GitHub state signature is invalid");
            }
            try {
                Claims claims = mapper.readValue(Base64.getUrlDecoder().decode(parts[0]), Claims.class);
                validate(claims);
                if (claims.stage() != expectedStage) throw new SecurityException("GitHub state stage is invalid");
                return claims;
            } catch (SecurityException error) {
                throw error;
            } catch (Exception error) {
                throw new SecurityException("GitHub state payload is invalid");
            }
        }

        String pkceVerifier(String nonce) {
            requireIdentifier(nonce, "state nonce", 64);
            return URL.encodeToString(hmac(("pkce:" + nonce).getBytes(StandardCharsets.US_ASCII)));
        }

        private void validate(Claims claims) {
            if (claims == null || claims.version() != 1 || claims.stage() == null
                    || claims.expiresAt() == null) {
                throw new SecurityException("GitHub state payload is incomplete");
            }
            requireIdentifier(claims.organizationId(), "organization id", 64);
            requireIdentifier(claims.connectionId(), "connection id", 64);
            requireIdentifier(claims.nonce(), "state nonce", 64);
            Instant now = clock.instant();
            if (!claims.expiresAt().isAfter(now)
                    || claims.expiresAt().isAfter(now.plus(Duration.ofMinutes(11)))) {
                throw new SecurityException("GitHub state is expired or outside its bounded lifetime");
            }
            if (claims.stage() == Stage.INSTALL && claims.installationId() != null
                    || claims.stage() == Stage.OAUTH
                    && (claims.installationId() == null || claims.installationId() <= 0)) {
                throw new SecurityException("GitHub state installation identity is invalid");
            }
        }

        private byte[] hmac(byte[] input) {
            try {
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(secret, "HmacSHA256"));
                return mac.doFinal(input);
            } catch (Exception error) {
                throw new IllegalStateException("Unable to authenticate GitHub state", error);
            }
        }
    }

    private static String nonce() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return URL.encodeToString(bytes);
    }

    private static byte[] sha256(byte[] input) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(input);
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static String requireIdentifier(String value, String field, int maximum) {
        if (value == null || value.isBlank() || value.length() > maximum
                || !value.matches("[A-Za-z0-9][A-Za-z0-9_:-]*")) {
            throw new IllegalArgumentException("GitHub onboarding " + field + " is invalid");
        }
        return value;
    }

    private static String requireHttps(String raw) {
        if (raw == null || raw.isBlank()) throw new IllegalArgumentException("GitHub onboarding HTTPS URL is required");
        java.net.URI uri = java.net.URI.create(raw);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                || uri.getUserInfo() != null || uri.getFragment() != null) {
            throw new SecurityException("GitHub onboarding endpoint must be credential-free HTTPS");
        }
        return raw.endsWith("/") ? raw.substring(0, raw.length() - 1) : raw;
    }
}
