package io.elmos.databasedata;

import io.elmos.engine.api.EngineApi.JobResponse;

import java.util.Optional;

interface DatabaseJobStore {
    record IdempotentResult(String fingerprint, JobResponse response) {}

    Optional<JobResponse> job(String organizationId, String jobId);

    Optional<IdempotentResult> idempotent(String scopedKey);

    void save(String organizationId, String jobId, String scopedKey, IdempotentResult result);

    void replaceJob(String organizationId, String jobId, JobResponse response);

    default boolean durable() {
        return false;
    }
}
