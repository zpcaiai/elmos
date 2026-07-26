package io.elmos.worker;

import java.nio.file.Path;

import static io.elmos.worker.SpringUpgradeModels.*;

final class DisabledSpringUpgradeExecutionPort implements SpringUpgradeExecutionPort {
    private final String reason;
    DisabledSpringUpgradeExecutionPort(String reason) { this.reason = reason; }

    @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
        throw new BlockedException("APPROVED_SPRING_UPGRADE_RUNNER_NOT_CONFIGURED", reason);
    }
    @Override public RuntimeHandle start(ExecutionResult result, StartRequest request, Path runRoot, Control control) {
        throw new BlockedException("APPROVED_APPLICATION_RUNNER_NOT_CONFIGURED", reason);
    }
    @Override public void stop(RuntimeHandle handle, Control control) { }
    @Override public boolean configured() { return false; }
    @Override public String configurationReason() { return reason; }
    @Override public String runtimeConfigurationReason() { return reason; }
}
