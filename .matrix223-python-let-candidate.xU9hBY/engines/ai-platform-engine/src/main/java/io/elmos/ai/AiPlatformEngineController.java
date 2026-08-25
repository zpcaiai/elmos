package io.elmos.ai;

import io.elmos.engine.api.EngineApi.*;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class AiPlatformEngineController {
    private final EvidenceBoundDomainEngine engine;
    public AiPlatformEngineController(EvidenceBoundDomainEngine engine) { this.engine = engine; }
    @GetMapping("/capabilities") public Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse discover(@Valid @RequestBody JobRequest request) { return engine.discover(request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse plan(@Valid @RequestBody JobRequest request) { return engine.plan(request); }
    @PostMapping("/train") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse train(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("train", request); }
    @PostMapping("/evaluate") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse evaluate(@Valid @RequestBody JobRequest request) { return engine.evaluate("evaluate", request); }
    @PostMapping("/deploy") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse deploy(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("deploy", request); }
    @PostMapping("/monitor") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse monitor(@Valid @RequestBody JobRequest request) { return engine.evaluate("monitor", request); }
    @GetMapping("/jobs/{jobId}") public JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel") public JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }
    @ExceptionHandler(JobNotFoundException.class) @ResponseStatus(HttpStatus.NOT_FOUND) Map<String,Object> notFound(JobNotFoundException e) { return Map.of("errorCode", "ENGINE_JOB_NOT_FOUND", "message", "The requested engine job was not found.", "retryable", false); }
    @ExceptionHandler({JobConflictException.class, IdempotencyConflictException.class}) @ResponseStatus(HttpStatus.CONFLICT) Map<String,Object> conflict(RuntimeException e) { return Map.of("errorCode", "ENGINE_JOB_CONFLICT", "message", "The engine job conflicts with its terminal or idempotent state.", "retryable", false); }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(IllegalArgumentException e) { return Map.of("errorCode", "AI_REQUEST_REJECTED", "message", "The AI platform request was rejected by its contract.", "retryable", false); }
}
