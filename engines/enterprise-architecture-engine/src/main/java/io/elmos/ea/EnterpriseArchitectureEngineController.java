package io.elmos.ea;

import io.elmos.engine.api.EngineApi.*;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public final class EnterpriseArchitectureEngineController {
    private final EvidenceBoundDomainEngine engine;
    public EnterpriseArchitectureEngineController(EvidenceBoundDomainEngine engine) { this.engine = engine; }
    @GetMapping("/capabilities") public Capabilities capabilities() { return engine.capabilities(); }
    @PostMapping("/discover") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse discover(@Valid @RequestBody JobRequest request) { return engine.discover(request); }
    @PostMapping("/assess") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse assess(@Valid @RequestBody JobRequest request) { return engine.evaluate("assess", request); }
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse plan(@Valid @RequestBody JobRequest request) { return engine.plan(request); }
    @PostMapping("/evaluate") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse evaluate(@Valid @RequestBody JobRequest request) { return engine.evaluate("evaluate", request); }
    @PostMapping("/decisions") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse decisions(@Valid @RequestBody ExecuteStepRequest request) { return engine.execute("decisions", request); }
    @PostMapping("/conformance") @ResponseStatus(HttpStatus.ACCEPTED) public JobResponse conformance(@Valid @RequestBody JobRequest request) { return engine.evaluate("conformance", request); }
    @GetMapping("/jobs/{jobId}") public JobResponse job(@RequestParam String organizationId, @PathVariable String jobId) { return engine.job(organizationId, jobId); }
    @PostMapping("/jobs/{jobId}/cancel") public JobResponse cancel(@RequestParam String organizationId, @PathVariable String jobId) { return engine.cancel(organizationId, jobId); }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(IllegalArgumentException e) { return Map.of("errorCode", "EA_REQUEST_REJECTED", "message", e.getMessage(), "retryable", false); }
}
