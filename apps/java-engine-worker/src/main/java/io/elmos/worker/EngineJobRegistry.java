package io.elmos.worker;

import io.elmos.engine.api.EngineApi;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

final class EngineJobRegistry {
    private record TenantJob(String organizationId, EngineApi.JobResponse response) {}
    private record IdempotencyEntry(String jobId, String requestFingerprint) {}
    private final Map<String,TenantJob> jobs=new ConcurrentHashMap<>();
    private final Map<String,IdempotencyEntry> idempotency=new ConcurrentHashMap<>();

    synchronized EngineApi.JobResponse unavailable(String organizationId, String key, String operation,
                                                    Object request, EngineApi.ErrorCode errorCode,
                                                    String reasonCode, String message, String suggestedAction) {
        var scope=organizationId+"|"+operation+"|"+key;
        var fingerprint = fingerprint(operation, request);
        var existing = idempotency.get(scope);
        if (existing != null) {
            if (!existing.requestFingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException(key);
            }
            return jobs.get(existing.jobId()).response();
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
    EngineApi.JobResponse get(String organizationId,String id){var value=jobs.get(id);if(value==null||!value.organizationId().equals(organizationId))throw new JobNotFoundException(id);return value.response();}
    EngineApi.JobResponse cancel(String organizationId,String id){
        var current=get(organizationId,id);
        if (current.status()==EngineApi.JobStatus.SUCCEEDED || current.status()==EngineApi.JobStatus.FAILED
                || current.status()==EngineApi.JobStatus.CANCELLED) throw new JobConflictException(id);
        var cancelled=new EngineApi.JobResponse(current.schemaVersion(),id,EngineApi.JobStatus.CANCELLED,
                current.evidenceRefs(),current.result(),current.error());
        jobs.put(id,new TenantJob(organizationId,cancelled));
        return cancelled;
    }

    private String fingerprint(String operation, Object request) {
        try {
            var digest=MessageDigest.getInstance("SHA-256");
            return java.util.HexFormat.of().formatHex(digest.digest((operation+"\n"+request).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) { throw new IllegalStateException("SHA-256 unavailable", error); }
    }
    static final class JobNotFoundException extends RuntimeException { JobNotFoundException(String id){super("job not found: "+id);} }
    static final class IdempotencyConflictException extends RuntimeException { IdempotencyConflictException(String key){super("idempotency key was already used with different input: "+key);} }
    static final class JobConflictException extends RuntimeException { JobConflictException(String id){super("job is already terminal: "+id);} }
}
