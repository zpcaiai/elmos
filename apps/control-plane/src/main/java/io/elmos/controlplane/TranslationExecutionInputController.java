package io.elmos.controlplane;

import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;

/** Runner input reads use the same authoritative lease and object metadata as artifacts. */
@RestController
final class TranslationExecutionInputController {
    private final JdbcObjectStorageStore storage;
    private final ExecutionJobPort jobs;
    private final ArtifactController.ObjectStoreFactory stores;
    private final java.util.concurrent.Semaphore downloads = new java.util.concurrent.Semaphore(4);
    private final java.util.Set<String> activeLeases = java.util.concurrent.ConcurrentHashMap.newKeySet();
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER).build();
    private static final java.util.concurrent.ScheduledExecutorService DEADLINES =
            java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
                Thread thread = new Thread(r, "translation-input-deadlines"); thread.setDaemon(true); return thread;
            });
    TranslationExecutionInputController(JdbcObjectStorageStore storage, ExecutionJobPort jobs,
                                       ArtifactController.ObjectStoreFactory stores) {
        this.storage = storage; this.jobs = jobs; this.stores = stores;
    }
    record Request(String jobId, String runnerNodeId) {}

    @PostMapping("/runner/v1/leases/{leaseId}/translation-input")
    ResponseEntity<StreamingResponseBody> input(@PathVariable String leaseId, @RequestBody Request request,
            @RequestHeader("X-Elmos-Lease-Token") String token) throws Exception {
        String tokenHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
        if (!storage.leaseOwnsJob(leaseId, request.runnerNodeId(), request.jobId(), tokenHash)) {
            return ResponseEntity.status(403).build();
        }
        String tenant = storage.organizationForLease(leaseId).orElseThrow();
        var job = jobs.find(tenant, request.jobId()).orElseThrow();
        if (job.businessLine() != ExecutionJobPort.BusinessLine.TRANSLATION
                || !job.jobKind().equals(TranslationExecutionPreparation.KIND)) return ResponseEntity.notFound().build();
        Map<String, Object> payload = jobs.requestPayload(tenant, request.jobId()).orElseThrow();
        if (!(payload.get("input") instanceof Map<?, ?> object)
                || !(object.get("sha256") instanceof String digest) || !digest.matches("[0-9a-f]{64}")
                || !(object.get("byteSize") instanceof Number size) || size.longValue() < 1 || size.longValue() > 96L * 1024 * 1024
                || !storage.executionInputAvailable(tenant, request.jobId(), String.valueOf(object.get("bindingId")),
                    String.valueOf(object.get("objectId")), digest, size.longValue())) return ResponseEntity.status(409).build();
        var ticket = stores.current().presignDownload(tenant, digest, "input.zip", Duration.ofMinutes(2));
        StreamingResponseBody body = output -> {
            if (!downloads.tryAcquire()) throw new java.io.IOException("TRANSLATION_INPUT_CAPACITY_EXCEEDED");
            boolean admitted = activeLeases.add(leaseId);
            try {
                if (!admitted) throw new java.io.IOException("TRANSLATION_INPUT_LEASE_CAPACITY_EXCEEDED");
                if (!storage.leaseOwnsJob(leaseId, request.runnerNodeId(), request.jobId(), tokenHash)) throw new java.io.IOException("TRANSLATION_INPUT_LEASE_LOST");
                var response = http.send(
                        HttpRequest.newBuilder(ticket.downloadUrl()).timeout(Duration.ofSeconds(60)).GET().build(),
                        HttpResponse.BodyHandlers.ofInputStream());
                try (var input = response.body()) {
                    if (response.statusCode() != 200) throw new java.io.IOException("TRANSLATION_INPUT_OBJECT_UNAVAILABLE");
                    var deadline = DEADLINES.schedule(() -> closeBody(input), 60, java.util.concurrent.TimeUnit.SECONDS);
                    try {
                        byte[] buffer = new byte[64 * 1024]; long observed = 0; int n;
                        long lastLeaseCheck = System.nanoTime();
                        while ((n = input.read(buffer)) != -1) {
                            observed += n;
                            if (observed > size.longValue()) throw new java.io.IOException("TRANSLATION_INPUT_SIZE_MISMATCH");
                            if (System.nanoTime() - lastLeaseCheck > 1_000_000_000L) {
                                if (!storage.leaseOwnsJob(leaseId, request.runnerNodeId(), request.jobId(), tokenHash))
                                    throw new java.io.IOException("TRANSLATION_INPUT_LEASE_LOST");
                                lastLeaseCheck = System.nanoTime();
                            }
                            output.write(buffer, 0, n);
                        }
                        if (observed != size.longValue()) throw new java.io.IOException("TRANSLATION_INPUT_SIZE_MISMATCH");
                    } finally { deadline.cancel(false); }
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt(); throw new java.io.IOException("TRANSLATION_INPUT_INTERRUPTED");
            } finally {
                if (admitted) activeLeases.remove(leaseId);
                downloads.release();
            }
        };
        return ResponseEntity.ok().contentLength(size.longValue())
                .contentType(org.springframework.http.MediaType.parseMediaType("application/zip")).body(body);
    }
    private static void closeBody(java.io.InputStream input) {
        try { input.close(); } catch (java.io.IOException ignored) { /* stream task reports failure */ }
    }
}
