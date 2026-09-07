package io.elmos.testquality;

import io.elmos.engine.api.EngineApi;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class TestQualityEngineController {
    private final TestQualityEngineService engine;
    public TestQualityEngineController(TestQualityEngineService engine) { this.engine = engine; }

    @GetMapping("/capabilities") public EngineApi.Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse discover(@Valid @RequestBody EngineApi.JobRequest request) { return engine.discover(request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse plan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.plan(request); }
    @PostMapping("/generate") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse generate(@Valid @RequestBody EngineApi.JobRequest request) { return engine.generate(request); }
    @PostMapping("/execute") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse execute(@Valid @RequestBody EngineApi.ExecuteStepRequest request) { return engine.execute(request); }
    @PostMapping("/evaluate") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse evaluate(@Valid @RequestBody EngineApi.JobRequest request) { return engine.evaluate(request); }
    @PostMapping("/ai-candidates/promote")
    public QualityModels.PromotionDecision promote(@RequestBody QualityModels.PromotionRequest request) { return engine.promote(request); }
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
        return Map.of("errorCode", "TEST_QUALITY_REQUEST_REJECTED", "message", "The test quality engine request was rejected by its contract.", "retryable", false);
    }
}
