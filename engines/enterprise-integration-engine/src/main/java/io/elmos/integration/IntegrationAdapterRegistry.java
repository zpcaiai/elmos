package io.elmos.integration;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.integration.IntegrationModels.*;

public final class IntegrationAdapterRegistry {
    private final List<Adapter> adapters = List.of(
            adapter("esb-export", "ESB and SOA Configuration Export", Set.of(RunnerType.DISCOVERY), Set.of("READ_PLATFORM_CONFIG", "READ_ROUTE_METADATA")),
            adapter("ibm-mq", "IBM MQ", Set.of(RunnerType.DISCOVERY, RunnerType.BROKER_VALIDATION), Set.of("READ_QUEUE_METADATA", "READ_DLQ_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("kafka", "Apache Kafka", Set.of(RunnerType.DISCOVERY, RunnerType.BROKER_VALIDATION), Set.of("READ_TOPIC_METADATA", "READ_CONSUMER_OFFSET", "EXECUTE_APPROVED_TEST")),
            adapter("rabbitmq", "RabbitMQ", Set.of(RunnerType.DISCOVERY, RunnerType.BROKER_VALIDATION), Set.of("READ_EXCHANGE_METADATA", "READ_QUEUE_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("schema-registry", "Schema Registry", Set.of(RunnerType.DISCOVERY, RunnerType.BROKER_VALIDATION), Set.of("READ_SCHEMA_METADATA", "CHECK_COMPATIBILITY")),
            adapter("api-gateway", "API Gateway", Set.of(RunnerType.DISCOVERY, RunnerType.API_GATEWAY_VALIDATION), Set.of("READ_ROUTE_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("as2-edi", "AS2 and EDI", Set.of(RunnerType.DISCOVERY, RunnerType.B2B_TEST), Set.of("READ_PARTNER_METADATA", "EXECUTE_APPROVED_PARTNER_TEST")),
            adapter("mft-sftp", "MFT and SFTP", Set.of(RunnerType.DISCOVERY, RunnerType.B2B_TEST), Set.of("READ_TRANSFER_METADATA", "EXECUTE_APPROVED_PARTNER_TEST")),
            adapter("workflow", "BPM and Workflow", Set.of(RunnerType.DISCOVERY, RunnerType.WORKFLOW), Set.of("READ_PROCESS_METADATA", "EXECUTE_APPROVED_TEST")),
            adapter("runtime-observation", "Trace and Runtime Observation", Set.of(RunnerType.DISCOVERY), Set.of("READ_TRACE_METADATA", "READ_LAG_METADATA", "READ_TRANSFER_STATUS")),
            adapter("replay", "Controlled Replay", Set.of(RunnerType.REPLAY), Set.of("READ_APPROVED_MESSAGE_RANGE", "EXECUTE_APPROVED_REPLAY")),
            adapter("bridge", "Compatibility Bridge", Set.of(RunnerType.BROKER_VALIDATION, RunnerType.CUTOVER), Set.of("READ_BRIDGE_STATUS", "EXECUTE_APPROVED_TEST"))
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
