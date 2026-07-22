package io.elmos.suite;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.suite.SuiteModels.*;

public final class SuiteAdapterRegistry {
    private final List<Adapter> adapters = List.of(
            adapter("sap", "SAP ECC and S/4HANA", Set.of(RunnerType.DISCOVERY, RunnerType.SAP), Set.of("READ_CONFIGURATION", "READ_ABAP_METADATA", "READ_USAGE_METADATA", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("oracle-ebs", "Oracle E-Business Suite", Set.of(RunnerType.DISCOVERY, RunnerType.ORACLE), Set.of("READ_FND_METADATA", "READ_FORMS_REPORTS_WORKFLOW", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("oracle-fusion", "Oracle Fusion Cloud Applications", Set.of(RunnerType.DISCOVERY, RunnerType.ORACLE), Set.of("READ_CONFIGURATION", "READ_EXTENSION_METADATA", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("dynamics", "Microsoft Dynamics 365", Set.of(RunnerType.DISCOVERY, RunnerType.DYNAMICS), Set.of("READ_SOLUTION_METADATA", "READ_SECURITY_METADATA", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("dataverse", "Microsoft Dataverse and Power Platform", Set.of(RunnerType.DISCOVERY, RunnerType.DYNAMICS), Set.of("READ_SOLUTION_LAYERS", "READ_FLOW_METADATA", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("salesforce", "Salesforce", Set.of(RunnerType.DISCOVERY, RunnerType.SALESFORCE), Set.of("READ_ORG_METADATA", "READ_PACKAGE_METADATA", "EXECUTE_APPROVED_SANDBOX_TEST")),
            adapter("process-mining", "Process Mining", Set.of(RunnerType.DISCOVERY, RunnerType.PROCESS_VALIDATION), Set.of("READ_APPROVED_EVENT_LOG", "READ_PROCESS_VARIANTS")),
            adapter("mdm", "Master Data Governance", Set.of(RunnerType.MASTER_DATA, RunnerType.DATA_MIGRATION), Set.of("READ_MASTER_DATA_METADATA", "EXECUTE_APPROVED_SYNTHETIC_MATCH")),
            adapter("archive", "Suite Archive", Set.of(RunnerType.DATA_MIGRATION, RunnerType.CUTOVER), Set.of("READ_ARCHIVE_METADATA", "EXECUTE_APPROVED_ARCHIVE_TEST"))
    );

    public List<Adapter> all() { return adapters; }
    public Map<String, String> statusSummary() {
        return adapters.stream().collect(java.util.stream.Collectors.toUnmodifiableMap(Adapter::id, a -> a.status().name()));
    }
    public boolean anyReady(RunnerType type) {
        return adapters.stream().anyMatch(a -> a.status() == AdapterStatus.READY && a.runnerTypes().contains(type));
    }
    private static Adapter adapter(String id, String product, Set<RunnerType> runners, Set<String> permissions) {
        return new Adapter(id, product, "UNCONFIGURED", AdapterStatus.NOT_CONFIGURED, runners, permissions, "ALLOWLIST_REQUIRED", false);
    }
}
