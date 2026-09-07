package io.elmos.enterprise;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Real {@link ModelHealthProbe} for the Anthropic catalog entries
 * ({@code claude-fable-5}, {@code claude-opus-5}). Makes one bounded,
 * side-effect-free GET to Anthropic's {@code /v1/models} endpoint to confirm
 * the supplied credential is actually accepted.
 *
 * <p><b>Unlike {@link DeepSeekModelHealthProbe}, this probe has not been run
 * against live Anthropic traffic.</b> No real Anthropic credential has been
 * supplied to this codebase; the endpoint URL, header names, and status-code
 * mapping below follow Anthropic's publicly documented REST conventions but
 * are code-complete, not field-verified. An operator must export a real key as
 * {@code ELMOS_MODEL_CREDENTIAL_CLAUDE_OPUS_5} and run
 * {@code AnthropicModelHealthProbeTest#liveAnthropicCredentialProvisionsARealApprovedEndpoint}
 * before this probe's live behavior can be trusted the way DeepSeek's now is.
 *
 * <p>The credential is only ever placed in the {@code x-api-key} header of this
 * one request; it is never logged, never written to disk, and this class has
 * no other side effect.
 */
public final class AnthropicModelHealthProbe implements ModelHealthProbe {
    private static final URI MODELS_ENDPOINT = URI.create("https://api.anthropic.com/v1/models");
    private static final String ANTHROPIC_VERSION = "2023-06-01";
    private static final Duration TIMEOUT = Duration.ofSeconds(15);

    private final HttpClient httpClient;

    public AnthropicModelHealthProbe() {
        this(HttpClient.newBuilder().connectTimeout(TIMEOUT).build());
    }

    /** Package-visible seam for tests that need to substitute a fake {@link HttpClient}. */
    AnthropicModelHealthProbe(HttpClient httpClient) {
        this.httpClient = java.util.Objects.requireNonNull(httpClient, "httpClient");
    }

    @Override
    public Result probe(String modelId, String credential) {
        EnterpriseModels.require(modelId, "modelId");
        EnterpriseModels.require(credential, "credential");
        HttpRequest request = HttpRequest.newBuilder(MODELS_ENDPOINT)
                .timeout(TIMEOUT)
                .header("x-api-key", credential)
                .header("anthropic-version", ANTHROPIC_VERSION)
                .GET()
                .build();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (java.io.IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new RuntimeException("ANTHROPIC_PROBE_TRANSPORT_FAILURE", error);
        }
        return interpret(response.statusCode());
    }

    /** Pure, unit-testable without any network access. */
    static Result interpret(int statusCode) {
        if (statusCode == 200) {
            return new Result(true, "ANTHROPIC_MODELS_LIST_OK", "http-status:200");
        }
        if (statusCode == 401 || statusCode == 403) {
            return new Result(false, "ANTHROPIC_CREDENTIAL_REJECTED:" + statusCode, "http-status:" + statusCode);
        }
        if (statusCode == 429) {
            return new Result(false, "ANTHROPIC_RATE_LIMITED", "http-status:429");
        }
        return new Result(false, "ANTHROPIC_UNEXPECTED_STATUS:" + statusCode, "http-status:" + statusCode);
    }
}
