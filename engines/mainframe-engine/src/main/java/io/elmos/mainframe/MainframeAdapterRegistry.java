package io.elmos.mainframe;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.mainframe.MainframeModels.*;

public final class MainframeAdapterRegistry {
    private final List<Adapter> adapters = List.of(
            adapter("zosmf", "z/OSMF REST", Set.of(RunnerType.DISCOVERY, RunnerType.BUILD, RunnerType.TEST), Set.of("READ_DATASET_METADATA", "READ_APPROVED_SOURCE", "READ_JOB_STATUS", "READ_SPOOL")),
            adapter("scm", "Mainframe SCM", Set.of(RunnerType.DISCOVERY, RunnerType.BUILD), Set.of("READ_APPROVED_SOURCE", "READ_COPYLIB")),
            adapter("application-discovery", "Application Discovery", Set.of(RunnerType.DISCOVERY), Set.of("READ_CATALOG_METADATA", "READ_RUNTIME_METADATA")),
            adapter("cics", "CICS", Set.of(RunnerType.DISCOVERY, RunnerType.TEST), Set.of("READ_CICS_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("ims", "IMS", Set.of(RunnerType.DISCOVERY, RunnerType.TEST), Set.of("READ_IMS_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("db2", "Db2 for z/OS", Set.of(RunnerType.DISCOVERY, RunnerType.TEST), Set.of("READ_DB2_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("cdc", "CDC", Set.of(RunnerType.DISCOVERY, RunnerType.PARALLEL_COMPARATOR), Set.of("READ_CDC_METADATA", "READ_APPROVED_CHANGE_STREAM")),
            adapter("scheduler", "Enterprise Scheduler", Set.of(RunnerType.DISCOVERY), Set.of("READ_SCHEDULER_METADATA", "READ_JOB_STATUS")),
            adapter("watsonx", "watsonx Code Assistant for Z", Set.of(RunnerType.DISTRIBUTED_ANALYSIS), Set.of("READ_APPROVED_SOURCE", "CREATE_CANDIDATE_ONLY")),
            adapter("test-accelerator", "IBM Test Accelerator for Z", Set.of(RunnerType.TEST), Set.of("EXECUTE_APPROVED_TEST", "READ_TEST_RESULT"))
    );

    public List<Adapter> all() { return adapters; }
    public Map<String, String> statusSummary() {
        return adapters.stream().collect(java.util.stream.Collectors.toUnmodifiableMap(Adapter::id, a -> a.status().name()));
    }
    public boolean anyReady(RunnerType type) { return adapters.stream().anyMatch(a -> a.status() == AdapterStatus.READY && a.runnerTypes().contains(type)); }

    private static Adapter adapter(String id, String product, Set<RunnerType> runners, Set<String> permissions) {
        return new Adapter(id, product, "UNCONFIGURED", AdapterStatus.NOT_CONFIGURED, runners, permissions, "ALLOWLIST_REQUIRED", false);
    }
}
