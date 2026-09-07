package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class BatchFourteenGrowthAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test
    void growthControlPlaneImplementsExactPegmAndCannotExecuteExternalOperations()
            throws IOException {
        Path source = root.resolve("modules/ecosystem-growth/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try {
                            return Files.readString(path);
                        } catch (IOException error) {
                            throw new java.io.UncheckedIOException(error);
                        }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertTrue(production.contains("Product and Ecosystem Growth Model (PEGM)"));
        for (String domain : List.of("ACQUISITION", "ACTIVATION", "ADOPTION", "RETENTION",
                "EXPANSION", "ADVOCACY", "ECOSYSTEM")) {
            assertTrue(production.contains(domain));
        }
        assertTrue(production.contains("ProductActivationAuthority"));
        assertTrue(production.contains("ContentDeveloperAuthority"));
        assertTrue(production.contains("CommunitySafetyAuthority"));
        assertTrue(production.contains("MarketplaceGrowthAuthority"));
        assertTrue(production.contains("InternationalizationAuthority"));
        assertTrue(production.contains("RegionalChannelAuthority"));
        assertTrue(production.contains("GrowthConformanceAuthority"));
        assertTrue(production.contains(
                "scalable growth readiness requires G14-G and complete external evidence"));
        assertTrue(production.contains("external_operation_executed"));
        assertFalse(production.contains("source_specification_truncated_after_skill_444"));
        assertFalse(production.contains("B14_H"));
    }

    @Test
    void allSixtyAuthoritativeSkillCreatorPackagesAreExactPromptedAndBoundaryBound()
            throws IOException {
        Path skills = root.resolve("agent-skills/ecosystem-growth");
        Map<Integer, String> expected = expectedSkills();
        List<Path> packages;
        try (var paths = Files.list(skills)) {
            packages = paths.filter(Files::isDirectory)
                    .filter(path -> Files.isRegularFile(path.resolve("SKILL.md"))).toList();
        }
        assertEquals(60, packages.size());
        assertEquals(expected.values().stream().sorted().toList(),
                packages.stream().map(path -> path.getFileName().toString()).sorted().toList());
        for (Map.Entry<Integer, String> entry : expected.entrySet()) {
            String name = entry.getValue();
            Path skill = skills.resolve(name);
            String body = Files.readString(skill.resolve("SKILL.md"));
            String metadata = Files.readString(skill.resolve("agents/openai.yaml"));
            assertTrue(body.contains("name: " + name));
            assertTrue(body.contains("authoritative Batch 14 Skill " + entry.getKey())
                    || body.contains("Authoritative Batch 14 Skill " + entry.getKey()));
            assertTrue(body.contains("../references/batch-14-growth-evidence-boundary.md"));
            assertTrue(body.contains("## Hard Rules"));
            assertTrue(body.contains("## Acceptance Criteria"));
            assertFalse(body.contains("TODO"));
            assertTrue(metadata.contains("$" + name));
            assertTrue(metadata.contains("short_description:"));
        }
        String reference = Files.readString(
                skills.resolve("references/batch-14-growth-evidence-boundary.md"));
        assertTrue(reference.contains("Skills 401–460"));
        assertTrue(reference.contains("Product and Ecosystem Growth Model (PEGM)"));
        assertTrue(reference.contains("G14-G"));
        assertTrue(reference.contains("external_operation_executed=false"));
        assertFalse(reference.contains("truncat"));
    }

    @Test
    void contractsReportsAndAcceptanceMappingCoverTheAuthoritativeBatch()
            throws IOException {
        Path schemas = root.resolve("contracts/ecosystem-growth-schema");
        try (var paths = Files.list(schemas)) {
            var files = paths.filter(path ->
                    path.getFileName().toString().endsWith(".schema.json")).toList();
            assertEquals(18, files.size());
            for (Path schema : files) {
                String body = Files.readString(schema);
                assertTrue(body.contains("https://json-schema.org/draft/2020-12/schema"));
                assertTrue(body.contains("\"additionalProperties\": false"), schema.toString());
            }
        }
        String conformance = Files.readString(
                schemas.resolve("batch-14-conformance-report.schema.json"));
        assertTrue(conformance.contains("\"const\": \"G14_G\""));
        assertTrue(conformance.contains("\"scalable_growth_ready\""));
        assertTrue(conformance.contains(
                "\"external_operation_executed\": { \"const\": false }"));
        String pack = Files.readString(schemas.resolve("growth-evidence-pack.schema.json"));
        assertTrue(pack.contains("\"minItems\": 6"));
        assertTrue(pack.contains("\"gate-evidence.schema.json\""));
        assertFalse(pack.contains("source_specification_truncated"));

        String writer = Files.readString(root.resolve(
                "modules/ecosystem-growth/src/main/java/io/elmos/ecosystemgrowth/EcosystemGrowthArtifactWriter.java"));
        for (String report : List.of(
                "product-growth-report.json", "activation-retention-report.json",
                "channel-attribution-report.json", "content-performance-report.json",
                "developer-ecosystem-report.json", "community-health-report.json",
                "marketplace-growth-report.json", "localization-quality-report.json",
                "regional-launch-report.json", "channel-economics-report.json",
                "growth-risk-report.json", "batch-14-conformance-report.json")) {
            assertTrue(writer.contains(report));
        }

        String checklist = Files.readString(
                root.resolve("docs/batch-14-growth-acceptance-checklist.md"));
        long rows = checklist.lines()
                .filter(line -> line.startsWith("| 4") && line.contains(" | G14-")).count();
        assertEquals(60, rows);
        assertTrue(checklist.contains("401 `growth-system-orchestrator`"));
        assertTrue(checklist.contains(
                "460 `batch-14-growth-and-ecosystem-conformance-gate`"));
        assertFalse(checklist.contains("| 461 "));
    }

    @Test
    void v22IsTenantIsolatedAppendOnlyAndContainsExactSixtyNineCoreTables()
            throws IOException {
        String migration = Files.readString(root.resolve(
                "modules/persistence/src/main/resources/db/migration/" +
                        "V22__product_ecosystem_growth_and_regional_replication.sql"));
        int start = migration.indexOf("batch14_tables text[] := ARRAY[");
        int end = migration.indexOf("];", start);
        assertTrue(start >= 0 && end > start);
        String array = migration.substring(start, end);
        var matcher = Pattern.compile("'([a-z][a-z_]*)'").matcher(array);
        Set<String> tables = matcher.results()
                .map(result -> result.group(1)).collect(Collectors.toSet());
        assertEquals(69, tables.size());
        assertTrue(tables.containsAll(Set.of(
                "growth_programs", "north_star_metrics", "growth_events",
                "content_assets", "developer_profiles", "community_spaces",
                "marketplace_publishers", "translations", "regional_requirements",
                "regional_metrics", "growth_economics")));
        assertTrue(migration.contains("tenant_scope varchar(255) NOT NULL"));
        assertTrue(migration.contains("persona varchar(96)"));
        assertTrue(migration.contains("channel varchar(96)"));
        assertTrue(migration.contains("campaign varchar(160)"));
        assertTrue(migration.contains("consent varchar(64) NOT NULL"));
        assertTrue(migration.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(migration.contains(
                "current_setting(''app.organization_id'', true)"));
        assertTrue(migration.contains("external_operation_executed = false"));
        assertEquals(18, Pattern.compile("CREATE TRIGGER batch14_")
                .matcher(migration).results().count());
        assertTrue(migration.contains("batch14_growth_events_append_only"));
        assertTrue(migration.contains("batch14_moderation_cases_append_only"));
        assertTrue(migration.contains("batch14_growth_economics_append_only"));
        assertFalse(migration.contains("secret_value"));
        assertFalse(migration.contains("CREATE TABLE billing"));
    }

    private static Map<Integer, String> expectedSkills() {
        String[] names = {
                "growth-system-orchestrator",
                "north-star-and-growth-metric-designer",
                "user-journey-and-growth-funnel-modeler",
                "acquisition-channel-architecture-manager",
                "product-led-growth-strategy-manager",
                "self-service-signup-and-workspace-provisioner",
                "first-assessment-activation-orchestrator",
                "time-to-value-optimizer",
                "trial-freemium-and-developer-plan-manager",
                "lifecycle-messaging-and-in-product-guidance",
                "referral-invitation-and-team-expansion-manager",
                "growth-experiment-and-feature-test-platform",
                "experiment-statistics-and-decision-controller",
                "growth-event-and-semantic-analytics-layer",
                "channel-attribution-and-incrementality-manager",
                "content-strategy-and-topic-architecture",
                "technical-content-production-pipeline",
                "seo-topic-cluster-and-search-demand-manager",
                "comparison-migration-guide-and-solution-page-factory",
                "customer-case-study-and-proof-content-manager",
                "webinar-workshop-and-technical-event-manager",
                "research-industry-report-and-thought-leadership-manager",
                "developer-portal-builder",
                "documentation-as-product-manager",
                "api-cli-and-sdk-developer-experience-manager",
                "starter-kit-sample-repository-and-reference-app-manager",
                "interactive-demo-sandbox-and-playground",
                "developer-relations-program-manager",
                "champion-ambassador-and-expert-program",
                "community-platform-and-identity-integrator",
                "community-content-question-and-knowledge-architecture",
                "community-moderation-trust-and-safety-manager",
                "community-contribution-and-reputation-system",
                "community-event-hackathon-and-challenge-manager",
                "support-community-and-documentation-knowledge-loop",
                "marketplace-growth-orchestrator",
                "marketplace-publisher-onboarding-manager",
                "marketplace-asset-certification-and-quality-gate",
                "marketplace-search-discovery-and-recommendation-engine",
                "marketplace-install-version-and-dependency-manager",
                "marketplace-pricing-promotion-and-revenue-share",
                "marketplace-review-trust-and-abuse-manager",
                "marketplace-supply-demand-network-effect-manager",
                "internationalization-platform-architect",
                "localization-content-workflow-manager",
                "terminology-glossary-translation-memory-and-style-guide",
                "locale-format-and-regional-user-experience-manager",
                "regional-legal-privacy-and-product-compliance-manager",
                "multi-currency-tax-and-regional-pricing-manager",
                "regional-market-entry-assessor",
                "regional-launch-playbook-manager",
                "local-content-community-and-developer-program",
                "regional-channel-and-partner-replication-manager",
                "cloud-marketplace-and-technology-alliance-manager",
                "regional-support-sla-and-operating-model",
                "regional-growth-dashboard-and-comparison-engine",
                "growth-cost-ltv-and-channel-economics-manager",
                "brand-trust-and-growth-risk-governance",
                "growth-playbook-and-learning-repository",
                "batch-14-growth-and-ecosystem-conformance-gate"
        };
        Map<Integer, String> result = new LinkedHashMap<>();
        for (int index = 0; index < names.length; index++) {
            result.put(401 + index, names[index]);
        }
        return Map.copyOf(result);
    }
}
