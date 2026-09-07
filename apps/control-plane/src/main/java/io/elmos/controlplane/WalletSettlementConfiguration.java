package io.elmos.controlplane;

import io.elmos.commercial.WalletSettlementPort;
import io.elmos.commercial.WalletSettlementService;
import io.elmos.persistence.JdbcWalletSettlementStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Wires the settlement loop into the control plane.
 *
 * <p>The control plane rather than the commercial API, because settlement is
 * driven by job lifecycle. Everything it reacts to -- terminal transitions, the
 * lease reaper marking a job LOST, an operator cancelling -- happens here. The
 * commercial API never sees a job finish; putting the settler there would mean
 * one service watching another service's state machine over the database.
 *
 * <p>No {@code TransactionTemplate}: every call is a single V74 function that
 * is already atomic on its own, and the settler must not hold one transaction
 * open across a batch. A batch-wide transaction would turn one unpriceable row
 * into a rollback of every settlement that ran before it in the same pass.
 */
@Configuration
class WalletSettlementConfiguration {

    @Bean
    WalletSettlementPort walletSettlementPort(JdbcClient jdbc) {
        return new JdbcWalletSettlementStore(jdbc);
    }

    @Bean
    WalletSettlementService walletSettlementService(WalletSettlementPort walletSettlementPort) {
        return new WalletSettlementService(walletSettlementPort);
    }
}
