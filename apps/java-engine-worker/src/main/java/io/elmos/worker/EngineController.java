package io.elmos.worker;

import io.elmos.engine.api.EngineApi;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
public class EngineController {
    private final EngineJobRegistry jobs=new EngineJobRegistry();

    @GetMapping("/capabilities")
    public EngineApi.Capabilities capabilities(){return new EngineApi.Capabilities("1.0","ELMOS_JAVA","0.1.0",List.of("JAVA"),List.of("8","11","17","21"),List.of("17","21","25"),List.of("MAVEN","GRADLE"),List.of(),List.of(),List.of("JAVA8_MAVEN","JAVA11_MAVEN","JAVA17_MAVEN","JAVA21_MAVEN"),List.of("SPRING_BOOT_1","SPRING_BOOT_2","SPRING_BOOT_3"),List.of("org.openrewrite.java.migrate.UpgradeToJava21","org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_5"),List.of("LEGACY_HEALTH_CHECK","MIGRATION_PLAN","COMPILE","UNIT_TEST","API_CONTRACT"),Map.of("isolation","container","networkDefault","DENY_ALL","healthCheck","REAL_STATIC_SCAN","migrationPlanning","REAL_DETERMINISTIC_PLAN","recipeExecution","NOT_CONFIGURED_FAIL_CLOSED"));}
    @PostMapping("/scan") @ResponseStatus(HttpStatus.ACCEPTED) public EngineApi.JobResponse scan(@Valid @RequestBody EngineApi.JobRequest request){return jobs.unavailable(
            request.organizationId(),request.idempotencyKey(),"SCAN",request,EngineApi.ErrorCode.POLICY_BLOCKED,
            "USE_EVIDENCE_BOUND_HEALTH_CHECK_ENDPOINT","The generic scan executor is not configured and no scan was run.",
            "Use /engine/v1/health-checks in a snapshot-bound workspace or configure an approved scanner Runner.");}
    @PostMapping("/plan") @ResponseStatus(HttpStatus.ACCEPTED) public EngineApi.JobResponse plan(@Valid @RequestBody EngineApi.JobRequest request){return jobs.unavailable(
            request.organizationId(),request.idempotencyKey(),"PLAN",request,EngineApi.ErrorCode.POLICY_BLOCKED,
            "USE_EVIDENCE_BOUND_MIGRATION_PLAN_ENDPOINT","The generic plan executor is not configured and no plan was generated.",
            "Use /engine/v1/migration-plans in a snapshot-bound workspace or configure an approved planning Runner.");}
    @PostMapping("/validate") @ResponseStatus(HttpStatus.ACCEPTED) public EngineApi.JobResponse validate(@Valid @RequestBody EngineApi.JobRequest request){return jobs.unavailable(
            request.organizationId(),request.idempotencyKey(),"VALIDATE",request,EngineApi.ErrorCode.VALIDATION_FAILED,
            "INDEPENDENT_VALIDATION_EVIDENCE_REQUIRED","Validation cannot run without baseline and migrated evidence.",
            "Submit evidence to the domain-specific /engine/v1/validation comparison endpoints and aggregate the decision.");}
    @PostMapping("/execute-step") @ResponseStatus(HttpStatus.ACCEPTED) public EngineApi.JobResponse execute(@Valid @RequestBody EngineApi.ExecuteStepRequest request){return jobs.unavailable(
            request.organizationId(),request.idempotencyKey(),"EXECUTE_STEP",request,EngineApi.ErrorCode.WORKSPACE_UNAVAILABLE,
            "APPROVED_WORKSPACE_RUNNER_NOT_CONFIGURED","No approved isolated Workspace Runner is configured; the migration step was not executed.",
            "Provision an approved digest-pinned Runner and bind the request to its lease and immutable snapshot.");}
    @GetMapping("/jobs/{jobId}") public EngineApi.JobResponse job(@PathVariable String jobId,@RequestParam String organizationId){return jobs.get(organizationId,jobId);}
    @PostMapping("/jobs/{jobId}/cancel") public EngineApi.JobResponse cancel(@PathVariable String jobId,@RequestParam String organizationId){return jobs.cancel(organizationId,jobId);}
    @ExceptionHandler(EngineJobRegistry.JobNotFoundException.class) @ResponseStatus(HttpStatus.NOT_FOUND) Map<String,Object> notFound(RuntimeException error){return Map.of("errorCode","INTERNAL_ENGINE_ERROR","message",error.getMessage(),"retryable",false);}
    @ExceptionHandler({EngineJobRegistry.IdempotencyConflictException.class, EngineJobRegistry.JobConflictException.class})
    @ResponseStatus(HttpStatus.CONFLICT) Map<String,Object> conflict(RuntimeException error){return Map.of("errorCode","ENGINE_JOB_CONFLICT","message",error.getMessage(),"retryable",false);}
}
