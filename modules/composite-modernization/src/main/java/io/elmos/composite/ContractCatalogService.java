package io.elmos.composite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.composite.CompositeModels.*;

public final class ContractCatalogService {
    public enum ContractType {
        HTTP_OPENAPI, GRPC_PROTOBUF, SOAP_WSDL, ASYNCAPI, JSON_SCHEMA, AVRO,
        PROTOBUF_MESSAGE, DATABASE_SCHEMA, FILE_SCHEMA, MODEL_SIGNATURE, CUSTOM_BINARY
    }
    public enum ContractStrength { AUTHORITATIVE, VERIFIED, INFERRED, OBSERVED, CANDIDATE, UNKNOWN }
    public enum Compatibility { BACKWARD, FORWARD, FULL, BREAKING, UNKNOWN }

    public record ContractIdentity(String organizationId, String domain, ContractType type,
                                   String name, int majorVersion) {
        public ContractIdentity {
            require(organizationId, "organizationId"); require(domain, "domain");
            Objects.requireNonNull(type, "type"); require(name, "name");
            if (majorVersion < 1) throw new IllegalArgumentException("majorVersion must be positive");
        }
        public String permanentId() {
            return organizationId + ":" + domain + ":" + type + ":" + name + ":v" + majorVersion;
        }
    }

