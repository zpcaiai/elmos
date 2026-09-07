package io.elmos.domain;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MigrationRunTest {
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-20T12:00:00Z"), ZoneOffset.UTC);
    private final OrganizationId organizationId = OrganizationId.random();
    private final SnapshotId snapshotId = SnapshotId.random();

    @Test
    void completesAuditableHappyPath() {
        var plan = plan();
        plan.approve("reviewer-1", clock);
        var run = run(plan);

        run.prepareRepository();
        run.fingerprint();
        run.baseline();
        run.recordBaseline(true);
        run.planGenerated();
        run.startMigration(plan);
        var step = run.startStep(plan.steps().getFirst());
        run.completeStep(step, EvidenceId.random());
        run.validate();
        run.recordValidation(true);
        run.approveDelivery();
        run.deliver();

        assertEquals(MigrationState.DELIVERED, run.state());
        assertEquals(StepState.SUCCEEDED, step.state());
        assertFalse(run.pullEvents().isEmpty());
    }

    @Test
    void rejectsUnapprovedPlanAndSuccessWithoutEvidence() {
        var plan = plan();
        var run = run(plan);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(true); run.planGenerated();
        assertThrows(DomainException.class, () -> run.startMigration(plan));

        plan.approve("reviewer-1", clock);
        run.startMigration(plan);
        var step = run.startStep(plan.steps().getFirst());
        assertThrows(DomainException.class, () -> run.completeStep(step, null));
    }

    @Test
    void baselineFailureIsExplicitTerminalEvidenceBoundary() {
        var plan = plan();
        var run = run(plan);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(false);
        assertEquals(MigrationState.BASELINE_BROKEN, run.state());
        assertTrue(run.state().terminal());
        assertThrows(DomainException.class, run::planGenerated);
    }

    @Test
    void rejectsCrossTenantPlan() {
        var plan = new MigrationPlan(MigrationPlanId.random(), OrganizationId.random(), snapshotId, 1,
                "java11-spring2", "java21-spring3", List.of(new MigrationPlan.Step("rewrite", "OPENREWRITE", List.of(), false)));
        plan.approve("reviewer", clock);
        var run = new MigrationRun(MigrationRunId.random(), organizationId, snapshotId, plan.id(), plan.version(), clock);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(true); run.planGenerated();
        assertThrows(DomainException.class, () -> run.startMigration(plan));
    }

    @Test
    void enforcesApprovedStepMembershipDependencyOrderAndCompletePlan() {
        var first = new MigrationPlan.Step("rewrite", "OPENREWRITE", List.of(), false);
        var second = new MigrationPlan.Step("compile", "BUILD", List.of("rewrite"), false);
        var plan = new MigrationPlan(MigrationPlanId.random(), organizationId, snapshotId, 1,
                "java11-spring2", "java21-spring3", List.of(first, second));
        plan.approve("reviewer", clock);
        var run = run(plan);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(true); run.planGenerated(); run.startMigration(plan);

        assertThrows(DomainException.class, () -> run.startStep(second));
        assertThrows(DomainException.class, () -> run.startStep(new MigrationPlan.Step("invented", "AGENT", List.of(), false)));
        assertThrows(DomainException.class, run::validate);

        var firstRun = run.startStep(first);
        run.completeStep(firstRun, EvidenceId.random());
        assertThrows(DomainException.class, () -> run.startStep(first));
        assertThrows(DomainException.class, run::validate);

        var secondRun = run.startStep(second);
        run.completeStep(secondRun, EvidenceId.random());
        run.validate();
        assertEquals(MigrationState.VALIDATING, run.state());
    }

    @Test
    void permitsOnlyRetryableStepAttempts() {
        var plan = plan();
        plan.approve("reviewer", clock);
        var run = run(plan);
        run.prepareRepository(); run.fingerprint(); run.baseline(); run.recordBaseline(true); run.planGenerated(); run.startMigration(plan);

        var firstAttempt = run.startStep(plan.steps().getFirst());
        run.failStep(firstAttempt, "TRANSIENT_RUNNER_FAILURE", true);
        var secondAttempt = run.startStep(plan.steps().getFirst());

        assertEquals(2, secondAttempt.attempt());
        run.failStep(secondAttempt, "POLICY_BLOCKED", false);
        assertThrows(DomainException.class, () -> run.startStep(plan.steps().getFirst()));
        assertThrows(DomainException.class, run::validate);
    }

    @Test
    void rejectsCyclicPlans() {
        var first = new MigrationPlan.Step("first", "ENGINE", List.of("second"), false);
        var second = new MigrationPlan.Step("second", "ENGINE", List.of("first"), false);
        assertThrows(IllegalArgumentException.class, () -> new MigrationPlan(
                MigrationPlanId.random(), organizationId, snapshotId, 1,
                "source", "target", List.of(first, second)));
    }

    private MigrationPlan plan() {
        return new MigrationPlan(MigrationPlanId.random(), organizationId, snapshotId, 1,
                "java11-spring2", "java21-spring3", List.of(new MigrationPlan.Step("rewrite", "OPENREWRITE", List.of(), false)));
    }

    private MigrationRun run(MigrationPlan plan) {
        return new MigrationRun(MigrationRunId.random(), organizationId, snapshotId, plan.id(), plan.version(), clock);
    }
}
