package io.elmos.worker;

import java.nio.file.Path;
import java.util.List;

import static io.elmos.worker.SpringUpgradeModels.*;

interface SpringUpgradeExecutionPort {
    interface Control {
        void stage(Stage stage, String message);
        void log(String line);
        void process(Process process);
        boolean cancelled();
    }

    ExecutionResult execute(StartRequest request, Path runRoot, Control control);
    RuntimeHandle start(ExecutionResult result, StartRequest request, Path runRoot, Control control);
    void stop(RuntimeHandle handle, Control control);
    default List<String> runtimeLogs(RuntimeHandle handle) { return List.of(); }
    boolean configured();
    String configurationReason();
    default boolean runtimeConfigured() { return false; }
    default boolean experimentalRoutesEnabled() { return false; }
    default String runtimeConfigurationReason() {
        return "An isolated per-run application Runner is not configured.";
    }
}
