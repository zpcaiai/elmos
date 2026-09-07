package io.elmos.application;

import io.elmos.engine.api.EngineApi;

public interface ModernizationEnginePort {
    EngineApi.Capabilities capabilities();
    EngineApi.JobResponse scan(EngineApi.JobRequest request);
    EngineApi.JobResponse plan(EngineApi.JobRequest request);
    EngineApi.JobResponse executeStep(EngineApi.ExecuteStepRequest request);
    EngineApi.JobResponse validate(EngineApi.JobRequest request);
    EngineApi.JobResponse job(String organizationId, String jobId);
    EngineApi.JobResponse cancel(String organizationId, String jobId);
}
