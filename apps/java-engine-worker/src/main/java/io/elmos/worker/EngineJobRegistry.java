package io.elmos.worker;

import io.elmos.engine.api.EngineApi;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.LinkedHashMap;

final class EngineJobRegistry {
    private record TenantJob(String organizationId, EngineApi.JobResponse response) {}
    private record IdempotencyEntry(String jobId, String requestFingerprint) {}
    /**
     * Job records exist so a client can read back a response it already
     * received, and idempotency keys so a retry of the same request returns the
     * same job. Both are therefore bounded. Before this cap neither map was ever
     * read from and never written to disk, yet both grew for the lifetime of the
     * worker: one record per rejected request, until the process ran out of
     * heap. A client asking for a record older than the cap gets the same
     * JobNotFound it would get after a worker restart, which it already handles.
     */
    private static final int MAX_RETAINED_JOBS = 10_000;

    private final Map<String,TenantJob> jobs = boundedByInsertion(MAX_RETAINED_JOBS);
    private final Map<String,IdempotencyEntry> idempotency = boundedByInsertion(MAX_RETAINED_JOBS);

    private static <K, V> Map<K, V> boundedByInsertion(int capacity) {
        return new LinkedHashMap<>(16, 0.75f, false) {
            @Override protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
                return size() > capacity;
            }
        };
    }

    synchronized EngineApi.JobResponse unavailable(String organizationId, String key, String operation,
                                                    Object request, EngineApi.ErrorCode errorCode,
                                                    String reasonCode, String message, String suggestedAction) {
        var scope=organizationId+"|"+operation+"|"+key;
        var fingerprint = fingerprint(operation, request);
        var existing = idempotency.get(scope);
        if (existing != null) {
            if (!existing.requestFingerprint().equals(fingerprint)) {
                throw new EngineApi.IdempotencyConflictException(key);
            }
            TenantJob retained = jobs.get(existing.jobId());
            /*
             * The two maps are evicted independently, so an idempotency key can
             * outlive the job it points at. Treat that as an expired key and
             * issue a fresh job rather than dereferencing a record that is gone.
             */
            if (retained != null) return retained.response();
            idempotency.remove(scope);
        }
        var jobId=UUID.randomUUID().toString();
        var error = new EngineApi.EngineError(errorCode, message, false, List.of(), null, null, suggestedAction);
        var response = new EngineApi.JobResponse("1.0", jobId, EngineApi.JobStatus.FAILED, List.of(),
                Map.of("operation", operation, "executed", false, "configured", false,
                        "reasonCode", reasonCode, "customerCodeExecuted", false), error);
        idempotency.put(scope, new IdempotencyEntry(jobId, fingerprint));
        jobs.put(jobId, new TenantJob(organizationId, response));
        return response;
    }
    synchronized EngineApi.JobResponse get(String organizationId,String id){var value=jobs.get(id);if(value==null||!value.organizationId().equals(organizationId))throw new EngineApi.JobNotFoundException(id);return value.response();}
    synchronized EngineApi.JobResponse cancel(String organizationId,String id){
        var current=get(organizationId,id);
        if (EngineApi.isTerminal(current.status())) throw new EngineApi.JobConflictException(id);
        var cancelled=new EngineApi.JobResponse(current.schemaVersion(),id,EngineApi.JobStatus.CANCELLED,
                current.evidenceRefs(),current.result(),current.error());
        jobs.put(id,new TenantJob(organizationId,cancelled));
        return cancelled;
    }

    private String fingerprint(String operation, Object request) {
        try {
            var digest=MessageDigest.getInstance("SHA-256");
            return java.util.HexFormat.of().formatHex(digest.digest((operation+"\n"+EngineApi.idempotencyMaterial(request)).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) { throw new IllegalStateException("SHA-256 unavailable", error); }
    }
}
