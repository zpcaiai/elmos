package io.elmos.liveworkbench;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.product.execution.SecureExecutionModels;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

/** HTTPS provider adapter with bounded timeouts, HMAC request binding and explicit unknown-result reconciliation. */
public final class HttpSandboxProvider implements SandboxProviderPort {
    public record Configuration(URI baseUri, Duration timeout, String signingKey, boolean allowLoopbackHttp,
                                Set<String> previewOrigins) {
        public Configuration {
            if (baseUri == null || !baseUri.isAbsolute() || baseUri.getUserInfo() != null || baseUri.getQuery() != null || baseUri.getFragment() != null)
                throw new IllegalArgumentException("provider base URI");
            boolean loopback = "localhost".equalsIgnoreCase(baseUri.getHost()) || "127.0.0.1".equals(baseUri.getHost()) || "::1".equals(baseUri.getHost());
            if (!"https".equalsIgnoreCase(baseUri.getScheme()) && !(allowLoopbackHttp && loopback)) throw new IllegalArgumentException("provider must use HTTPS");
            if (timeout == null || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofSeconds(30)) > 0) throw new IllegalArgumentException("provider timeout");
            if (signingKey == null || signingKey.length() < 32) throw new IllegalArgumentException("provider signing key must be at least 32 characters");
            previewOrigins = Set.copyOf(previewOrigins == null || previewOrigins.isEmpty()
                    ? Set.of(origin(baseUri)) : previewOrigins);
            if (previewOrigins.stream().anyMatch(value -> {
                try { URI uri = URI.create(value); return !"https".equalsIgnoreCase(uri.getScheme()) || !value.equals(origin(uri)); }
                catch (IllegalArgumentException error) { return true; }
            })) throw new IllegalArgumentException("preview origins must be exact HTTPS origins");
        }
    }

    private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {};
    private final HttpClient http;
    private final ObjectMapper json;
    private final Configuration configuration;

    public HttpSandboxProvider(HttpClient http, ObjectMapper json, Configuration configuration) {
        this.http = http; this.json = json; this.configuration = configuration;
    }

    @Override public boolean ready() {
        try {
            long timestamp = System.currentTimeMillis() / 1_000;
            String idempotencyKey = "health-" + (timestamp / 10);
            String bodyDigest = LwDigest.sha256("");
            Map<String, Object> response = send(base("/v1/workbench/health", idempotencyKey, timestamp, bodyDigest).GET().build());
            return VERSION.equals(response.get("schemaVersion")) && Boolean.TRUE.equals(response.get("ready"));
        } catch (RuntimeException unavailable) {
            return false;
        }
    }

    @Override public SecureExecutionModels.AdmissionRequest preflight(PrincipalScope scope, String sessionId,
                                                                       CreateSessionRequest request, String idempotencyKey) {
        Map<String, Object> response = post("/v1/workbench/admission", idempotencyKey, Map.ofEntries(
                Map.entry("schemaVersion", VERSION), Map.entry("tenantId", scope.tenantId()),
                Map.entry("accountId", scope.accountId()), Map.entry("actorId", scope.actorId()),
                Map.entry("environmentId", scope.environmentId()), Map.entry("sessionId", sessionId),
                Map.entry("repositoryId", request.repositoryId()), Map.entry("snapshotId", request.snapshotId()),
                Map.entry("deliveryId", request.deliveryId()), Map.entry("runtimeProfileId", request.runtimeProfileId()),
                Map.entry("scenario", request.scenario()), Map.entry("mode", request.mode()),
                Map.entry("slotWeight", request.slotWeight()), Map.entry("debugRequired", request.debugRequired())));
        return new SecureExecutionModels.AdmissionRequest(
                scope.tenantId(), sessionId, text(response, "runnerId"), number(response, "assignmentEpoch"),
                rawDigest(request.snapshotId()), rawDigest(text(response, "policyBundleDigest")),
                SecureExecutionModels.IsolationProvider.valueOf(text(response, "isolationProvider")),
                Instant.ofEpochSecond(number(response, "evaluatedAtEpochSecond")),
                bool(response, "capabilityAttested"), bool(response, "capabilityIndependentlyVerified"),
                bool(response, "fixedRunnerVersion"), bool(response, "fixedImageDigest"),
                bool(response, "capacityReserved"), bool(response, "hardConstraintsSatisfied"),
                bool(response, "assignmentLeaseActive"), bool(response, "schedulerSeparatedFromProvider"),
                bool(response, "sourceReadOnly"), bool(response, "rootless"), bool(response, "defaultDenyNetwork"),
                bool(response, "metadataEndpointsBlocked"), bool(response, "processBoundSecrets"),
                bool(response, "secretPersisted"), bool(response, "seccompCapabilitiesAndLsmEnforced"),
                bool(response, "resourceLimitsEnforced"), bool(response, "repositoryCannotWeakenSandbox"),
                bool(response, "typedCommandsOnly"), bool(response, "checkpointCompatible"),
                bool(response, "durableQueueAndOutbox"), bool(response, "redactedBeforePersistence"),
                bool(response, "offlinePermitCreatesNewRights"), bool(response, "siteEpochValid"),
                bool(response, "checksummedArtifactTransfer"), bool(response, "idempotentCleanup"),
                bool(response, "unknownResultsReconciled"), stringList(response.get("evidenceRefs")));
    }

    @Override public ProviderAllocation allocate(PrincipalScope scope, String sessionId, CreateSessionRequest request,
                                                 String idempotencyKey, long requestedHardDeadlineEpochSecond) {
        Map<String, Object> response = post("/v1/workbench/sessions", idempotencyKey, Map.ofEntries(
                Map.entry("schemaVersion", VERSION), Map.entry("tenantId", scope.tenantId()),
                Map.entry("accountId", scope.accountId()), Map.entry("actorId", scope.actorId()),
                Map.entry("environmentId", scope.environmentId()), Map.entry("sessionId", sessionId),
                Map.entry("repositoryId", request.repositoryId()), Map.entry("snapshotId", request.snapshotId()),
                Map.entry("deliveryId", request.deliveryId()), Map.entry("runtimeProfileId", request.runtimeProfileId()),
                Map.entry("scenario", request.scenario()), Map.entry("mode", request.mode()),
                Map.entry("slotWeight", request.slotWeight()), Map.entry("debugRequired", request.debugRequired()),
                Map.entry("requestedHardDeadlineEpochSecond", requestedHardDeadlineEpochSecond)));
        return new ProviderAllocation(text(response, "providerSessionId"), text(response, "resourceLeaseId"),
                number(response, "hardDeadlineEpochSecond"), stringMap(response.get("members")), stringList(response.get("evidenceRefs")));
    }

    @Override public CleanupOutcome cleanupUnknownAllocation(PrincipalScope scope, String controlSessionId,
                                                               String allocationIdempotencyKey, String reason) {
        Map<String, Object> response = post("/v1/workbench/sessions/by-control/" + path(controlSessionId) + "/cleanup",
                "reconcile-" + allocationIdempotencyKey, Map.of(
                        "schemaVersion", VERSION, "tenantId", scope.tenantId(), "controlSessionId", controlSessionId,
                        "allocationIdempotencyKey", allocationIdempotencyKey, "reason", reason));
        return cleanupOutcome(response);
    }

    @Override public ProviderCommandResult dispatchDebug(PrincipalScope scope, SessionView session, String commandId,
                                                         String idempotencyKey, DebugRequest request) {
        try {
            Map<String, Object> response = post("/v1/workbench/sessions/" + path(session.providerSessionId()) + "/debug-commands", idempotencyKey, Map.of(
                    "schemaVersion", VERSION, "tenantId", scope.tenantId(), "sessionId", session.sessionId(),
                    "generation", session.generation(), "commandId", commandId, "command", request.command(),
                    "argumentsDigest", request.argumentsDigest(), "stopEpoch", request.stopEpoch(),
                    "controlLeaseId", request.controlLeaseId(), "deadlineEpochSecond", session.expiresAtEpochSecond()));
            return result(response);
        } catch (LiveWorkbenchException unavailable) {
            return new ProviderCommandResult(CommandState.UNKNOWN, null, null);
        }
    }

    @Override public ProviderCommandResult reconcileDebug(PrincipalScope scope, SessionView session, String commandId,
                                                          String idempotencyKey) {
        Map<String, Object> response = get("/v1/workbench/sessions/" + path(session.providerSessionId()) + "/debug-commands/" + path(commandId), idempotencyKey,
                scope.tenantId(), session.sessionId());
        return result(response);
    }

    @Override public CleanupOutcome cleanup(PrincipalScope scope, SessionView session, String reason) {
        Map<String, Object> response = post("/v1/workbench/sessions/" + path(session.providerSessionId()) + "/cleanup", "cleanup-" + session.sessionId(), Map.of(
                "schemaVersion", VERSION, "tenantId", scope.tenantId(), "sessionId", session.sessionId(),
                "generation", session.generation(), "resourceLeaseId", session.resourceLeaseId(), "reason", reason,
                "deadlineEpochSecond", session.expiresAtEpochSecond() == null ? session.providerHardDeadlineEpochSecond() : session.expiresAtEpochSecond()));
        return cleanupOutcome(response);
    }

    @Override public PreviewAccess previewAccess(PrincipalScope scope, SessionView session) {
        Map<String, Object> response = post("/v1/workbench/sessions/" + path(session.providerSessionId()) + "/preview-access",
                "preview-access-" + session.sessionId() + "-" + session.generation(), Map.of(
                        "schemaVersion", VERSION, "tenantId", scope.tenantId(), "accountId", scope.accountId(),
                        "actorId", scope.actorId(), "controlSessionId", session.sessionId(),
                        "generation", session.generation(), "hardExpiryEpochSecond", session.expiresAtEpochSecond()));
        PreviewAccess access = new PreviewAccess(text(response, "url"), number(response, "expiresAtEpochSecond"),
                text(response, "audience"), stringList(response.get("evidenceRefs")));
        if (!configuration.previewOrigins().contains(origin(URI.create(access.url()))))
            throw LiveWorkbenchException.unavailable("PREVIEW_ORIGIN_NOT_ALLOWLISTED");
        return access;
    }

    @Override public SourceContent readSource(PrincipalScope scope, SourceAnchor anchor) {
        Map<String, Object> response = post("/v1/workbench/source", "source-" + LwDigest.sha256(
                anchor.snapshotId() + anchor.path() + anchor.byteStart() + anchor.byteEnd()).substring(7, 39), Map.ofEntries(
                Map.entry("schemaVersion", VERSION), Map.entry("tenantId", scope.tenantId()),
                Map.entry("actorId", scope.actorId()), Map.entry("repositoryId", anchor.repositoryId()),
                Map.entry("snapshotId", anchor.snapshotId()), Map.entry("path", anchor.path()),
                Map.entry("blobDigest", anchor.blobDigest()), Map.entry("byteStart", anchor.byteStart()),
                Map.entry("byteEnd", anchor.byteEnd()), Map.entry("coordinateSystem", anchor.coordinateSystem())));
        return new SourceContent(anchor, text(response, "content"), text(response, "selectionDigest"),
                stringList(response.get("evidenceRefs")));
    }

    @Override public MissionAttemptReceipt assess(PrincipalScope scope, LearningMission mission,
                                                   MissionAttemptRequest request, String attemptId, String idempotencyKey) {
        Map<String, Object> response = post("/v1/workbench/missions/" + path(mission.missionId()) + "/attempts",
                idempotencyKey, Map.ofEntries(
                        Map.entry("schemaVersion", VERSION), Map.entry("tenantId", scope.tenantId()),
                        Map.entry("actorId", scope.actorId()), Map.entry("missionId", mission.missionId()),
                        Map.entry("snapshotId", mission.snapshotId()), Map.entry("attemptId", attemptId),
                        Map.entry("sessionId", request.sessionId()), Map.entry("generation", request.generation()),
                        Map.entry("answersDigest", request.answersDigest()), Map.entry("runtimeEventIds", request.runtimeEventIds()),
                        Map.entry("assessmentServiceRef", mission.assessmentServiceRef())));
        return attempt(response, attemptId, idempotencyKey);
    }

    @Override public MissionAttemptReceipt reconcileAssessment(PrincipalScope scope, LearningMission mission,
                                                                 String attemptId, String idempotencyKey) {
        Map<String, Object> response = get("/v1/workbench/missions/" + path(mission.missionId()) + "/attempts/" + path(attemptId),
                idempotencyKey, scope.tenantId(), attemptId);
        return attempt(response, attemptId, idempotencyKey);
    }

    private CleanupOutcome cleanupOutcome(Map<String, Object> response) {
        try {
            SessionState status = SessionState.valueOf(text(response, "status"));
            return new CleanupOutcome(status, booleanMap(response.get("memberChecks")), text(response, "verifierId"),
                    stringList(response.get("evidenceRefs")), number(response, "observedAtEpochSecond"));
        } catch (IllegalArgumentException error) {
            throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID");
        }
    }

    private ProviderCommandResult result(Map<String, Object> response) {
        CommandState state = CommandState.valueOf(text(response, "state"));
        String evidence = optionalText(response, "evidenceRef"); String digest = optionalText(response, "responseDigest");
        return new ProviderCommandResult(state, evidence, digest);
    }

    private MissionAttemptReceipt attempt(Map<String, Object> response, String attemptId, String idempotencyKey) {
        try {
            CommandState state = CommandState.valueOf(text(response, "state"));
            Object rawScore = response.get("score");
            Integer score = rawScore instanceof Number number ? number.intValue() : null;
            return new MissionAttemptReceipt(attemptId, idempotencyKey, state, score,
                    stringList(response.get("feedbackClaimIds")), stringList(response.get("evidenceRefs")),
                    response.get("version") instanceof Number number ? number.longValue() : 0);
        } catch (IllegalArgumentException error) {
            throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID");
        }
    }

    private Map<String, Object> get(String path, String idempotencyKey, String tenantId, String sessionId) {
        long timestamp = System.currentTimeMillis() / 1000;
        String bodyDigest = LwDigest.sha256("");
        HttpRequest request = base(path, idempotencyKey, timestamp, bodyDigest)
                .header("X-Elmos-Tenant", tenantId).header("X-Elmos-Session", sessionId).GET().build();
        return send(request);
    }
    private Map<String, Object> post(String path, String idempotencyKey, Map<String, Object> payload) {
        try {
            byte[] body = json.writeValueAsBytes(payload); long timestamp = System.currentTimeMillis() / 1000;
            HttpRequest request = base(path, idempotencyKey, timestamp, LwDigest.sha256(body))
                    .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
            return send(request);
        } catch (LiveWorkbenchException error) { throw error; }
        catch (Exception error) { throw LiveWorkbenchException.unavailable("PROVIDER_REQUEST_ENCODING_FAILED"); }
    }
    private HttpRequest.Builder base(String path, String idempotencyKey, long timestamp, String bodyDigest) {
        String canonical = "lw.v1\n" + path + "\n" + idempotencyKey + "\n" + timestamp + "\n" + bodyDigest;
        return HttpRequest.newBuilder(configuration.baseUri().resolve(path)).timeout(configuration.timeout())
                .header("Accept", "application/json").header("Idempotency-Key", idempotencyKey)
                .header("X-Elmos-Timestamp", Long.toString(timestamp)).header("X-Elmos-Body-SHA256", bodyDigest)
                .header("X-Elmos-Signature", hmac(canonical));
    }
    private Map<String, Object> send(HttpRequest request) {
        try {
            HttpResponse<byte[]> response = http.send(request, HttpResponse.BodyHandlers.ofByteArray());
            String mediaType = response.headers().firstValue("Content-Type").orElse("").split(";", 2)[0].trim();
            if (response.statusCode() < 200 || response.statusCode() >= 300 || response.body().length < 2
                    || response.body().length > 1_048_576 || !"application/json".equalsIgnoreCase(mediaType))
                throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_REJECTED");
            return json.readValue(response.body(), MAP);
        } catch (LiveWorkbenchException error) { throw error; }
        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw LiveWorkbenchException.unavailable("PROVIDER_REQUEST_INTERRUPTED"); }
        catch (Exception error) { throw LiveWorkbenchException.unavailable("PROVIDER_UNAVAILABLE"); }
    }
    private String hmac(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256"); mac.init(new SecretKeySpec(configuration.signingKey().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) { throw new IllegalStateException("HMAC unavailable", error); }
    }
    private static String path(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._:-]{1,200}")) throw new IllegalArgumentException("unsafe provider path identity"); return value;
    }
    private static String origin(URI uri) {
        int port = uri.getPort();
        return uri.getScheme().toLowerCase(java.util.Locale.ROOT) + "://" + uri.getHost().toLowerCase(java.util.Locale.ROOT)
                + (port < 0 ? "" : ":" + port);
    }
    private static String text(Map<String, Object> value, String key) { String result = optionalText(value, key); if (result == null) throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID"); return result; }
    private static String optionalText(Map<String, Object> value, String key) { Object raw = value.get(key); return raw instanceof String text && !text.isBlank() ? text : null; }
    private static long number(Map<String, Object> value, String key) { Object raw = value.get(key); if (!(raw instanceof Number number)) throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID"); return number.longValue(); }
    private static boolean bool(Map<String, Object> value, String key) { Object raw = value.get(key); if (!(raw instanceof Boolean result)) throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID"); return result; }
    private static String rawDigest(String value) {
        if (LwDigest.exact(value)) return value.substring("sha256:".length());
        if (value != null && value.matches("[a-f0-9]{64}")) return value;
        throw LiveWorkbenchException.unavailable("PROVIDER_RESPONSE_INVALID");
    }
    private static Map<String, String> stringMap(Object raw) { if (!(raw instanceof Map<?, ?> map)) return Map.of(); return map.entrySet().stream().filter(e -> e.getKey() instanceof String && e.getValue() instanceof String).collect(java.util.stream.Collectors.toUnmodifiableMap(e -> (String)e.getKey(), e -> (String)e.getValue())); }
    private static Map<String, Boolean> booleanMap(Object raw) { if (!(raw instanceof Map<?, ?> map)) return Map.of(); return map.entrySet().stream().filter(e -> e.getKey() instanceof String && e.getValue() instanceof Boolean).collect(java.util.stream.Collectors.toUnmodifiableMap(e -> (String)e.getKey(), e -> (Boolean)e.getValue())); }
    private static List<String> stringList(Object raw) { if (!(raw instanceof List<?> list)) return List.of(); return list.stream().filter(String.class::isInstance).map(String.class::cast).toList(); }
}
