package io.elmos.databasedata;

import io.elmos.engine.api.EngineApi.JobResponse;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

final class InMemoryDatabaseJobStore implements DatabaseJobStore {
    private final Map<String, JobResponse> jobs = new ConcurrentHashMap<>();
    private final Map<String, IdempotentResult> idempotency = new ConcurrentHashMap<>();

    @Override
    public Optional<JobResponse> job(String organizationId, String jobId) {
        return Optional.ofNullable(jobs.get(organizationId + ":" + jobId));
    }

    @Override
    public Optional<IdempotentResult> idempotent(String scopedKey) {
        return Optional.ofNullable(idempotency.get(scopedKey));
    }

    @Override
    public void save(String organizationId, String jobId, String scopedKey, IdempotentResult result) {
        idempotency.put(scopedKey, result);
        jobs.put(organizationId + ":" + jobId, result.response());
    }

    @Override
    public void replaceJob(String organizationId, String jobId, JobResponse response) {
        jobs.put(organizationId + ":" + jobId, response);
    }
}
