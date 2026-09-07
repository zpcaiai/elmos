package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

import java.util.*;

public final class RepairPolicyEngine {
    private static final Set<String> MUTATING_SCM = Set.of("git push", "git merge", "git commit", "gh pr merge", "glab mr merge");

    public PatchReview review(RepairTask task, AgentPatch patch) {
        if (!task.taskId().equals(patch.taskId())) throw new SecurityException("patch is not bound to repair task");
        List<String> findings = new ArrayList<>();
        if (patch.changedFiles().size() > task.scope().maximumFiles() || patch.changedLines() > task.scope().maximumChangedLines())
            findings.add("PATCH_LIMIT_EXCEEDED");
        if (patch.changedFiles().stream().anyMatch(path -> task.scope().allowedPathPrefixes().stream().noneMatch(path::startsWith)))
            findings.add("PATCH_OUTSIDE_ALLOWED_SCOPE");
        if (patch.changedFiles().stream().anyMatch(path -> task.scope().deniedPathPrefixes().stream().anyMatch(path::startsWith)))
            findings.add("PATCH_DENIED_PATH_CHANGED");
        if (patch.requestedCommands().stream().anyMatch(command -> MUTATING_SCM.stream().anyMatch(command::startsWith)))
            findings.add("SCM_MUTATION_REQUESTED");
        if (patch.requestedCommands().stream().anyMatch(command -> task.scope().allowedCommands().stream().noneMatch(command::startsWith)))
            findings.add("COMMAND_NOT_ALLOWLISTED");
        if (patch.testsChanged() && !task.scope().allowTestChanges()) findings.add("TEST_CHANGE_FORBIDDEN");
        if (patch.buildConfigurationChanged() && !task.scope().allowBuildConfigurationChanges()) findings.add("BUILD_CONFIGURATION_CHANGE_FORBIDDEN");
        if (patch.filesDeleted()) findings.add("FILE_DELETION_REQUIRES_REVIEW");
        if (patch.baseTreeHash().equals(patch.resultTreeHash())) findings.add("PATCH_PRODUCED_NO_TREE_CHANGE");
        boolean manual = task.risk().ordinal() >= Risk.HIGH.ordinal() || patch.testsChanged()
                || patch.buildConfigurationChanged() || patch.filesDeleted();
        return new PatchReview(findings.isEmpty(), manual, findings,
                task.requiredValidations().stream().filter(ValidationRequirement::independent).map(ValidationRequirement::validator).toList());
    }

    public LoopDecision next(RepairTask task, List<AttemptSnapshot> attempts, VerificationResult verification,
                             long remainingBudgetMicros, List<String> eligibleProviders) {
        int nextAttempt = attempts.size() + 1;
        List<String> evidence = verification == null ? List.of() : verification.evidenceRefs();
        if (verification != null && verification.passed()) return new LoopDecision(LoopAction.STOP_SUCCESS,
                "INDEPENDENT_VALIDATION_PASSED", nextAttempt, null, evidence);
        if (remainingBudgetMicros <= 0) return new LoopDecision(LoopAction.STOP_BUDGET, "REPAIR_BUDGET_EXHAUSTED", nextAttempt, null, evidence);
        if (attempts.size() >= task.maximumAttempts()) return new LoopDecision(LoopAction.ESCALATE_HUMAN, "MAXIMUM_ATTEMPTS_REACHED", nextAttempt, null, evidence);
        if (oscillating(attempts)) return new LoopDecision(LoopAction.STOP_OSCILLATION, "REPAIR_TREE_OSCILLATION_DETECTED", nextAttempt, null, evidence);
        if (attempts.size() >= 2) {
            AttemptSnapshot last = attempts.getLast(), prior = attempts.get(attempts.size() - 2);
            if (last.validationScore() <= prior.validationScore() && Objects.equals(last.afterFingerprint(), prior.afterFingerprint())) {
                String alternative = eligibleProviders.stream().filter(provider -> !provider.equals(last.providerId())).findFirst().orElse(null);
                return alternative == null
                        ? new LoopDecision(LoopAction.ESCALATE_HUMAN, "NO_MEASURABLE_PROGRESS", nextAttempt, null, evidence)
                        : new LoopDecision(LoopAction.SWITCH_PROVIDER, "NO_MEASURABLE_PROGRESS_SWITCH_PROVIDER", nextAttempt, alternative, evidence);
            }
        }
        String provider = attempts.isEmpty() ? eligibleProviders.stream().findFirst().orElse(null) : attempts.getLast().providerId();
        if (provider == null) return new LoopDecision(LoopAction.ESCALATE_HUMAN, "NO_ELIGIBLE_PROVIDER", nextAttempt, null, evidence);
        return new LoopDecision(LoopAction.RETRY_SAME_PROVIDER, "BOUNDED_REPAIR_RETRY", nextAttempt, provider, evidence);
    }

    public EscalationPackage escalate(RepairTask task, String reason, List<AttemptSnapshot> attempts,
                                      List<String> patchRefs, List<String> validationRefs, long consumedCostMicros) {
        String id = "escalation-" + FailureNormalizer.hash(task.taskId() + "\n" + reason + "\n" + attempts).substring(0, 24);
        return new EscalationPackage(id, task.taskId(), reason,
                attempts.stream().map(AttemptSnapshot::afterFingerprint).filter(Objects::nonNull).distinct().toList(),
                attempts.stream().map(AttemptSnapshot::providerId).distinct().toList(), patchRefs, validationRefs,
                consumedCostMicros, List.of("approve-repair-scope", "choose-next-action", "accept-or-reject-residual-risk"));
    }

    private static boolean oscillating(List<AttemptSnapshot> attempts) {
        Map<String,Integer> first = new HashMap<>();
        for (int index = 0; index < attempts.size(); index++) {
            String hash = attempts.get(index).resultTreeHash();
            Integer seen = first.putIfAbsent(hash, index);
            if (seen != null && index - seen > 1) return true;
        }
        return false;
    }
}
