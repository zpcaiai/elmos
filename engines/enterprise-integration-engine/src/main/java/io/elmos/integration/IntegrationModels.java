package io.elmos.integration;

import java.util.Objects;
import java.util.Set;

public final class IntegrationModels {
    private IntegrationModels() {}

    public enum AdapterStatus { NOT_CONFIGURED, READY, LICENSE_BLOCKED }
    public enum RunnerType { DISCOVERY, BROKER_VALIDATION, API_GATEWAY_VALIDATION, B2B_TEST, WORKFLOW, REPLAY, CUTOVER }
    public enum MessageKind { COMMAND, DOMAIN_EVENT, INTEGRATION_EVENT, NOTIFICATION, QUERY, REPLY, CONTROL_MESSAGE, FILE_TRANSFER }
    public enum DeliverySemantics { AT_MOST_ONCE, AT_LEAST_ONCE, BROKER_TRANSACTIONAL,
        EXACTLY_ONCE_WITHIN_PLATFORM, EFFECTIVELY_ONCE_WITH_IDEMPOTENCY, END_TO_END_VERIFIED, UNKNOWN }
    public enum TargetProfile { KEEP_AND_HARDEN, UPGRADE_PLATFORM, MANAGED_EQUIVALENT, API_ENABLE,
        EVENT_ENABLE, BROKER_REPLATFORM, FLOW_DECOMPOSE, WORKFLOW_EXTRACT, DOMAIN_LOGIC_EXTRACT,
        PARTNER_REPLATFORM, REPLACE_PLATFORM, RETIRE }
    public enum MigrationState { INTEGRATION_DISCOVERY, CONTRACT_BASELINING, RUNTIME_CORRELATING,
        TARGET_PLANNING, SCHEMA_STABILIZING, COMPATIBILITY_BUILDING, FLOW_MIGRATING,
        CONTRACT_VALIDATING, PARALLEL_RUNNING, PRODUCER_CUTOVER, CONSUMER_CUTOVER,
        PARTNER_CUTOVER, STABILITY_HOLD, LEGACY_READ_ONLY, DECOMMISSION_READY, DECOMMISSIONED }
    public enum EquivalenceStatus { EXACT, SEMANTICALLY_EQUIVALENT, EXPECTED_DIFFERENCE, REGRESSION, INCONCLUSIVE }

    public record Adapter(String id, String product, String version, AdapterStatus status,
                          Set<RunnerType> runnerTypes, Set<String> permissions,
                          String networkPolicy, boolean productionCapable) {
        public Adapter {
            require(id, "id"); require(product, "product"); require(version, "version");
            Objects.requireNonNull(status); runnerTypes = Set.copyOf(runnerTypes);
            permissions = Set.copyOf(permissions); require(networkPolicy, "networkPolicy");
            if (!"ALLOWLIST_REQUIRED".equals(networkPolicy)) throw new IllegalArgumentException("integration egress must be allowlisted");
            if (permissions.stream().anyMatch(IntegrationModels::prohibited)) throw new IllegalArgumentException("prohibited integration adapter permission");
        }
    }

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean prohibited(String permission) {
        return Set.of("PURGE_PRODUCTION_QUEUE", "RESET_PRODUCTION_OFFSET", "DELETE_TOPIC",
                "MODIFY_PARTNER_CERTIFICATE", "REPLAY_PRODUCTION_MESSAGE", "CREATE_PUBLIC_GATEWAY_ROUTE",
                "SWITCH_PRODUCER", "ACCEPT_MESSAGE_LOSS").contains(permission);
    }
}