    public record ContractVersion(
            String versionId, ContractIdentity identity, String semanticVersion, String producerId,
            ContractStrength strength, String artifactHash, Instant effectiveFrom,
            Map<String,String> fields, Set<String> requiredFields, Map<String,Set<String>> enumValues,
            Map<String,String> formats, List<String> evidenceRefs) {
        public ContractVersion {
            require(versionId, "versionId"); Objects.requireNonNull(identity, "identity");
            require(semanticVersion, "semanticVersion"); require(producerId, "producerId");
            Objects.requireNonNull(strength, "strength"); require(artifactHash, "artifactHash");
            Objects.requireNonNull(effectiveFrom, "effectiveFrom"); fields = immutable(fields);
            requiredFields = immutable(requiredFields);
            enumValues = enumValues == null ? Map.of() : enumValues.entrySet().stream().collect(
                    java.util.stream.Collectors.toUnmodifiableMap(Map.Entry::getKey, entry -> Set.copyOf(entry.getValue())));
            formats = immutable(formats); evidenceRefs = immutable(evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("contract version requires evidence");
        }
    }

    public record Consumer(String consumerId, Language language, boolean connectedRepository,
                           boolean external, String currentVersion, String targetVersion,
                           List<String> evidenceRefs) {
        public Consumer {
            require(consumerId, "consumerId"); Objects.requireNonNull(language, "language");
            require(currentVersion, "currentVersion"); require(targetVersion, "targetVersion");
            evidenceRefs = immutable(evidenceRefs);
        }
    }

    public record MatrixEntry(String contractId, String producerId, String consumerId,
                              Language consumerLanguage, String currentVersion, String targetVersion,
                              Compatibility compatibility, List<String> findings,
                              List<String> evidenceRefs) {}
    public record CatalogDecision(List<MatrixEntry> matrix, Compatibility overall,
                                  List<String> blockers, boolean destructiveChangeAllowed) {}

    public CatalogDecision evaluate(ContractVersion current, ContractVersion target,
                                    List<Consumer> consumers, boolean destructiveChangeRequested,
                                    long observedOldVersionUsage) {
        if (!current.identity().permanentId().equals(target.identity().permanentId())) {
            throw new IllegalArgumentException("contract identity cannot change between versions");
        }
        List<String> findings = compare(current, target);
        Compatibility base = compatibility(current, findings);
        List<Consumer> sortedConsumers = immutable(consumers).stream()
                .sorted(Comparator.comparing(Consumer::consumerId)).toList();
        List<MatrixEntry> matrix = sortedConsumers.stream().map(consumer -> new MatrixEntry(
                current.identity().permanentId(), target.producerId(), consumer.consumerId(), consumer.language(),
                consumer.currentVersion(), consumer.targetVersion(),
                consumer.evidenceRefs().isEmpty() ? Compatibility.UNKNOWN : base,
                consumer.evidenceRefs().isEmpty()
                        ? append(findings, "CONSUMER_COMPATIBILITY_EVIDENCE_MISSING") : findings,
                consumer.evidenceRefs())).toList();
        LinkedHashSet<String> blockers = new LinkedHashSet<>();
        if (base == Compatibility.BREAKING) blockers.add("CONTRACT_BREAKING");
        if (base == Compatibility.UNKNOWN) blockers.add("CONTRACT_COMPATIBILITY_UNKNOWN");
        if (matrix.stream().anyMatch(entry -> entry.compatibility() == Compatibility.UNKNOWN)) {
            blockers.add("CONSUMER_MATRIX_INCOMPLETE");
        }
        if (sortedConsumers.stream().anyMatch(consumer -> consumer.external() || !consumer.connectedRepository())) {
            blockers.add("UNKNOWN_CONSUMER_BLOCKER");
        }
        if (observedOldVersionUsage > 0) blockers.add("OLD_CONTRACT_USAGE_PRESENT");
        boolean allowed = !destructiveChangeRequested || blockers.isEmpty();
        return new CatalogDecision(matrix, base, List.copyOf(blockers), allowed);
    }

    private List<String> compare(ContractVersion current, ContractVersion target) {
        LinkedHashSet<String> findings = new LinkedHashSet<>();
        if (current.strength() == ContractStrength.INFERRED || current.strength() == ContractStrength.CANDIDATE
                || current.strength() == ContractStrength.UNKNOWN) findings.add("CONTRACT_NOT_AUTHORITATIVE");
        for (String field : current.fields().keySet()) {
            if (!target.fields().containsKey(field)) findings.add("FIELD_REMOVED:" + field);
        }
        for (String field : target.requiredFields()) {
            if (!current.requiredFields().contains(field)) {
                findings.add("REQUIRED_FIELD_ADDED:" + field);
            }
        }
        if (current.identity().type() == ContractType.GRPC_PROTOBUF
                || current.identity().type() == ContractType.PROTOBUF_MESSAGE) {
            current.fields().forEach((field, descriptor) -> {
                String targetDescriptor = target.fields().get(field);
                if (targetDescriptor != null && !fieldNumber(descriptor).equals(fieldNumber(targetDescriptor))) {
                    findings.add("PROTOBUF_WIRE_FIELD_NUMBER_CHANGED:" + field);
                }
                if (targetDescriptor != null && !descriptor.equals(targetDescriptor)) {
                    findings.add("PROTOBUF_WIRE_OR_TYPE_CHANGED:" + field);
                }
            });
        }
        current.enumValues().forEach((field, values) -> {
            Set<String> targetValues = target.enumValues().getOrDefault(field, Set.of());
            if (!targetValues.containsAll(values)) findings.add("ENUM_VALUE_REMOVED:" + field);
        });
        current.formats().forEach((field, format) -> {
            if (target.formats().containsKey(field) && !format.equals(target.formats().get(field))) {
                findings.add("FORMAT_CHANGED:" + field);
            }
        });
        return List.copyOf(findings);
    }

    private Compatibility compatibility(ContractVersion current, List<String> findings) {
        if (findings.contains("CONTRACT_NOT_AUTHORITATIVE")) return Compatibility.UNKNOWN;
        if (findings.stream().anyMatch(value -> value.startsWith("FIELD_REMOVED")
                || value.startsWith("REQUIRED_FIELD_ADDED") || value.startsWith("PROTOBUF_WIRE")
                || value.startsWith("ENUM_VALUE_REMOVED") || value.startsWith("FORMAT_CHANGED"))) {
            return Compatibility.BREAKING;
        }
        return Compatibility.FULL;
    }

    private String fieldNumber(String descriptor) {
        int separator = descriptor.indexOf(':');
        return separator < 0 ? descriptor : descriptor.substring(0, separator);
    }

    private List<String> append(List<String> values, String value) {
        ArrayList<String> result = new ArrayList<>(values); result.add(value); return List.copyOf(result);
    }
}
