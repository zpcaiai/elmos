package io.elmos.securitycompliance;

import io.elmos.engine.api.EngineApi;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class SecurityComplianceEngineController {
    private final SecurityComplianceEngineService engine;
    public SecurityComplianceEngineController(SecurityComplianceEngineService engine) { this.engine = engine; }

    @GetMapping("/capabilities") public EngineApi.Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/scan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse scan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.scan(request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse plan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.plan(request); }
    @PostMapping("/execute-step") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse execute(@Valid @RequestBody EngineApi.ExecuteStepRequest request) { return engine.executeStep(request); }
    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse validate(@Valid @RequestBody EngineApi.JobRequest request) { return engine.validate(request); }
    @PostMapping("/authorize")
    public SecurityModels.AuthorizationResult authorize(@Valid @RequestBody SecurityModels.AuthorizationRequest request) { return engine.authorize(request); }
    @GetMapping("/jobs/{jobId}")
    public EngineApi.JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel")
    public EngineApi.JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "SECURITY_REQUEST_REJECTED", "message", "The security engine request was rejected by its contract.", "retryable", false);
    }
}
