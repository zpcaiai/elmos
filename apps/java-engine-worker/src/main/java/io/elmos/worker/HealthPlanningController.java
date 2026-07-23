package io.elmos.worker;

import io.elmos.health.HealthModels;
import io.elmos.health.JavaLegacyHealthCheck;
import io.elmos.planning.MigrationPlanner;
import io.elmos.planning.PlanningModels;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/engine/v1")
final class HealthPlanningController {
    record AnalysisRequest(@NotBlank String snapshotId, @NotBlank String relativePath) {}
    private final JavaLegacyHealthCheck health; private final MigrationPlanner planner; private final WorkspacePathResolver paths;
    HealthPlanningController(JavaLegacyHealthCheck health, MigrationPlanner planner, WorkspacePathResolver paths) { this.health = health; this.planner = planner; this.paths = paths; }

    @PostMapping("/health-checks") HealthModels.LegacyHealthReport health(@Valid @RequestBody AnalysisRequest request) {
        return health.scan(new JavaLegacyHealthCheck.Request(request.snapshotId(), paths.resolve(request.relativePath())));
    }
    @PostMapping("/migration-plans") PlanningModels.MigrationPlan plan(@Valid @RequestBody AnalysisRequest request) {
        var report = health.scan(new JavaLegacyHealthCheck.Request(request.snapshotId(), paths.resolve(request.relativePath())));
        return planner.plan(report, PlanningModels.OrganizationPolicy.defaults());
    }
    @ExceptionHandler({IllegalArgumentException.class, SecurityException.class}) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String,Object> badRequest(RuntimeException error) { return Map.of("errorCode", "ENGINE_INPUT_REJECTED", "message", "The health planning request was rejected by its contract.", "retryable", false); }
}
