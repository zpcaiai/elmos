package io.elmos.enterprise;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Real {@link ModelHealthProbe} for the DeepSeek catalog entries
 * ({@code deepseek-v4-pro}, {@code deepseek-v4-flash}). Makes one bounded,
 * side-effect-free call to DeepSeek's OpenAI-compatible {@code /v1/models}
 * endpoint to confirm the supplied credential is actually accepted —
 * possessing a non-blank string is not evidence of anything by itself.
 *
 * The credential is only ever placed in the Authorization header of this one
 * request; it is never logged, never written to disk, and this class has no
 * other side effect. Callers are responsible for how the credential reaches
 * them (see {@link ModelCredentialSource}) — this class does not read
 * environment variables or files itself.
 */
public final class DeepSeekModelHealthProbe implements ModelHealthProbe {
    private static final URI MODELS_ENDPOINT = URI.create("https://api.deepseek.com/v1/models");
    private static final Duration TIMEOUT = Duration.ofSeconds(15);

    private final HttpClient httpClient;

    public DeepSeekModelHealthProbe() {
        this(HttpClient.newBuilder().connectTimeout(TIMEOUT).build());
    }

    /** Package-visible seam for tests that need to substitute a fake {@link HttpClient}. */
    DeepSeekModelHealthProbe(HttpClient httpClient) {
        this.httpClient = java.util.Objects.requireNonNull(httpClient, "httpClient");
    }

    @Override
    public Result probe(String modelId, String credential) {
        EnterpriseModels.require(modelId, "modelId");
        EnterpriseModels.require(credential, "credential");
        HttpRequest request = HttpRequest.newBuilder(MODELS_ENDPOINT)
                .timeout(TIMEOUT)
                .header("Authorization", "Bearer " + credential)
                .GET()
                .build();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (java.io.IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new RuntimeException("DEEPSEEK_PROBE_TRANSPORT_FAILURE", error);
        }
        return interpret(response.statusCode());
    }

    /** Pure, unit-testable without any network access. */
    static Result interpret(int statusCode) {
        if (statusCode == 200) {
            return new Result(true, "DEEPSEEK_MODELS_LIST_OK", "http-status:200");
        }
        if (statusCode == 401 || statusCode == 403) {
            return new Result(false, "DEEPSEEK_CREDENTIAL_REJECTED:" + statusCode, "http-status:" + statusCode);
        }
        if (statusCode == 429) {
            return new Result(false, "DEEPSEEK_RATE_LIMITED", "http-status:429");
        }
        return new Result(false, "DEEPSEEK_UNEXPECTED_STATUS:" + statusCode, "http-status:" + statusCode);
    }
}
