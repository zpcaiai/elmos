package io.elmos.recipe;

import io.elmos.recipe.RecipeModels.*;

import java.util.*;

public final class RecipeOutcomeEvaluator {
    private static final Set<String> REQUIRED_TABLES = Set.of(
            "org.openrewrite.table.SourcesFileResults",
            "org.openrewrite.table.SourcesFileErrors",
            "org.openrewrite.table.RecipeRunStats");

    public RecipeRun evaluate(ExecutionManifest manifest, RunEvidence evidence) {
        if (!manifest.manifestHash().equals(evidence.manifestHash())) throw new SecurityException("run evidence does not match execution manifest");
        List<String> findings = new ArrayList<>(); RunStatus status;
        if (evidence.workspaceBoundaryViolation()) { status = RunStatus.POLICY_BLOCKED; findings.add("OPENREWRITE_UNEXPECTED_FILE_CHANGE"); }
        else if (evidence.timedOut()) { status = RunStatus.TIMED_OUT; findings.add("OPENREWRITE_TIMEOUT"); }
        else if (evidence.resourceExceeded()) { status = RunStatus.RESOURCE_EXCEEDED; findings.add("OPENREWRITE_OUT_OF_MEMORY"); }
        else if (!evidence.parseErrors().isEmpty()) { status = RunStatus.PARSE_FAILED; findings.add("OPENREWRITE_PARSE_FAILED"); }
        else if (!evidence.recipeErrors().isEmpty()) { status = RunStatus.RECIPE_FAILED; findings.add("OPENREWRITE_EXECUTION_EXCEPTION"); }
        else if (evidence.fileResults().isEmpty()) { status = RunStatus.NO_CHANGES; findings.add("OPENREWRITE_NO_EXPECTED_CHANGE"); }
        else { status = RunStatus.SUCCEEDED_WITH_CHANGES; }
        if (!evidence.dataTables().containsAll(REQUIRED_TABLES)) {
            findings.add("OPENREWRITE_DATA_TABLE_MISSING");
            status = RunStatus.POLICY_BLOCKED;
        }
        IdempotenceResult idempotence = evaluateIdempotence(evidence.treeHashes(), evidence.secondRunChanged(),
                evidence.fileResults().size(), manifest.maxCycles());
        if (idempotence.status() != IdempotenceStatus.IDEMPOTENT
                && idempotence.status() != IdempotenceStatus.FIXPOINT_REACHED_AFTER_MULTIPLE_CYCLES) {
            findings.add("RECIPE_" + idempotence.status()); status = RunStatus.POLICY_BLOCKED;
        }
        String runId = "recipe-run-" + RecipeGovernanceService.digest(manifest.manifestHash() + "\n" + evidence.treeHashes()).substring(0, 24);
        return new RecipeRun("1.0", runId, manifest.manifestId(), manifest.manifestHash(), status,
                evidence.cycleCount(), evidence.fileResults().size(), evidence.parseErrors().size(), evidence.recipeErrors().size(),
                idempotence, findings, List.of("evidence://recipe-run/" + runId));
    }

    public IdempotenceResult evaluateIdempotence(List<String> treeHashes, boolean secondRunChanged,
                                                  int secondRunChangedFiles, int maxCycles) {
        if (treeHashes.isEmpty()) return new IdempotenceResult(IdempotenceStatus.INCONCLUSIVE, treeHashes, secondRunChangedFiles, "TREE_HASH_EVIDENCE_MISSING");
        if (treeHashes.size() > maxCycles + 1) return new IdempotenceResult(IdempotenceStatus.MAX_CYCLES_EXCEEDED, treeHashes, secondRunChangedFiles, "MAX_CYCLES_EXCEEDED");
        Map<String,Integer> firstIndex = new HashMap<>();
        for (int index = 0; index < treeHashes.size(); index++) {
            Integer seen = firstIndex.putIfAbsent(treeHashes.get(index), index);
            if (seen != null && index - seen > 1)
                return new IdempotenceResult(IdempotenceStatus.OSCILLATING, treeHashes, secondRunChangedFiles, "TREE_HASH_OSCILLATION_DETECTED");
        }
        if (!secondRunChanged) return new IdempotenceResult(treeHashes.size() > 2
                ? IdempotenceStatus.FIXPOINT_REACHED_AFTER_MULTIPLE_CYCLES : IdempotenceStatus.IDEMPOTENT,
                treeHashes, 0, "SECOND_FRESH_PROCESS_PRODUCED_NO_DIFF");
        return new IdempotenceResult(IdempotenceStatus.NON_IDEMPOTENT, treeHashes, secondRunChangedFiles, "SECOND_FRESH_PROCESS_PRODUCED_CHANGES");
    }

    public PromotionDecision promotion(RegressionEvidence evidence) {
        List<String> blocked = new ArrayList<>();
        if (!evidence.descriptorPassed()) blocked.add("DESCRIPTOR_INVALID");
        if (!evidence.unitTestsPassed()) blocked.add("UNIT_TESTS_FAILED");
        if (!evidence.negativeTestsPassed()) blocked.add("NEGATIVE_TESTS_FAILED");
        if (!evidence.compilePassed()) blocked.add("COMPILE_REGRESSION");
        if (evidence.idempotence() != IdempotenceStatus.IDEMPOTENT
                && evidence.idempotence() != IdempotenceStatus.FIXPOINT_REACHED_AFTER_MULTIPLE_CYCLES) blocked.add("IDEMPOTENCE_FAILED");
        if (!evidence.compositionPassed()) blocked.add("COMPOSITION_REGRESSION");
        if (!evidence.performanceWithinBudget()) blocked.add("PERFORMANCE_REGRESSION");
        if (!evidence.licenseAllowed()) blocked.add("LICENSE_BLOCKED");
        if (!evidence.artifactSigned()) blocked.add("ARTIFACT_UNSIGNED");
        if (!evidence.sbomPresent()) blocked.add("SBOM_MISSING");
        if (evidence.humanReviewers() < 1) blocked.add("HUMAN_REVIEW_MISSING");
        if (!evidence.rollbackDefined()) blocked.add("ROLLBACK_UNDEFINED");
        if (blocked.isEmpty()) return new PromotionDecision(RegressionStatus.PASS, PromotionStatus.APPROVED, true, List.of());
        RegressionStatus regression = blocked.contains("LICENSE_BLOCKED") ? RegressionStatus.FAIL_LICENSE
                : blocked.contains("IDEMPOTENCE_FAILED") ? RegressionStatus.FAIL_IDEMPOTENCE
                : blocked.contains("COMPILE_REGRESSION") ? RegressionStatus.FAIL_COMPILE : RegressionStatus.FAIL_FUNCTIONAL;
        return new PromotionDecision(regression, PromotionStatus.BLOCKED, false, blocked);
    }
}
