package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskFinopsFeatureRolloutTest {
    @Test
    void advancesOneStageAfterSameEnvironmentPrerequisites() {
        var snapshot = snapshot(Map.of(
                key(TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                        TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING),
                state(TaskFinopsFeatureRollout.Stage.SHADOW, 0)));
        var change = change(
                TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                TaskFinopsFeatureRollout.Feature.ACCOUNT_CONCURRENCY_LIMIT,
                TaskFinopsFeatureRollout.Stage.SHADOW,
                0);

        var validation = TaskFinopsFeatureRollout.validate(snapshot, change);
        var updated = TaskFinopsFeatureRollout.apply(snapshot, change);

        assertEquals(TaskFinopsFeatureRollout.Decision.APPLY, validation.decision());
        assertTrue(validation.accepted());
        assertEquals(TaskFinopsFeatureRollout.Stage.SHADOW,
                updated.state(change.environment(), change.feature()).stage());
    }

    @Test
    void rejectsFeatureOrderViolationsAndStageJumps() {
        var empty = snapshot(Map.of());
        var outOfOrder = TaskFinopsFeatureRollout.validate(empty, change(
                TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                TaskFinopsFeatureRollout.Feature.DURABLE_WORKFLOW_START,
                TaskFinopsFeatureRollout.Stage.SHADOW,
                0));
        assertEquals(TaskFinopsFeatureRollout.Decision.REJECT, outOfOrder.decision());
        assertTrue(outOfOrder.violations().stream().allMatch(violation ->
                violation.reasonCode()
                        == TaskFinopsFeatureRollout.ReasonCode.PREREQUISITE_NOT_READY));

        var skipped = TaskFinopsFeatureRollout.validate(empty, change(
                TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING,
                TaskFinopsFeatureRollout.Stage.CANARY,
                10));
        assertTrue(skipped.violations().stream().anyMatch(violation ->
                violation.reasonCode()
                        == TaskFinopsFeatureRollout.ReasonCode.STAGE_ADVANCE_SKIPPED));
    }

    @Test
    void productionCannotOutrunStaging() {
        var snapshot = snapshot(Map.of(
                key(TaskFinopsFeatureRollout.Environment.STAGING,
                        TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING),
                state(TaskFinopsFeatureRollout.Stage.CANARY, 10)));

        var validation = TaskFinopsFeatureRollout.validate(snapshot, change(
                TaskFinopsFeatureRollout.Environment.PRODUCTION,
                TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING,
                TaskFinopsFeatureRollout.Stage.SHADOW,
                0));

        assertEquals(TaskFinopsFeatureRollout.Decision.REJECT, validation.decision());
        assertEquals(TaskFinopsFeatureRollout.ReasonCode.PREVIOUS_ENVIRONMENT_NOT_ON,
                validation.violations().getFirst().reasonCode());
        assertEquals(TaskFinopsFeatureRollout.Environment.STAGING,
                validation.violations().getFirst().relatedEnvironment());
    }

    @Test
    void rollbackRequiresDependentsAndDownstreamEnvironmentsFirst() {
        var snapshot = snapshot(Map.of(
                key(TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                        TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING),
                state(TaskFinopsFeatureRollout.Stage.ON, 100),
                key(TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                        TaskFinopsFeatureRollout.Feature.ACCOUNT_CONCURRENCY_LIMIT),
                state(TaskFinopsFeatureRollout.Stage.ON, 100),
                key(TaskFinopsFeatureRollout.Environment.STAGING,
                        TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING),
                state(TaskFinopsFeatureRollout.Stage.ON, 100)));

        var validation = TaskFinopsFeatureRollout.validate(snapshot, change(
                TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING,
                TaskFinopsFeatureRollout.Stage.OFF,
                0));

        assertEquals(TaskFinopsFeatureRollout.Decision.REJECT, validation.decision());
        assertTrue(validation.violations().stream().anyMatch(violation ->
                violation.reasonCode()
                        == TaskFinopsFeatureRollout.ReasonCode.DEPENDENT_FEATURE_ACTIVE));
        assertTrue(validation.violations().stream().anyMatch(violation ->
                violation.reasonCode()
                        == TaskFinopsFeatureRollout.ReasonCode.DOWNSTREAM_ENVIRONMENT_ACTIVE));
        assertThrows(TaskFinopsFeatureRollout.RolloutRejectedException.class,
                () -> TaskFinopsFeatureRollout.apply(snapshot, change(
                        TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                        TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING,
                        TaskFinopsFeatureRollout.Stage.OFF,
                        0)));
    }

    @Test
    void stateExposureAndIdempotentChangesAreExact() {
        assertThrows(IllegalArgumentException.class, () ->
                state(TaskFinopsFeatureRollout.Stage.CANARY, 0));
        assertThrows(IllegalArgumentException.class, () ->
                state(TaskFinopsFeatureRollout.Stage.ON, 99));
        var state = state(TaskFinopsFeatureRollout.Stage.SHADOW, 0);
        var key = key(TaskFinopsFeatureRollout.Environment.DEVELOPMENT,
                TaskFinopsFeatureRollout.Feature.AUTHENTICATED_ACCOUNT_BINDING);
        var snapshot = snapshot(Map.of(key, state));
        var noChange = change(key.environment(), key.feature(), state.stage(), 0);

        assertEquals(TaskFinopsFeatureRollout.Decision.NO_CHANGE,
                TaskFinopsFeatureRollout.validate(snapshot, noChange).decision());
        assertSame(snapshot, TaskFinopsFeatureRollout.apply(snapshot, noChange));
    }

    private static TaskFinopsFeatureRollout.RolloutSnapshot snapshot(
            Map<TaskFinopsFeatureRollout.FlagKey, TaskFinopsFeatureRollout.FlagState> states
    ) {
        return new TaskFinopsFeatureRollout.RolloutSnapshot(states);
    }

    private static TaskFinopsFeatureRollout.FlagKey key(
            TaskFinopsFeatureRollout.Environment environment,
            TaskFinopsFeatureRollout.Feature feature
    ) {
        return new TaskFinopsFeatureRollout.FlagKey(environment, feature);
    }

    private static TaskFinopsFeatureRollout.FlagState state(
            TaskFinopsFeatureRollout.Stage stage,
            int exposurePercent
    ) {
        return new TaskFinopsFeatureRollout.FlagState(stage, exposurePercent);
    }

    private static TaskFinopsFeatureRollout.Change change(
            TaskFinopsFeatureRollout.Environment environment,
            TaskFinopsFeatureRollout.Feature feature,
            TaskFinopsFeatureRollout.Stage stage,
            int exposurePercent
    ) {
        return new TaskFinopsFeatureRollout.Change(
                environment, feature, state(stage, exposurePercent));
    }
}
