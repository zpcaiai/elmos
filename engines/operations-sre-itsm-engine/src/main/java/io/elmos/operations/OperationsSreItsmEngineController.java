package io.elmos.operations;

import io.elmos.engine.api.EngineApi.*;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class OperationsSreItsmEngineController {
    private final EvidenceBoundDomainEngine engine;
    public OperationsSreItsmEngineController(EvidenceBoundDomainEngine engine) { this.engine = engine; }
    @GetMapping("/capabilities") public Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse discover(@Valid @RequestBody JobRequest request) { return engine.discover(request); }
    @PostMapping("/events") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse events(@Valid @RequestBody JobRequest request) { return engine.evaluate("events", request); }
    @PostMapping("/incidents") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse incidents(@Valid @RequestBody JobRequest request) { return engine.evaluate("incidents", request); }
    @PostMapping("/changes") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse changes(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("changes", request); }
    @PostMapping("/remediate") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse remediate(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("remediate", request); }
    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse validate(@Valid @RequestBody JobRequest request) { return engine.evaluate("validate", request); }
    @GetMapping("/jobs/{jobId}") public JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel") public JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(IllegalArgumentException e) { return Map.of("errorCode", "OPERATIONS_REQUEST_REJECTED", "message", "The operations engine request was rejected by its contract.", "retryable", false); }
}
