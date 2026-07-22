package io.elmos.integrations;

import io.elmos.application.ModernizationEnginePort;
import io.elmos.engine.api.EngineApi;
import org.springframework.web.client.RestClient;

public final class HttpModernizationEngineAdapter implements ModernizationEnginePort {
    private final RestClient client;
    public HttpModernizationEngineAdapter(String baseUrl) { this.client=RestClient.builder().baseUrl(baseUrl).build(); }
    @Override public EngineApi.Capabilities capabilities(){return client.get().uri("/engine/v1/capabilities").retrieve().body(EngineApi.Capabilities.class);}
    @Override public EngineApi.JobResponse scan(EngineApi.JobRequest request){return client.post().uri("/engine/v1/scan").body(request).retrieve().body(EngineApi.JobResponse.class);}
    @Override public EngineApi.JobResponse plan(EngineApi.JobRequest request){return client.post().uri("/engine/v1/plan").body(request).retrieve().body(EngineApi.JobResponse.class);}
    @Override public EngineApi.JobResponse executeStep(EngineApi.ExecuteStepRequest request){return client.post().uri("/engine/v1/execute-step").body(request).retrieve().body(EngineApi.JobResponse.class);}
    @Override public EngineApi.JobResponse validate(EngineApi.JobRequest request){return client.post().uri("/engine/v1/validate").body(request).retrieve().body(EngineApi.JobResponse.class);}
    @Override public EngineApi.JobResponse job(String organizationId,String jobId){return client.get().uri(uri->uri.path("/engine/v1/jobs/{id}").queryParam("organizationId",organizationId).build(jobId)).retrieve().body(EngineApi.JobResponse.class);}
    @Override public EngineApi.JobResponse cancel(String organizationId,String jobId){return client.post().uri(uri->uri.path("/engine/v1/jobs/{id}/cancel").queryParam("organizationId",organizationId).build(jobId)).retrieve().body(EngineApi.JobResponse.class);}
}
