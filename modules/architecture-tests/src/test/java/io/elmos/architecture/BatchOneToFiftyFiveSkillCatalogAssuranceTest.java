package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchOneToFiftyFiveSkillCatalogAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test
    void combinedCatalogKeepsMigrationAndProductNamespacesSeparate() throws IOException {
        String manifest = Files.readString(root.resolve(
                "elmos-codex-skills-batch1-55-complete/manifest.json"));
        assertEquals(820, occurrences(manifest, "\"namespace\": \"migration-pack\""));
        assertEquals(1004, occurrences(manifest, "\"namespace\": \"product-commercialization\""));
        assertTrue(manifest.contains("\"skillCount\": 1824"));
        assertTrue(manifest.contains("\"renamed\": 1015"));
        assertTrue(manifest.contains("\"structural\": \"PASS\""));
        assertTrue(manifest.contains("\"overall\": \"NOT_COMPLETE\""));
        assertTrue(manifest.contains("\"externalEvidenceStatus\": \"NOT_RUN\""));
    }

    @Test
    void incompleteSourceAndPlanningEditionsCannotMasqueradeAsCompletion() throws IOException {
        String manifest = Files.readString(root.resolve(
                "elmos-codex-skills-batch1-55-complete/manifest.json"));
        String report = Files.readString(root.resolve(
                "docs/batch1-55-skills/verification.md"));
        assertEquals(448, occurrences(manifest,
                "\"editionStatus\": \"normalized-source-incomplete\""));
        assertEquals(752, occurrences(manifest,
                "\"editionStatus\": \"generated-planning-edition\""));
        assertTrue(report.contains("Overall Batch 1–55 implementation completion: `NOT_COMPLETE`"));
        assertTrue(report.contains("all 408 cases `not-run`"));
    }

    private long occurrences(String value, String expression) {
        return Pattern.compile(Pattern.quote(expression)).matcher(value).results().count();
    }
}
