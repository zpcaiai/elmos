package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.recipe.*;
import io.elmos.recipe.RecipeModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/engine/v1/recipes")
final class RecipeGovernanceController {
    record SelectRequest(Catalog catalog, List<CommercialGrant> grants, SelectionRequest selection) {}
    record ManifestRequest(Catalog catalog, List<CommercialGrant> grants, Selection selection,
                           String sourceSnapshotId, String sourceCommit, String targetProfileId,
                           String compatibilitySnapshotId, String rewriteBomVersion, String pluginVersion,
                           Map<String,Map<String,Object>> options, RuntimeConfiguration runtime,
                           int maxCycles, int timeoutSeconds, String policyHash, Instant createdAt) {}
    record EvaluateRunRequest(ExecutionManifest manifest, RunEvidence evidence) {}
    record SegmentRequest(String migrationStepId, String patchArtifactPrefix, List<FileResult> changes, PatchPolicy policy) {}

    private final ObjectMapper json;
    RecipeGovernanceController(ObjectMapper json) { this.json = json; }

    @PostMapping("/selections") Selection select(@RequestBody SelectRequest request) {
        return new RecipeGovernanceService(request.catalog(), request.grants(), json).select(request.selection());
    }
    @PostMapping("/execution-manifests") ExecutionManifest manifest(@RequestBody ManifestRequest request) {
        return new RecipeGovernanceService(request.catalog(), request.grants(), json).buildManifest(request.selection(),
                request.sourceSnapshotId(), request.sourceCommit(), request.targetProfileId(), request.compatibilitySnapshotId(),
                request.rewriteBomVersion(), request.pluginVersion(), request.options(), request.runtime(), request.maxCycles(),
                request.timeoutSeconds(), request.policyHash(), request.createdAt());
    }
    @PostMapping("/runs/evaluate") RecipeRun evaluate(@RequestBody EvaluateRunRequest request) {
        return new RecipeOutcomeEvaluator().evaluate(request.manifest(), request.evidence());
    }
    @PostMapping("/patch-segments") List<PatchSegment> segment(@RequestBody SegmentRequest request) {
        return new PatchGovernance().segment(request.migrationStepId(), request.patchArtifactPrefix(), request.changes(), request.policy());
    }
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "RECIPE_GOVERNANCE_REJECTED", "message", "The recipe governance request was rejected by its contract.", "retryable", false);
    }
}
