package io.elmos.enterprise;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * Real {@link ModelHealthProbe} for the Google catalog entries
 * ({@code gemini-3.6-flash}, {@code gemini-3.5-flash}). Makes one bounded,
 * side-effect-free GET to the Generative Language API's {@code /v1beta/models}
 * endpoint to confirm the supplied credential is actually accepted.
 *
 * <p><b>Unlike {@link DeepSeekModelHealthProbe}, this probe has not been run
 * against live Google traffic.</b> No real Google credential has been supplied
 * to this codebase; the endpoint URL, the query-parameter auth convention, and
 * the status-code mapping below follow Google's publicly documented REST
 * conventions but are code-complete, not field-verified. An operator must
 * export a real key as {@code ELMOS_MODEL_CREDENTIAL_GEMINI_3_6_FLASH} and run
 * {@code GoogleModelHealthProbeTest#liveGoogleCredentialProvisionsARealApprovedEndpoint}
 * before this probe's live behavior can be trusted the way DeepSeek's now is.
 *
 * <p>Unlike the other vendor probes in this package, the Generative Language
 * API authenticates via an {@code ?key=} query parameter rather than a header.
 * The credential is only ever placed in that query parameter of this one
 * request; it is never logged, never written to disk, and this class has no
 * other side effect.
 */
public final class GoogleModelHealthProbe implements ModelHealthProbe {
    private static final String MODELS_ENDPOINT_BASE = "https://generativelanguage.googleapis.com/v1beta/models";
    private static final Duration TIMEOUT = Duration.ofSeconds(15);

    private final HttpClient httpClient;

    public GoogleModelHealthProbe() {
        this(HttpClient.newBuilder().connectTimeout(TIMEOUT).build());
    }

    /** Package-visible seam for tests that need to substitute a fake {@link HttpClient}. */
    GoogleModelHealthProbe(HttpClient httpClient) {
        this.httpClient = java.util.Objects.requireNonNull(httpClient, "httpClient");
    }

    @Override
    public Result probe(String modelId, String credential) {
        EnterpriseModels.require(modelId, "modelId");
        EnterpriseModels.require(credential, "credential");
        URI endpoint = URI.create(MODELS_ENDPOINT_BASE + "?key="
                + URLEncoder.encode(credential, StandardCharsets.UTF_8));
        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(TIMEOUT)
                .GET()
                .build();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (java.io.IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new RuntimeException("GOOGLE_PROBE_TRANSPORT_FAILURE", error);
        }
        return interpret(response.statusCode());
    }

    /** Pure, unit-testable without any network access. */
    static Result interpret(int statusCode) {
        if (statusCode == 200) {
            return new Result(true, "GOOGLE_MODELS_LIST_OK", "http-status:200");
        }
        if (statusCode == 401 || statusCode == 403) {
            return new Result(false, "GOOGLE_CREDENTIAL_REJECTED:" + statusCode, "http-status:" + statusCode);
        }
        if (statusCode == 429) {
            return new Result(false, "GOOGLE_RATE_LIMITED", "http-status:429");
        }
        return new Result(false, "GOOGLE_UNEXPECTED_STATUS:" + statusCode, "http-status:" + statusCode);
    }
}
