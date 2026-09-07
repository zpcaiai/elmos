package io.elmos.worker;

import java.nio.file.Path;

import static io.elmos.worker.SpringUpgradeModels.*;

interface SpringUpgradeIndependentValidationPort {
    IndependentValidationResult validate(ExecutionResult result, Path runRoot, SpringUpgradeExecutionPort.Control control);
    boolean configured();
    String configurationReason();
}
