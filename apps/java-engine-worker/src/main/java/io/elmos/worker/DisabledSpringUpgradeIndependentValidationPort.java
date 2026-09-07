package io.elmos.worker;

import java.nio.file.Path;

import static io.elmos.worker.SpringUpgradeModels.*;

final class DisabledSpringUpgradeIndependentValidationPort implements SpringUpgradeIndependentValidationPort {
    private final String reason;

    DisabledSpringUpgradeIndependentValidationPort(String reason) {
        this.reason = reason;
    }

    @Override
    public IndependentValidationResult validate(
            ExecutionResult result,
            Path runRoot,
            SpringUpgradeExecutionPort.Control control
    ) {
        throw new BlockedException("INDEPENDENT_VALIDATOR_NOT_CONFIGURED", reason);
    }

    @Override public boolean configured() { return false; }
    @Override public String configurationReason() { return reason; }
}
