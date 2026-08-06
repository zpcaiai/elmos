package io.elmos.proofloop;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.proofloop.ProofLoopModels.ExecutionClass;

/** Loads the immutable compiled contracts shipped by the Batch 105-108 package. */
public final class SkillContractCatalog {
    public record Contract(
            String id,
            int batch,
            String name,
            List<String> dependencies,
            List<String> inputs,
            List<String> outputs,
            List<String> workflow,
            List<String> tests,
            List<String> evidence,
            List<String> definitionOfDone,
            Map<String, List<String>> implementation,
            String canonicalSha256,
            ExecutionClass executionClass
    ) {
        public Contract {
            ProofLoopModels.identifier(id, "contract.id");
            ProofLoopModels.identifier(name, "contract.name");
            dependencies = List.copyOf(dependencies);
            inputs = List.copyOf(inputs);
            outputs = List.copyOf(outputs);
            workflow = List.copyOf(workflow);
            tests = List.copyOf(tests);
            evidence = List.copyOf(evidence);
            definitionOfDone = List.copyOf(definitionOfDone);
            implementation = Map.copyOf(implementation);
            ProofLoopModels.digest(canonicalSha256, "contract.canonicalSha256");
            ProofLoopModels.required(executionClass, "contract.executionClass");
        }
    }

    private final Map<String, Contract> contracts;

    public SkillContractCatalog() {
        this(new ObjectMapper());
    }

    public SkillContractCatalog(ObjectMapper mapper) {
        Map<String, Contract> loaded = new LinkedHashMap<>();
        for (int batch = 105; batch <= 108; batch++) {
            for (int ordinal = 1; ordinal <= 16; ordinal++) {
                String id = "B" + batch + "-S" + String.format("%02d", ordinal);
                Contract contract = load(mapper, id);
                if (!contract.id().equals(id)) throw new IllegalStateException("contract identity mismatch for " + id);
                loaded.put(id, contract);
            }
        }
        if (loaded.size() != 64) throw new IllegalStateException("Batch 105-108 requires exactly 64 contracts");
        validateDependencies(loaded);
        this.contracts = Collections.unmodifiableMap(loaded);
    }

    public List<Contract> all() { return List.copyOf(contracts.values()); }

    public Contract require(String id) {
        Contract value = contracts.get(id);
        if (value == null) throw new IllegalArgumentException("unknown Batch 105-108 Skill: " + id);
        return value;
    }

    /** Returns the local dependency closure in stable topological order. */
    public List<Contract> plan(String targetSkillId) {
        require(targetSkillId);
        LinkedHashSet<String> ordered = new LinkedHashSet<>();
        visit(targetSkillId, new LinkedHashSet<>(), ordered);
        return ordered.stream().map(this::require).toList();
    }

    private void visit(String id, Set<String> visiting, LinkedHashSet<String> ordered) {
        if (ordered.contains(id)) return;
        if (!visiting.add(id)) throw new IllegalStateException("contract dependency cycle at " + id);
        for (String dependency : require(id).dependencies()) {
            if (contracts.containsKey(dependency)) visit(dependency, visiting, ordered);
        }
        visiting.remove(id);
        ordered.add(id);
    }

    private static Contract load(ObjectMapper sourceMapper, String id) {
        ObjectMapper mapper = sourceMapper.copy()
                .configure(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY, true)
                .configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
        String resource = "/batch105-108-contracts/" + id + ".compiled.json";
        try (InputStream input = SkillContractCatalog.class.getResourceAsStream(resource)) {
            if (input == null) throw new IllegalStateException("missing compiled contract " + resource);
            JsonNode compiled = mapper.readTree(input);
            if (compiled.path("compiledVersion").asInt() != 1) throw new IllegalStateException("unsupported contract version for " + id);
            JsonNode node = compiled.path("contract");
            String actualDigest = "sha256:" + sha256(pythonCanonicalJson(node).getBytes(StandardCharsets.UTF_8));
            String declaredDigest = compiled.path("canonicalSha256").asText();
            if (!actualDigest.equals(declaredDigest)) {
                throw new IllegalStateException("compiled contract digest mismatch for " + id
                        + ": declared=" + declaredDigest + ", actual=" + actualDigest);
            }

            Map<String, Object> raw = mapper.convertValue(node, new TypeReference<>() {});
            Map<String, List<String>> implementation = new LinkedHashMap<>();
            Object rawImplementation = raw.get("implementation");
            if (rawImplementation instanceof Map<?, ?> values) {
                values.forEach((key, value) -> implementation.put(String.valueOf(key), strings(value)));
            }
            int batch = ((Number) raw.get("batch")).intValue();
            return new Contract(
                    string(raw.get("id")), batch, string(raw.get("name")),
                    strings(raw.get("dependencies")), strings(raw.get("inputs")), strings(raw.get("outputs")),
                    strings(raw.get("workflow")), strings(raw.get("tests")), strings(raw.get("evidence")),
                    strings(raw.get("definition_of_done")), implementation, declaredDigest,
                    executionClass(id));
        } catch (Exception ex) {
            if (ex instanceof IllegalStateException state) throw state;
            throw new IllegalStateException("cannot load compiled contract " + id, ex);
        }
    }

