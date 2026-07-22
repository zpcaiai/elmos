package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.*;

class CompanySeriesAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    private record Batch(int number, int first, int last, String group, String schema,
                         String checklist, String manifest, String digest,
                         String migration, int tables, int appendOnly, String finalGate) {}

    private static final List<Batch> BATCHES = List.of(
            new Batch(15, 461, 525, "company-operating-system", "company-operating-system-schema",
                    "batch-15-company-operating-acceptance-checklist.md",
                    "batch-15-company-series-source-manifest.json",
                    "7ed443ce960fab9afee75215f746412e0845e7c9c46ae8af3e3c63655778956f",
                    "V24__company_operating_and_governance_system.sql", 88, 11, "C15-G"),
            new Batch(16, 526, 592, "agent-workforce", "agent-workforce-schema",
                    "batch-16-agent-workforce-acceptance-checklist.md",
                    "batch-16-company-series-source-manifest.json",
                    "ba0eeafe289b8ae73e0f0198c64f4d8d8163e190e5c8c482dc33e63cfd06a999",
                    "V25__ai_native_company_and_agent_workforce.sql", 76, 13, "AI16-G"),
            new Batch(17, 593, 668, "vertical-solutions", "vertical-solution-schema",
                    "batch-17-vertical-solution-acceptance-checklist.md",
                    "batch-17-company-series-source-manifest.json",
                    "d582bd22cfab08efc3905d0a9f9853a3982bc42453333d9a5aaee19d551db7a8",
                    "V26__vertical_solution_factory.sql", 40, 6, "V17-G"),
            new Batch(18, 669, 745, "group-integration", "group-integration-schema",
                    "batch-18-group-integration-acceptance-checklist.md",
                    "batch-18-company-series-source-manifest.json",
                    "b94f20dfc4901a4bdb1c0d3ada77d2051f9a1b78be2ab246a30495ec94d77564",
                    "V27__group_integration_factory.sql", 51, 12, "M18-H"));

    @Test
    void allTwoHundredEightyFiveSkillsAreExactInitializedAndEvidenceBound() throws IOException {
        for (Batch batch : BATCHES) {
            Path group = root.resolve("agent-skills").resolve(batch.group());
            String checklist = Files.readString(root.resolve("docs").resolve(batch.checklist()));
            var matcher = Pattern.compile("(?m)^\\| (\\d{3}) `([^`]+)` \\|").matcher(checklist);
            Map<Integer, String> expected = matcher.results().collect(Collectors.toMap(
                    value -> Integer.parseInt(value.group(1)), value -> value.group(2),
                    (left, right) -> left, TreeMap::new));
            assertEquals(IntStream.rangeClosed(batch.first(), batch.last()).boxed().toList(),
                    expected.keySet().stream().toList());
            List<String> actual;
            try (var paths = Files.list(group)) {
                actual = paths.filter(path -> Files.isRegularFile(path.resolve("SKILL.md")))
                        .map(path -> path.getFileName().toString()).sorted().toList();
            }
            assertEquals(expected.values().stream().sorted().toList(), actual);
            for (Map.Entry<Integer, String> entry : expected.entrySet()) {
                Path skill = group.resolve(entry.getValue());
                String body = Files.readString(skill.resolve("SKILL.md"));
                String metadata = Files.readString(skill.resolve("agents/openai.yaml"));
                assertTrue(body.contains("name: " + entry.getValue()));
                assertTrue(body.contains("authoritative Batch " + batch.number() + " Skill " + entry.getKey())
                        || body.contains("Authoritative Batch " + batch.number() + " Skill " + entry.getKey()));
                assertTrue(body.contains("external_operation_executed=false"));
                assertTrue(body.contains("## Authoritative specification"));
                assertFalse(body.contains("TODO"));
                assertTrue(metadata.contains("$" + entry.getValue()));
            }
            String manifest = Files.readString(root.resolve("docs").resolve(batch.manifest()));
            assertTrue(manifest.contains(batch.digest()));
            assertTrue(manifest.contains("\"skill_count\": " + (batch.last() - batch.first() + 1)));
        }
        assertEquals(285, BATCHES.stream().mapToInt(value -> value.last() - value.first() + 1).sum());
    }

    @Test
    void schemasAndChecklistsKeepFinalGatesExternalAndFailClosed() throws IOException {
        for (Batch batch : BATCHES) {
            Path schema = root.resolve("contracts").resolve(batch.schema());
            try (var files = Files.list(schema)) {
                List<Path> schemas = files.filter(value -> value.toString().endsWith(".schema.json")).toList();
                assertEquals(4, schemas.size());
                for (Path file : schemas) {
                    String body = Files.readString(file);
                    assertTrue(body.contains("https://json-schema.org/draft/2020-12/schema"));
                    assertTrue(body.contains("\"additionalProperties\": false"));
                    assertTrue(body.contains("external_operation_executed"));
                }
            }
            String conformance = Files.readString(schema.resolve("conformance-report.schema.json"));
            assertTrue(conformance.contains("\"const\": \"" + batch.finalGate() + "\""));
            String checklist = Files.readString(root.resolve("docs").resolve(batch.checklist()));
            assertEquals(batch.last() - batch.first() + 1,
                    checklist.lines().filter(line -> line.matches("^\\| \\d{3} `.*")).count());
            assertEquals(batch.last() - batch.first() + 1,
                    checklist.lines().filter(line -> line.endsWith("| `NOT_RUN` |")).count());
        }
    }

    @Test
    void controlPlaneContainsExactModelsGatesAndNoExternalExecutionMechanism() throws IOException {
        Path source = root.resolve("modules/company-series/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.toString().endsWith(".java")).map(path -> {
                try { return Files.readString(path); }
                catch (IOException error) { throw new java.io.UncheckedIOException(error); }
            }).collect(Collectors.joining("\n"));
        }
        for (String value : List.of("COGS", "AI-native operating system", "VSP four-layer model", "GITM",
                "C15", "AI16", "V17", "M18", "company-scale-operating-ready",
                "bounded-autonomous-company-ready", "vertical-commercial-delivery-ready",
                "group-integration-completed", "externalOperationExecuted")) assertTrue(production.contains(value));
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertFalse(production.contains("HttpClient"));
    }

    @Test
    void migrationsUseDedicatedSchemasExactInventoriesStrongRlsAndAppendOnlyEvidence() throws IOException {
        Path migrations = root.resolve("modules/persistence/src/main/resources/db/migration");
        for (Batch batch : BATCHES) {
            String migration = Files.readString(migrations.resolve(batch.migration()));
            assertEquals(batch.tables(), arraySize(migration, "batch_tables text[] := ARRAY["));
            assertEquals(batch.appendOnly(), arraySize(migration, "append_only_tables text[] := ARRAY["));
            assertTrue(migration.contains("FORCE ROW LEVEL SECURITY"));
            assertTrue(migration.contains("tenant_isolation"));
            assertTrue(migration.contains("company_series_append_only"));
            assertTrue(migration.contains("external_operation_executed = false"));
            assertFalse(migration.contains("secret_value"));
        }
    }

    private static long arraySize(String migration, String marker) {
        int start = migration.indexOf(marker);
        int end = migration.indexOf("];", start);
        assertTrue(start >= 0 && end > start);
        return Pattern.compile("'([a-z][a-z0-9_]*)'").matcher(migration.substring(start, end))
                .results().count();
    }
}
