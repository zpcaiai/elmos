package io.elmos.commercial;

import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

/**
 * Prices finished jobs and resolves their holds.
 *
 * <h2>Why the pricing lives here and not in the trigger</h2>
 *
 * <p>The trigger that enqueues settlement work is deliberately trivial: it
 * asserts a hold exists and writes an outbox row. Everything judgemental --
 * what a partial run costs, whether a failure is the caller's fault, how a
 * cancellation mid-run is treated -- is policy that will change, and policy
 * that changes belongs where it can be read, tested and argued about, not in
 * plpgsql inside a BEFORE UPDATE.
 *
 * <h2>The direction this fails in</h2>
 *
 * <p>Every branch below either charges for measured work or releases. Nothing
 * charges the full hold "to be safe". If this service stops running entirely,
 * holds expire by TTL and the money goes back to the tenant -- we under-collect.
 * That is the deliberate choice: over-collecting from a customer because our
 * settler was down is a refund conversation and a trust problem; under-
 * collecting is a number on a dashboard.
 */
public final class WalletSettlementService {

    /** The actor recorded on ledger entries this service writes. */
    public static final String SETTLER_ACTOR = "system:wallet-settler";

    private final WalletSettlementPort settlements;

    public WalletSettlementService(WalletSettlementPort settlements) {
        this.settlements = Objects.requireNonNull(settlements, "settlements");
    }

    /** What one pass did. Zero of everything is the healthy steady state. */
    public record Pass(int resolved, int failed) {}

    public Pass runOnce(int batchSize, int leaseSeconds) {
        List<WalletSettlementPort.Claim> claims = settlements.claim(batchSize, leaseSeconds);
        int resolved = 0;
        int failed = 0;
        for (WalletSettlementPort.Claim claim : claims) {
            try {
                Decision decision = decide(claim);
                settlements.resolve(claim.outboxId(), decision.amountMinor(),
                        decision.resolutionCode(), SETTLER_ACTOR);
                resolved++;
            } catch (RuntimeException failure) {
                // The lease is released and the row stays unresolved, so the next
                // pass retries it. It is never resolved-with-a-guess: a hold that
                // nobody could price must stay visible, and the TTL is the backstop.
                settlements.fail(claim.outboxId(), errorCode(failure));
                failed++;
            }
        }
        return new Pass(resolved, failed);
    }

    /** The amount to charge and the code that explains it. */
    public record Decision(BigDecimal amountMinor, String resolutionCode) {
        public static Decision release(String code) {
            return new Decision(BigDecimal.ZERO, code);
        }
    }

    Decision decide(WalletSettlementPort.Claim claim) {
        WalletSettlementPort.JobFacts facts =
                settlements.facts(claim.organizationId(), claim.jobId());
        if (facts == null) {
            // The hold names a job that is not there. Releasing is the only
            // defensible move: we cannot price what we cannot see, and holding
            // the money hostage to a missing row helps nobody.
            return Decision.release("JOB_NOT_FOUND");
        }

        return switch (facts.status()) {
            case "SUCCEEDED", "PARTIAL" -> charge(facts, "SETTLED_" + facts.status());

            // Platform fault. The tenant did not get what they asked for, and the
            // reason it failed is ours unless someone has explicitly said
            // otherwise by putting the code in wallet_chargeable_failure_codes.
            case "FAILED" -> facts.chargeableFailure()
                    ? minimumOnly(facts, "SETTLED_FAILED_CHARGEABLE")
                    : Decision.release("FAILED_NOT_CHARGED");

            // A cancellation before the runner started cost nothing to run.
            // After it started, the work was really done and is charged for --
            // otherwise cancelling at the 99th second is a free run.
            case "CANCELLED" -> facts.elapsedSeconds() <= 0
                    ? Decision.release("CANCELLED_BEFORE_START")
                    : charge(facts, "SETTLED_CANCELLED");

            // We lost the runner. That is our failure however far it got.
            case "LOST" -> Decision.release("LOST_NOT_CHARGED");

            default -> throw new IllegalStateException(
                    "ELMOS_WALLET_SETTLEMENT_UNEXPECTED_STATUS:" + facts.status());
        };
    }

    private Decision charge(WalletSettlementPort.JobFacts facts, String code) {
        WalletSettlementPort.Quote quote = settlements.quote(
                facts.businessLine(), facts.jobKind(), facts.budgetWallSeconds());

        BigDecimal measured = switch (quote.unit()) {
            case "WALL_SECOND" -> quote.unitPriceMinor()
                    .multiply(BigDecimal.valueOf(Math.max(0, facts.elapsedSeconds())));
            // A job that ran at all costs at least the minimum, whatever the unit.
            // TOKEN pricing needs a usage feed this service does not have yet, so
            // it deliberately degrades to the floor rather than inventing a number.
            case "TOKEN", "JOB" -> quote.minChargeMinor();
            default -> throw new IllegalStateException(
                    "ELMOS_WALLET_SETTLEMENT_UNKNOWN_UNIT:" + quote.unit());
        };

        BigDecimal amount = measured.max(quote.minChargeMinor());
        // The hold is the ceiling. The database clamps this too; doing it here as
        // well means the number in the resolution code matches the number charged,
        // instead of the log claiming one figure and the ledger recording another.
        return new Decision(amount.min(quote.reserveMinor()), code);
    }

    private Decision minimumOnly(WalletSettlementPort.JobFacts facts, String code) {
        WalletSettlementPort.Quote quote = settlements.quote(
                facts.businessLine(), facts.jobKind(), facts.budgetWallSeconds());
        return new Decision(quote.minChargeMinor().min(quote.reserveMinor()), code);
    }

    private static String errorCode(RuntimeException failure) {
        String message = failure.getMessage();
        if (message != null && message.startsWith("ELMOS_")) {
            int colon = message.indexOf(':');
            return colon < 0 ? message : message.substring(0, colon);
        }
        return "SETTLEMENT_ERROR";
    }
}