    private static ExecutionClass executionClass(String id) {
        Set<String> independent = Set.of(
                "B105-S14", "B105-S16", "B106-S16", "B107-S03", "B107-S16",
                "B108-S07", "B108-S13", "B108-S16");
        if (independent.contains(id)) return ExecutionClass.INDEPENDENT_GATE;
        int batch = Integer.parseInt(id.substring(1, 4));
        int ordinal = Integer.parseInt(id.substring(6));
        if (batch == 105 && Set.of(3, 4, 6, 9, 10, 12, 13, 16).contains(ordinal)) return ExecutionClass.ISOLATED_RUNNER;
        if (batch == 106 && ordinal != 1 && ordinal != 2 && ordinal != 3 && ordinal != 13) return ExecutionClass.ISOLATED_RUNNER;
        if (batch == 107 && ordinal != 3 && ordinal != 15 && ordinal != 16) return ExecutionClass.ISOLATED_RUNNER;
        return ExecutionClass.CONTROL_PLANE;
    }

    private static void validateDependencies(Map<String, Contract> contracts) {
        for (Contract contract : contracts.values()) {
            for (String dependency : contract.dependencies()) {
                if (dependency.startsWith("B10") && !dependency.equals("B104-S16") && !contracts.containsKey(dependency)) {
                    throw new IllegalStateException(contract.id() + " has missing dependency " + dependency);
                }
            }
            if (contract.evidence().isEmpty() || contract.tests().isEmpty() || contract.workflow().isEmpty()) {
                throw new IllegalStateException(contract.id() + " is not executable");
            }
        }
        SkillContractCatalog temporary = new SkillContractCatalog(contracts);
        if (temporary.plan("B108-S16").size() != 64) {
            throw new IllegalStateException("B108-S16 must close over all 64 local Skills");
        }
    }

    private SkillContractCatalog(Map<String, Contract> contracts) { this.contracts = contracts; }

    private static String string(Object value) {
        if (!(value instanceof String text) || text.isBlank()) throw new IllegalStateException("contract field is missing");
        return text;
    }

    private static List<String> strings(Object value) {
        if (!(value instanceof Iterable<?> iterable)) return List.of();
        List<String> result = new ArrayList<>();
        iterable.forEach(item -> result.add(string(item)));
        return List.copyOf(result);
    }

    private static String sha256(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    /** Byte-compatible with json.dumps(value, sort_keys=True, separators=(",", ":")). */
    private static String pythonCanonicalJson(JsonNode node) {
        if (node.isObject()) {
            List<String> names = new ArrayList<>();
            node.fieldNames().forEachRemaining(names::add);
            Collections.sort(names);
            StringBuilder result = new StringBuilder("{");
            for (int index = 0; index < names.size(); index++) {
                if (index > 0) result.append(',');
                String name = names.get(index);
                result.append(pythonString(name)).append(':').append(pythonCanonicalJson(node.get(name)));
            }
            return result.append('}').toString();
        }
        if (node.isArray()) {
            StringBuilder result = new StringBuilder("[");
            for (int index = 0; index < node.size(); index++) {
                if (index > 0) result.append(',');
                result.append(pythonCanonicalJson(node.get(index)));
            }
            return result.append(']').toString();
        }
        if (node.isTextual()) return pythonString(node.textValue());
        if (node.isBoolean()) return node.booleanValue() ? "true" : "false";
        if (node.isNull()) return "null";
        if (node.isIntegralNumber()) return node.bigIntegerValue().toString();
        if (node.isFloatingPointNumber()) return node.decimalValue().stripTrailingZeros().toPlainString();
        throw new IllegalStateException("unsupported canonical JSON node: " + node.getNodeType());
    }

    private static String pythonString(String value) {
        StringBuilder result = new StringBuilder("\"");
        value.codePoints().forEach(codePoint -> {
            switch (codePoint) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\b' -> result.append("\\b");
                case '\t' -> result.append("\\t");
                case '\n' -> result.append("\\n");
                case '\f' -> result.append("\\f");
                case '\r' -> result.append("\\r");
                default -> {
                    if (codePoint >= 0x20 && codePoint <= 0x7e) {
                        result.append((char) codePoint);
                    } else if (codePoint <= 0xffff) {
                        result.append(String.format("\\u%04x", codePoint));
                    } else {
                        int adjusted = codePoint - 0x10000;
                        result.append(String.format("\\u%04x\\u%04x",
                                0xd800 + (adjusted >>> 10), 0xdc00 + (adjusted & 0x3ff)));
                    }
                }
            }
        });
        return result.append('"').toString();
    }
}
