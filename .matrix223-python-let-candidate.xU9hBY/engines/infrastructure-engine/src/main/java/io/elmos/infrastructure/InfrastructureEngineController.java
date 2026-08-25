package io.elmos.infrastructure;

import io.elmos.engine.api.EngineApi;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class InfrastructureEngineController {
    private final InfrastructureEngineService engine;

    public InfrastructureEngineController(InfrastructureEngineService engine) { this.engine = engine; }

    @GetMapping("/capabilities") public EngineApi.Capabilities capabilities() { return engine.capabilities(); }

    @PostMapping("/scan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse scan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.scan(request); }

    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse plan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.plan(request); }

    @PostMapping("/execute-step") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse execute(@Valid @RequestBody EngineApi.ExecuteStepRequest request) { return engine.executeStep(request); }

    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse validate(@Valid @RequestBody EngineApi.JobRequest request) { return engine.validate(request); }

    @GetMapping("/jobs/{jobId}")
    public EngineApi.JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }

    @PostMapping("/jobs/{jobId}/cancel")
    public EngineApi.JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }

    @ExceptionHandler(EngineApi.JobNotFoundException.class) @ResponseStatus(HttpStatus.NOT_FOUND)
    Map<String, Object> notFound(EngineApi.JobNotFoundException error) { return Map.of("errorCode", "ENGINE_JOB_NOT_FOUND", "message", "The requested engine job was not found.", "retryable", false); }

    @ExceptionHandler({EngineApi.JobConflictException.class, EngineApi.IdempotencyConflictException.class}) @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, Object> conflict(RuntimeException error) { return Map.of("errorCode", "ENGINE_JOB_CONFLICT", "message", "The engine job conflicts with its terminal or idempotent state.", "retryable", false); }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "INFRASTRUCTURE_REQUEST_REJECTED", "message", "The infrastructure engine request was rejected by its contract.", "retryable", false);
    }
}
