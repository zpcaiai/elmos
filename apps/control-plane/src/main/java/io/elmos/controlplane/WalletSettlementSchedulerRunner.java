package io.elmos.controlplane;

import io.elmos.commercial.WalletSettlementService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Drains the wallet settlement outbox.
 *
 * <p>No enable flag of its own, on purpose. The flag that matters lives in the
 * database ({@code wallet_enforcement_settings}); while charging is off the
 * outbox stays empty, and a scheduler polling an empty table is cheap. A second
 * flag would mostly be a way for charging to be on while nothing resolves it --
 * holds would then sit until their TTL and quietly release, which looks like the
 * feature working and is not.
 *
 * <p>Failures are logged, never rethrown: a thrown exception here stops the
 * fixed-delay schedule for the life of the process, so one poison row would end
 * settlement entirely. The per-claim failure path already leaves the row for the
 * next pass, and repeated failures are visible as {@code last_error_code} and a
 * rising {@code attempts}.
 */
@Component
final class WalletSettlementSchedulerRunner {
    private static final Logger LOG =
            LoggerFactory.getLogger(WalletSettlementSchedulerRunner.class);

    private final WalletSettlementService settlements;
    private final int batchSize;
    private final int leaseSeconds;

    WalletSettlementSchedulerRunner(
            WalletSettlementService settlements,
            @Value("${elmos.wallet.settlement.batch-size:50}") int batchSize,
            @Value("${elmos.wallet.settlement.lease-seconds:120}") int leaseSeconds
    ) {
        this.settlements = settlements;
        if (batchSize < 1 || batchSize > 500) {
            throw new IllegalStateException("wallet settlement batch size must be 1..500");
        }
        // The lease must outlast one pass over a full batch, or a slow pass will
        // have its own claims stolen by the next one and both will do the work.
        // The resolve is idempotent, so that is not a double charge -- it is just
        // two workers burning time on the same rows.
        if (leaseSeconds < 30 || leaseSeconds > 900) {
            throw new IllegalStateException("wallet settlement lease must be 30..900 seconds");
        }
        this.batchSize = batchSize;
        this.leaseSeconds = leaseSeconds;
    }

    @Scheduled(fixedDelayString = "${elmos.wallet.settlement.interval-ms:15000}")
    void settle() {
        try {
            WalletSettlementService.Pass pass = settlements.runOnce(batchSize, leaseSeconds);
            if (pass.failed() > 0) {
                LOG.warn("Wallet settlement pass had failures: resolved={}, failed={}",
                        pass.resolved(), pass.failed());
            } else if (pass.resolved() > 0) {
                LOG.info("Wallet settlement pass resolved {} holds", pass.resolved());
            }
        } catch (RuntimeException failure) {
            // Swallowed on purpose. See the class comment: rethrowing kills the
            // schedule, and money would then sit held until TTL with no error
            // after this one line.
            LOG.error("Wallet settlement pass aborted; retrying on the next tick", failure);
        }
    }
}
