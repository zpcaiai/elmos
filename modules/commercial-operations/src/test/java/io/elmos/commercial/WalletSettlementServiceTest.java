package io.elmos.commercial;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The settlement policy, which is the part of charging that is a judgement call.
 *
 * <p>All in memory: the arithmetic and the branch choice are what is being
 * tested. That the resulting charge actually moves the balance correctly is a
 * database property and is tested against a real PostgreSQL, not mocked here.
 */
class WalletSettlementServiceTest {

    private static final BigDecimal RESERVE = new BigDecimal("3600");
    private static final BigDecimal MIN_CHARGE = new BigDecimal("50");
    private static final BigDecimal PER_SECOND = BigDecimal.ONE;

    private final FakePort port = new FakePort();
    private final WalletSettlementService service = new WalletSettlementService(port);

    @Test void aSuccessfulJobIsChargedForTheSecondsItActuallyRan() {
        port.facts = facts("SUCCEEDED", null, 400, false);

        var decision = service.decide(aClaim());

        assertEquals(new BigDecimal("400"), decision.amountMinor());
        assertEquals("SETTLED_SUCCEEDED", decision.resolutionCode());
    }

    /**
     * The hold is a ceiling, not an estimate. A job that overran its budget --
     * or a clock that moved -- must not be able to charge past what the user was
     * shown when they pressed submit.
     */
    @Test void aJobCanNeverBeChargedMoreThanWasHeldForIt() {
        port.facts = facts("SUCCEEDED", null, 999_999, false);

        assertEquals(RESERVE, service.decide(aClaim()).amountMinor());
    }

    /** A run measured at almost nothing still costs the floor. */
    @Test void aVeryShortRunStillCostsTheMinimum() {
        port.facts = facts("SUCCEEDED", null, 2, false);

        assertEquals(MIN_CHARGE, service.decide(aClaim()).amountMinor());
    }

    @Test void aPartialResultIsChargedLikeASuccessBecauseTheWorkWasDone() {
        port.facts = facts("PARTIAL", null, 300, false);

        assertEquals(new BigDecimal("300"), service.decide(aClaim()).amountMinor());
    }

    /** The default: our failure, our cost. */
    @Test void anOrdinaryFailureCostsNothing() {
        port.facts = facts("FAILED", "RUNNER_OOM", 120, false);

        var decision = service.decide(aClaim());

        assertEquals(BigDecimal.ZERO, decision.amountMinor());
        assertEquals("FAILED_NOT_CHARGED", decision.resolutionCode());
    }

    /** Only a failure someone explicitly classified as the caller's doing bills. */
    @Test void aFailureExplicitlyClassifiedAsTheCallersCostsTheMinimum() {
        port.facts = facts("FAILED", "SOURCE_REPOSITORY_UNREACHABLE", 120, true);

        var decision = service.decide(aClaim());

        assertEquals(MIN_CHARGE, decision.amountMinor());
        assertEquals("SETTLED_FAILED_CHARGEABLE", decision.resolutionCode());
    }

    @Test void aJobCancelledBeforeItStartedIsFree() {
        port.facts = facts("CANCELLED", null, 0, false);

        var decision = service.decide(aClaim());

        assertEquals(BigDecimal.ZERO, decision.amountMinor());
        assertEquals("CANCELLED_BEFORE_START", decision.resolutionCode());
    }

    /** Otherwise cancelling at the last second is a free run. */
    @Test void aJobCancelledWhileRunningIsChargedForWhatItRan() {
        port.facts = facts("CANCELLED", null, 250, false);

        assertEquals(new BigDecimal("250"), service.decide(aClaim()).amountMinor());
    }

    @Test void aLostRunnerIsOurFaultHoweverFarItGot() {
        port.facts = facts("LOST", "RUNNER_LEASE_LOST", 3000, false);

        var decision = service.decide(aClaim());

        assertEquals(BigDecimal.ZERO, decision.amountMinor());
        assertEquals("LOST_NOT_CHARGED", decision.resolutionCode());
    }

