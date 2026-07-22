package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class BatchTwentyTwoToTwentySixAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();
    private record Batch(int number, String engine, String fixture, int scenarios, String migration,
                         String schema, int tables, String definitionFactory) {}
    private static final List<Batch> BATCHES = List.of(
            new Batch(22, "software-delivery-platform-engine", "batch22-acceptance-scenarios.json", 36,
                    "V28__software_delivery_platform_engine.sql", "software_delivery", 81, "DomainDefinitions.softwareDelivery()"),
            new Batch(23, "ai-platform-engine", "batch23-acceptance-scenarios.json", 44,
                    "V29__ai_ml_generative_ai_platform.sql", "ai_platform", 107, "DomainDefinitions.aiPlatform()"),
            new Batch(24, "edge-iot-industrial-engine", "batch24-acceptance-scenarios.json", 36,
                    "V30__edge_iot_industrial_systems.sql", "edge_industrial", 112, "DomainDefinitions.industrial()"),
            new Batch(25, "operations-sre-itsm-engine", "batch25-acceptance-scenarios.json", 44,
                    "V31__operations_sre_itsm.sql", "operations_sre", 108, "DomainDefinitions.operations()"),
            new Batch(26, "enterprise-architecture-engine", "batch26-acceptance-scenarios.json", 50,
                    "V32__enterprise_architecture_portfolio.sql", "enterprise_architecture", 108, "DomainDefinitions.enterpriseArchitecture()"));

    @Test void ninetyInitializedRuntimeSkillsCarryCompleteMetadataAndNoPlaceholders() throws IOException {
        var counts = new java.util.HashMap<>(Map.of(22, 0L, 23, 0L, 24, 0L, 25, 0L, 26, 0L));
        try (var directories = Files.list(root.resolve("agent-skills/runtime"))) {
            for (Path directory : directories.filter(path -> Files.isRegularFile(path.resolve("SKILL.md"))).toList()) {
                Path metadata = directory.resolve("agents/openai.yaml");
                if (!Files.isRegularFile(metadata)) continue;
                String yaml = Files.readString(metadata);
                for (Batch batch : BATCHES) if (yaml.contains("display_name: \"Batch " + batch.number() + " ")) {
                    counts.compute(batch.number(), (ignored, value) -> value + 1);
                    String skill = Files.readString(directory.resolve("SKILL.md"));
                    assertTrue(skill.startsWith("---\nname: "));
                    assertTrue(yaml.contains("$" + directory.getFileName()));
                    assertFalse(skill.contains("TODO"));
                }
            }
        }
        BATCHES.forEach(batch -> assertEquals(18L, counts.get(batch.number())));
    }

    @Test void schemasScenariosAndMigrationsMatchAuthoritativeInventories() throws IOException {
        List<String> schemas = List.of(
                "pipeline-component", "artifact-promotion", "golden-path", "dora-observation", "self-service-request",
                "ai-release-bundle", "ai-feature-parity-result", "agent-tool-permission", "ai-evaluation-decision", "responsible-ai-decision",
                "industrial-tag-contract", "digital-twin-state", "ota-release", "device-command", "industrial-cutover-decision",
                "operations-service-instance", "normalized-operational-event", "incident", "service-level-objective-v2", "remediation-policy", "continuity-exercise-result",
                "business-capability", "application-portfolio-assessment", "technology-standard", "architecture-decision", "architecture-roadmap");
        assertEquals(26, schemas.size());
        schemas.forEach(name -> assertTrue(Files.isRegularFile(root.resolve("contracts/" + name + "-schema/" + name + ".schema.json"))));
        for (Batch batch : BATCHES) {
            Path fixture = root.resolve("engines").resolve(batch.engine()).resolve("test-fixtures").resolve(batch.fixture());
            String scenarios = Files.readString(fixture);
            assertEquals(batch.scenarios(), Pattern.compile("\\\"scenarioId\\\"").matcher(scenarios).results().count());
            assertEquals(batch.scenarios(), Pattern.compile("\\\"safeOutcome\\\": \\\"FAIL_CLOSED\\\"").matcher(scenarios).results().count());
            String migration = Files.readString(root.resolve("modules/persistence/src/main/resources/db/migration").resolve(batch.migration()));
            assertEquals(batch.tables(), arraySize(migration, "batch_tables text[] := ARRAY["));
            assertTrue(migration.contains("CREATE SCHEMA IF NOT EXISTS " + batch.schema()));
            assertTrue(migration.contains("FORCE ROW LEVEL SECURITY"));
            assertTrue(migration.contains("actual_execution_evidence_ref"));
            assertTrue(migration.contains("human_approval_ref"));
            assertFalse(migration.contains("secret_value"));
        }
    }

    @Test void engineAndGovernanceSourcesCannotFabricateExternalSuccess() throws IOException {
        String shared = readSources(root.resolve("modules/evidence-bound-engine/src/main/java"));
        assertFalse(shared.contains("ProcessBuilder"));
        assertFalse(shared.contains("Runtime.getRuntime"));
        assertFalse(shared.contains("java.sql"));
        assertTrue(shared.contains("externalOperationExecuted"));
        assertTrue(shared.contains("evidenceFabricated"));
        assertTrue(shared.contains("humanDecisionGranted"));
        assertTrue(shared.contains("workerModifiedGate"));
        for (Batch batch : BATCHES) {
            String engine = readSources(root.resolve("engines").resolve(batch.engine()).resolve("src/main/java"));
            assertTrue(engine.contains(batch.definitionFactory()));
            assertFalse(engine.contains("ProcessBuilder"));
            assertFalse(engine.contains("Runtime.getRuntime"));
            assertFalse(engine.contains("java.sql"));
        }
        String governance = Files.readString(root.resolve("modules/application/src/main/java/io/elmos/application/CrossDomainDecisionGovernance.java"));
        assertTrue(governance.contains("READY_FOR_HUMAN_DECISION"));
        assertTrue(governance.contains("false, false, false"));
    }

    private static long arraySize(String migration, String marker) {
        int start = migration.indexOf(marker); int end = migration.indexOf("];", start);
        assertTrue(start >= 0 && end > start);
        return Pattern.compile("'([a-z][a-z0-9_]*)'").matcher(migration.substring(start, end)).results().count();
    }
    private static String readSources(Path source) throws IOException {
        try (var files = Files.walk(source)) {
            return files.filter(path -> path.toString().endsWith(".java")).map(path -> {
                try { return Files.readString(path); }
                catch (IOException error) { throw new java.io.UncheckedIOException(error); }
            }).collect(Collectors.joining("\n"));
        }
    }
}
