package io.elmos.infrastructure;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.infrastructure.InfrastructureModels.*;

public final class ProviderRunnerRegistry {
    private final Map<RunnerType, RunnerProfile> profiles;

    public ProviderRunnerRegistry() {
        var values = new EnumMap<RunnerType, RunnerProfile>(RunnerType.class);
        values.put(RunnerType.INFRASTRUCTURE_DISCOVERY, profile(RunnerType.INFRASTRUCTURE_DISCOVERY,
                List.of("SSH", "WINRM", "VM_API", "HYPERVISOR_API", "CLOUD_API", "CMDB", "SNMP", "MIDDLEWARE_CLI"), Set.of()));
        values.put(RunnerType.VM_IMAGE_BUILDER, profile(RunnerType.VM_IMAGE_BUILDER,
                List.of("PACKER_COMPATIBLE", "LINUX_IMAGE_BUILDER", "WINDOWS_IMAGE_BUILDER"), Set.of(ChangeKind.CREATE)));
        values.put(RunnerType.CONTAINER_BUILD, profile(RunnerType.CONTAINER_BUILD,
                List.of("ROOTLESS_BUILDKIT", "OCI", "SBOM", "SIGNATURE", "VULNERABILITY_SCAN"), Set.of(ChangeKind.CREATE)));
        values.put(RunnerType.KUBERNETES_VALIDATION, profile(RunnerType.KUBERNETES_VALIDATION,
                List.of("EPHEMERAL_CLUSTER", "HELM", "KUSTOMIZE", "GATEWAY_API", "POLICY_ENGINE"), Set.of(ChangeKind.CREATE, ChangeKind.UPDATE)));
        values.put(RunnerType.SERVERLESS_VALIDATION, profile(RunnerType.SERVERLESS_VALIDATION,
                List.of("FUNCTION_EMULATOR", "KNATIVE", "EVENT_SOURCE", "COLD_START_TEST"), Set.of(ChangeKind.CREATE, ChangeKind.UPDATE)));
        values.put(RunnerType.MULTICLOUD_TEST, profile(RunnerType.MULTICLOUD_TEST,
                List.of("PROVIDER_SANDBOX", "PRIVATE_CLOUD", "CONNECTIVITY_TEST", "RESTORE_TEST"), Set.of(ChangeKind.CREATE, ChangeKind.UPDATE, ChangeKind.DELETE)));
        profiles = Map.copyOf(values);
    }

    public Map<RunnerType, RunnerProfile> all() { return profiles; }

    private RunnerProfile profile(RunnerType type, List<String> tools, Set<ChangeKind> changes) {
        return new RunnerProfile(type, tools,
                Set.of("READ_INVENTORY", "READ_METRICS", "READ_CONFIGURATION", "READ_COST", "READ_LOG_METADATA"),
                changes, true, RunnerStatus.NOT_CONFIGURED);
    }
}
