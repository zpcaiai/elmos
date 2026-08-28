package io.elmos.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class TaskFinopsRecoveryCampaignTest {
    private static final TaskFinopsPolicy.CheckpointIdentity IDENTITY =
            new TaskFinopsPolicy.CheckpointIdentity(
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "rev-1",
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    null,
                    "schema-v1");

    @Test
    void plansEveryBoundaryAndKeepsLeaseAmbiguityManual() {
        TaskFinopsRecoveryCampaign.CampaignPlan plan =
                TaskFinopsRecoveryCampaign.plan("cp-1", IDENTITY);

        assertEquals(TaskFinopsRecoveryCampaign.FailureBoundary.values().length,
                plan.boundaries().size());
        assertTrue(plan.boundaries().stream().anyMatch(item ->
                item.faultPoint().boundary()
                        == TaskFinopsRecoveryCampaign.FailureBoundary.LEASE_EXPIRED
                        && item.decision() == TaskFinopsPolicy.RecoveryDecision.MANUAL_RECOVERY));
        assertEquals("NOT_RUN", plan.runtimeEvidence());
    }

    @Test
    void incompatibleCheckpointAlwaysForksInsteadOfOverwriting() {
        TaskFinopsPolicy.CheckpointIdentity incompatible =
                new TaskFinopsPolicy.CheckpointIdentity(
                        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                        "rev-2",
                        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        null,
                        "schema-v1");
        TaskFinopsRecoveryCampaign.RecoveryPlan result =
                TaskFinopsRecoveryCampaign.evaluate(
                        new TaskFinopsRecoveryCampaign.FaultPoint(
                                "cp-1", TaskFinopsRecoveryCampaign.FailureBoundary.AFTER_CHECKPOINT,
                                1, 1),
                        IDENTITY, incompatible,
                        TaskFinopsPolicy.ErrorClass.TRANSIENT, false);

        assertEquals(TaskFinopsPolicy.RecoveryDecision.FORK_RUN, result.decision());
        assertEquals("CHECKPOINT_COMPATIBILITY_MISMATCH", result.reason());
    }
}
