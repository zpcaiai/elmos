package io.elmos.deliveryplatform;

import io.elmos.engine.api.EngineApi.*;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class SoftwareDeliveryPlatformEngineController {
    private final EvidenceBoundDomainEngine engine;
    public SoftwareDeliveryPlatformEngineController(EvidenceBoundDomainEngine engine) { this.engine = engine; }
    @GetMapping("/capabilities") public Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse discover(@Valid @RequestBody JobRequest request) { return engine.discover(request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse plan(@Valid @RequestBody JobRequest request) { return engine.plan(request); }
    @PostMapping("/execute-step") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse executeStep(@Valid @RequestBody ExecuteStepRequest request) { return engine.executeStep(request); }
    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse validate(@Valid @RequestBody JobRequest request) { return engine.evaluate("validate", request); }
    @PostMapping("/self-service") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse selfService(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("self-service", request); }
    @GetMapping("/jobs/{jobId}") public JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel") public JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(IllegalArgumentException e) { return Map.of("errorCode", "PLATFORM_REQUEST_REJECTED", "message", "The software delivery request was rejected by its contract.", "retryable", false); }
}
