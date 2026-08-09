package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringComplexCapabilityDocumentationTest {
    private static final String DOCUMENT = "docs/batch30/SPRING_COMPLEX_CAPABILITY_TESTS.md";
    private static final String EXAMPLE_START = "<!-- spring-capability-tests-example:start -->";
    private static final String EXAMPLE_END = "<!-- spring-capability-tests-example:end -->";

    @Test void documentedManifestExampleMatchesTheExecutableGateContract() throws Exception {
        String document = Files.readString(repositoryFile(DOCUMENT));
        JsonNode example = new ObjectMapper().readTree(exampleJson(document));

        assertEquals("1.0", example.path("schema_version").asText());
        assertEquals("elmos.spring-capability-tests", example.path("kind").asText());
        Set<String> manifestTests = strings(example.path("test_identities"));
        assertTrue(!manifestTests.isEmpty());

        JsonNode domains = example.path("domains");
        for (Map.Entry<String, java.util.List<String>> required
                : LocalSpringUpgradeExecutionPort.requiredComplexCapabilityInvariants().entrySet()) {
            JsonNode domain = domains.path(required.getKey());
            assertTrue(domain.isObject(), "missing documented domain " + required.getKey());
            assertEquals(new TreeSet<>(required.getValue()), strings(domain.path("invariants")));
            Set<String> domainTests = strings(domain.path("test_identities"));
            assertTrue(!domainTests.isEmpty());
            assertTrue(manifestTests.containsAll(domainTests));
        }

        assertTrue(document.contains("CONDITIONAL_ACTIVATION_UNRESOLVED:<capability>"));
        assertTrue(document.contains("PASS_LOCAL_ENGINEERING"));
        assertTrue(document.contains("certification_eligible=false"));
        assertTrue(document.contains("certification_status=NOT_CERTIFIED"));
        assertTrue(document.contains("COMPLEX_CAPABILITY_VERIFICATION_BLOCKED"));
    }

    private static Set<String> strings(JsonNode node) {
        assertTrue(node.isArray());
        Set<String> values = new TreeSet<>();
        node.forEach(value -> {
            assertTrue(value.isTextual());
            assertTrue(values.add(value.asText()), "duplicate documented value " + value.asText());
        });
        return values;
    }

    private static String exampleJson(String document) {
        int markerStart = document.indexOf(EXAMPLE_START);
        int markerEnd = document.indexOf(EXAMPLE_END);
        assertTrue(markerStart >= 0 && markerEnd > markerStart);
        int fence = document.indexOf("```json", markerStart);
        int jsonStart = document.indexOf('\n', fence) + 1;
        int jsonEnd = document.indexOf("\n```", jsonStart);
        assertTrue(fence >= 0 && jsonStart > fence && jsonEnd > jsonStart && jsonEnd < markerEnd);
        return document.substring(jsonStart, jsonEnd);
    }

    private static Path repositoryFile(String relative) {
        Path directory = Path.of("").toAbsolutePath().normalize();
        while (directory != null) {
            Path candidate = directory.resolve(relative);
            if (Files.isRegularFile(candidate)) return candidate;
            directory = directory.getParent();
        }
        throw new AssertionError("repository document not found: " + relative);
    }
}
