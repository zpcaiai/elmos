package io.elmos.mainframe;

import io.elmos.engine.api.EngineApi;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class MainframeEngineController {
    private final MainframeEngineService engine;
    public MainframeEngineController(MainframeEngineService engine) { this.engine = engine; }

    @GetMapping("/capabilities") public EngineApi.Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse discover(@Valid @RequestBody EngineApi.JobRequest request) { return engine.discover(request); }
    @PostMapping("/analyze") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse analyze(@Valid @RequestBody EngineApi.JobRequest request) { return engine.analyze(request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse plan(@Valid @RequestBody EngineApi.JobRequest request) { return engine.plan(request); }
    @PostMapping("/transform") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse transform(@Valid @RequestBody EngineApi.JobRequest request) { return engine.transform(request); }
    @PostMapping("/execute") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse execute(@Valid @RequestBody EngineApi.ExecuteStepRequest request) { return engine.execute(request); }
    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED)
    public EngineApi.JobResponse validate(@Valid @RequestBody EngineApi.JobRequest request) { return engine.validate(request); }
    @PostMapping("/rules/approve") public MainframeModels.RuleApprovalDecision approveRule(@RequestBody MainframeModels.RuleApprovalRequest request) { return engine.approveRule(request); }
    @GetMapping("/jobs/{jobId}") public EngineApi.JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel") public EngineApi.JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "MAINFRAME_REQUEST_REJECTED", "message", "The mainframe engine request was rejected by its contract.", "retryable", false);
    }
}
