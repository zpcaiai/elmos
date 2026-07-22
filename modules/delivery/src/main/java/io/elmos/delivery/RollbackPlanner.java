package io.elmos.delivery;

import io.elmos.delivery.DeliveryModels.*;

import java.util.ArrayList;
import java.util.List;

public final class RollbackPlanner {
    public RollbackPlan plan(String migrationId, List<Change> changes, Integer suppliedRtoMinutes,
                             Integer suppliedRpoMinutes, DrillStatus drillStatus) {
        List<RollbackStep> steps = new ArrayList<>(); List<String> limitations = new ArrayList<>(); List<String> blockers = new ArrayList<>(); int order = 10;
        for (Change change : changes) {
            String domain = change.domain().toLowerCase();
            if (domain.equals("code") || domain.equals("deployment"))
                steps.add(step(order += 10, RollbackActionType.REVERT_CODE, "scm revert --commit <delivery-commit>", "delivery commit exists", "build and tests pass", true));
            else if (domain.equals("database")) {
                if (change.reversible() && !change.destructive())
                    steps.add(step(order += 10, RollbackActionType.ROLLBACK_DATABASE, "db migrate --target <previous-version>", "backup verified", "schema fingerprint restored", true));
                else {
                    steps.add(step(order += 10, RollbackActionType.RESTORE_DATABASE, "db restore --backup <verified-backup>", "verified backup and maintenance window", "row counts and checksums verified", true));
                    steps.add(step(order += 10, RollbackActionType.ROLL_FORWARD, "db migrate --apply <compensating-migration>", "restore is unsafe or RPO cannot be met", "compatibility suite passes", true));
                    limitations.add("Destructive database change cannot be undone by code revert alone");
                }
            } else if (domain.equals("cache")) {
                RollbackActionType action = change.backwardCompatible() ? RollbackActionType.INVALIDATE_CACHE : RollbackActionType.DUAL_READ_CACHE;
                steps.add(step(order += 10, action, action == RollbackActionType.INVALIDATE_CACHE ? "cache invalidate --namespace <migration>" : "cache enable-dual-read --old <v1> --new <v2>",
                        "cache version identified", "old and new clients read successfully", false));
            } else if (domain.equals("message"))
                steps.add(step(order += 10, change.reversible() ? RollbackActionType.REPLAY_MESSAGES : RollbackActionType.COMPENSATE_MESSAGES,
                        "message compensate --manifest <evidence-ref>", "consumer offsets captured", "consumer contract probes pass", true));
            else if (domain.equals("traffic"))
                steps.add(step(order += 10, RollbackActionType.SHIFT_TRAFFIC, "traffic shift --to <previous-deployment>", "previous deployment healthy", "error rate returns below trigger", true));
        }
        if (steps.isEmpty()) blockers.add("ROLLBACK_STEPS_MISSING");
        if (suppliedRtoMinutes == null) blockers.add("RTO_NOT_SUPPLIED");
        if (suppliedRpoMinutes == null) blockers.add("RPO_NOT_SUPPLIED");
        if (drillStatus == DrillStatus.FAILED) blockers.add("ROLLBACK_DRILL_FAILED");
        String seed = migrationId + "\n" + changes + "\n" + suppliedRtoMinutes + "\n" + suppliedRpoMinutes;
        return new RollbackPlan("1.0", "rollback-" + DeliveryReadModel.hash(seed).substring(0, 24), migrationId,
                List.of("validation-critical-failure", "post-deploy-error-budget-breach", "data-integrity-alert"),
                steps, suppliedRtoMinutes, suppliedRpoMinutes, drillStatus, limitations, blockers.isEmpty(), blockers);
    }
    private static RollbackStep step(int order, RollbackActionType action, String command, String precondition, String verification, boolean approval) {
        return new RollbackStep(order, action, command, precondition, verification, approval);
    }
}
