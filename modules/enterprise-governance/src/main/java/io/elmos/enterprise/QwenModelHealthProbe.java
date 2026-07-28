package io.elmos.enterprise;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Real {@link ModelHealthProbe} for the Alibaba Qwen catalog entry
 * ({@code qwen3.8-max-preview}). Makes one bounded, side-effect-free GET to
 * DashScope's OpenAI-compatible-mode {@code /v1/models} endpoint to confirm
 * the supplied credential is actually accepted.
 *
 * <p><b>Unlike {@link DeepSeekModelHealthProbe}, this probe has not been run
 * against live Alibaba Cloud traffic.</b> No real DashScope credential has
 * been supplied to this codebase; the endpoint URL, header name, and
 * status-code mapping below follow Alibaba Cloud's publicly documented
 * OpenAI-compatible-mode REST conventions but are code-complete, not
 * field-verified. An operator must export a real key as
 * {@code ELMOS_MODEL_CREDENTIAL_QWEN3_8_MAX_PREVIEW} and run
 * {@code QwenModelHealthProbeTest#liveQwenCredentialProvisionsARealApprovedEndpoint}
 * before this probe's live behavior can be trusted the way DeepSeek's now is.
 *
 * <p>The credential is only ever placed in the Authorization header of this one
 * request; it is never logged, never written to disk, and this class has no
 * other side effect.
 */
public final class QwenModelHealthProbe implements ModelHealthProbe {
    private static final URI MODELS_ENDPOINT =
            URI.create("https://dashscope.aliyuncs.com/compatible-mode/v1/models");
    private static final Duration TIMEOUT = Duration.ofSeconds(15);

    private final HttpClient httpClient;

    public QwenModelHealthProbe() {
        this(HttpClient.newBuilder().connectTimeout(TIMEOUT).build());
    }

    /** Package-visible seam for tests that need to substitute a fake {@link HttpClient}. */
    QwenModelHealthProbe(HttpClient httpClient) {
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
            throw new RuntimeException("QWEN_PROBE_TRANSPORT_FAILURE", error);
        }
        return interpret(response.statusCode());
    }

    /** Pure, unit-testable without any network access. */
    static Result interpret(int statusCode) {
        if (statusCode == 200) {
            return new Result(true, "QWEN_MODELS_LIST_OK", "http-status:200");
        }
        if (statusCode == 401 || statusCode == 403) {
            return new Result(false, "QWEN_CREDENTIAL_REJECTED:" + statusCode, "http-status:" + statusCode);
        }
        if (statusCode == 429) {
            return new Result(false, "QWEN_RATE_LIMITED", "http-status:429");
        }
        return new Result(false, "QWEN_UNEXPECTED_STATUS:" + statusCode, "http-status:" + statusCode);
    }
}
