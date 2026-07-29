package io.elmos.integrations;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.integrations.GitRepositoryWorkspaceService.Provider;
import io.elmos.integrations.GitRepositoryWorkspaceService.PullRequestContext;
import io.elmos.integrations.GitRepositoryWorkspaceService.PullRequestPublisher;
import io.elmos.integrations.GitRepositoryWorkspaceService.PullRequestResult;
import io.elmos.scm.EphemeralCredential;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;

/**
 * Exact GitHub/Gitee pull-request adapters. Generic Git intentionally has no
 * assumed review API.
 */
public final class ProviderPullRequestPublisher implements PullRequestPublisher {
    private final HttpClient client;
    private final ObjectMapper json;
    private final Map<String, URI> apiBases;

    public ProviderPullRequestPublisher(
            HttpClient client,
            ObjectMapper json,
            Map<String, URI> apiBases
    ) {
        this.client = Objects.requireNonNull(client, "client");
        this.json = Objects.requireNonNull(json, "json");
        this.apiBases = Map.copyOf(apiBases);
    }

    @Override
    public PullRequestResult publish(
            String workspaceId,
            PullRequestContext context,
            EphemeralCredential credential
    ) {
        URI base = apiBases.get(context.providerInstanceId().toLowerCase());
        if (base == null) throw new IllegalStateException("GIT_PULL_REQUEST_API_NOT_ALLOWLISTED");
        if (context.provider() == Provider.GENERIC_GIT) {
            throw new IllegalArgumentException("GENERIC_GIT_PULL_REQUEST_UNSUPPORTED");
        }
        String[] repository = context.nativeRepositoryId().split("/", -1);
        if (repository.length != 2
                || !repository[0].matches("[A-Za-z0-9_.-]+")
                || !repository[1].matches("[A-Za-z0-9_.-]+")) {
            throw new IllegalArgumentException("GIT_NATIVE_REPOSITORY_ID_INVALID");
        }
        return credential.use(chars -> publishWithToken(
                workspaceId, context, base, repository[0], repository[1],
                new String(chars)));
    }

    private PullRequestResult publishWithToken(
            String workspaceId,
            PullRequestContext context,
            URI base,
            String owner,
            String repository,
            String token
    ) {
        try {
            String apiPath = context.provider() == Provider.GITHUB
                    ? "/repos/" + owner + "/" + repository + "/pulls"
                    : "/api/v5/repos/" + owner + "/" + repository + "/pulls";
            URI endpoint = base.resolve(apiPath);
            String payload = json.writeValueAsString(context.provider() == Provider.GITHUB
                    ? Map.of(
                            "title", context.title(),
                            "head", context.sourceBranch(),
                            "base", context.baseBranch(),
                            "body", context.body())
                    : Map.of(
                            "title", context.title(),
                            "head", context.sourceBranch(),
                            "base", context.baseBranch(),
                            "body", context.body(),
                            "prune_source_branch", false));
            HttpRequest.Builder builder = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/json")
                    .header("Content-Type", "application/json")
                    .header("Idempotency-Key", context.idempotencyKey())
                    .POST(HttpRequest.BodyPublishers.ofString(payload));
            if (context.provider() == Provider.GITHUB) {
                builder.header("Authorization", "Bearer " + token)
                        .header("X-GitHub-Api-Version", "2022-11-28");
            } else {
                builder.header("Authorization", "token " + token);
            }
            HttpResponse<String> response = client.send(
                    builder.build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.body().length() > 1_048_576) {
                throw new IllegalStateException("GIT_PULL_REQUEST_RESPONSE_TOO_LARGE");
            }
            if (response.statusCode() != 201 && response.statusCode() != 200) {
                throw new IllegalStateException(
                        "GIT_PULL_REQUEST_PROVIDER_REJECTED_" + response.statusCode());
            }
            JsonNode body = json.readTree(response.body());
            String url = body.path("html_url").asText("");
            String id = body.path("number").asText("");
            URI parsed = URI.create(url);
            if (id.isBlank() || !"https".equalsIgnoreCase(parsed.getScheme())
                    || parsed.getHost() == null
                    || !parsed.getHost().equalsIgnoreCase(context.providerInstanceId())) {
                throw new SecurityException("GIT_PULL_REQUEST_RESPONSE_INVALID");
            }
            return new PullRequestResult(
                    workspaceId, id, url, context.sourceCommit(),
                    context.sourceBranch(), context.baseBranch(),
                    "PULL_REQUEST_CREATED", true);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("GIT_PULL_REQUEST_INTERRUPTED", error);
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GIT_PULL_REQUEST_FAILED", error);
        } finally {
            // The credential lease clears its mutable copy. Provider APIs require
            // an immutable header String, which is never persisted or logged.
            token = "";
        }
    }
}