    @Test void aHoldWhoseJobHasVanishedIsReleasedRatherThanGuessedAt() {
        port.facts = null;

        var decision = service.decide(aClaim());

        assertEquals(BigDecimal.ZERO, decision.amountMinor());
        assertEquals("JOB_NOT_FOUND", decision.resolutionCode());
    }

    /**
     * A claim that cannot be priced must stay unresolved. Resolving it with a
     * guess is the one outcome that is worse than leaving it: the guess is
     * silent and permanent, while an unresolved row is visible and the TTL
     * eventually gives the money back.
     */
    @Test void anUnpriceableClaimIsLeftForTheNextPassRatherThanResolvedWithAGuess() {
        port.facts = facts("SOMETHING_NEW", null, 100, false);

        var pass = service.runOnce(10, 120);

        assertEquals(0, pass.resolved());
        assertEquals(1, pass.failed());
        assertTrue(port.resolved.isEmpty(), () -> "resolved anyway: " + port.resolved);
        assertEquals(List.of("ELMOS_WALLET_SETTLEMENT_UNEXPECTED_STATUS"), port.failures);
    }

    /** One bad claim must not stop the rest of the batch. */
    @Test void oneUnpriceableClaimDoesNotBlockTheOthers() {
        port.queue = List.of(aClaim("wsx-good-1"), aClaim("wsx-bad"), aClaim("wsx-good-2"));
        port.factsByJob = Map.of(
                "wsx-good-1", facts("SUCCEEDED", null, 100, false),
                "wsx-bad", facts("SOMETHING_NEW", null, 100, false),
                "wsx-good-2", facts("SUCCEEDED", null, 200, false));

        var pass = service.runOnce(10, 120);

        assertEquals(2, pass.resolved());
        assertEquals(1, pass.failed());
    }

    // ------------------------------------------------------------------

    // 命名为 aClaim 而不是 claim：FakePort 实现了 claim(int, int)，
    // 内部类里同名方法会遮蔽外层的静态 claim()，编译期直接报参数不匹配。
    private static WalletSettlementPort.Claim aClaim() {
        return aClaim("wsx-1");
    }

    private static WalletSettlementPort.Claim aClaim(String outboxId) {
        // jobId 与 outboxId 同名，只是为了让下面的假件按一个键查得到；
        // 真实系统里两者是不同的标识。
        return new WalletSettlementPort.Claim(
                outboxId, "org-1", outboxId, "wres-1", "SUCCEEDED", null, 1);
    }

    private static WalletSettlementPort.JobFacts facts(
            String status, String failureCode, int elapsed, boolean chargeable) {
        return new WalletSettlementPort.JobFacts(
                status, failureCode, "GENERATION", "gen", 3600, elapsed, chargeable);
    }

    private static final class FakePort implements WalletSettlementPort {
        private WalletSettlementPort.JobFacts facts;
        private List<Claim> queue = List.of(aClaim());
        private Map<String, JobFacts> factsByJob = Map.of();
        private final List<String> resolved = new ArrayList<>();
        private final List<String> failures = new ArrayList<>();
        private boolean drained;

        @Override public List<Claim> claim(int limit, int leaseSeconds) {
            if (drained) {
                return List.of();
            }
            drained = true;
            return queue;
        }

        @Override public JobFacts facts(String organizationId, String jobId) {
            return factsByJob.isEmpty() ? facts : factsByJob.get(jobId);
        }

        @Override public Quote quote(String businessLine, String jobKind, int budgetWallSeconds) {
            return new Quote("q", RESERVE, MIN_CHARGE, "WALL_SECOND", PER_SECOND);
        }

        @Override public boolean resolve(String outboxId, BigDecimal amount,
                                         String resolutionCode, String actorId) {
            resolved.add(outboxId + "=" + amount);
            return true;
        }

        @Override public void fail(String outboxId, String errorCode) {
            failures.add(errorCode);
        }
    }
}
