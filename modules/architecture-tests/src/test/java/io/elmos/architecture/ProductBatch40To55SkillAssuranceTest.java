package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductBatch40To55SkillAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test
    void exactCatalogProvenanceAndNamespaceRemainFailClosed() throws IOException {
        String manifest = Files.readString(root.resolve(
                "docs/product-batches40-55-complete/skill-source-manifest.json"));
        assertEquals(768, Pattern.compile(
                "\"family\": \"elmos-product-commercialization-b40-b55-complete\"")
                .matcher(manifest).results().count());
        assertEquals(48, Pattern.compile("\"subbatch\": \"(?:4[0-9]|5[0-5])[ABC]\"")
                .matcher(manifest).results().map(result -> result.group()).distinct().count());
        assertTrue(manifest.contains("\"approved_conversation_design_count\": 16"));
        assertTrue(manifest.contains("\"generated_planning_edition_count\": 752"));
        assertTrue(manifest.contains("\"canonical_product_skill_count_with_prior_families\": 1107"));
        assertTrue(manifest.contains("Product Batch B40-B55 Enterprise Domains"));
        assertTrue(manifest.contains("Migration Packs M40-M45"));
        assertTrue(manifest.contains("\"external_execution_evidence\": \"NOT_RUN\""));
    }

    @Test
    void generatedPlanningEditionCannotMasqueradeAsCertification() throws IOException {
        String repositoryInstructions = Files.readString(root.resolve("AGENTS.md"));
        String packageReadme = Files.readString(root.resolve(
                "elmos-codex-skills-batch40-55-complete/README.md"));
        String provenance = Files.readString(root.resolve(
                "elmos-codex-skills-batch40-55-complete/references/provenance.md"));
        assertTrue(repositoryInstructions.contains("generated planning edition"));
        assertTrue(repositoryInstructions.contains("static Skill checks remain engineering evidence only"));
        assertTrue(packageReadme.contains("does not certify production implementations"));
        assertTrue(provenance.contains("generated as a structured planning edition"));
        assertTrue(provenance.contains("have not yet been reviewed one subbatch at a time"));
    }
}
