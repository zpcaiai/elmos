package io.elmos.companyseries;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

import static io.elmos.companyseries.CompanySeriesModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CompanySeriesEvaluatorTest {
    private static final Instant NOW = Instant.parse("2026-07-22T00:00:00Z");
    @TempDir Path temporary;

    @Test
    void definitionsPreserveExactModelsGatesDimensionsAndReports() {
        List<ProgramDefinition> definitions = CompanySeriesPrograms.all();
        assertEquals(List.of(15, 16, 17, 18), definitions.stream().map(ProgramDefinition::batch).toList());
        assertEquals(List.of("C15-G", "AI16-G", "V17-G", "M18-H"),
                definitions.stream().map(ProgramDefinition::finalGate).toList());
        assertEquals(List.of(12, 13, 8, 12), definitions.stream().map(value -> value.reports().size()).toList());
        assertEquals("COGS", definitions.getFirst().model());
        assertEquals("GITM", definitions.getLast().model());
        assertTrue(definitions.get(2).dimensions().containsAll(List.of(
                "finance", "manufacturing", "energy", "healthcare", "government", "commerce", "telecom")));
    }

    @Test
    void absentAuthoritiesFailClosedWithoutClaimingFieldReadiness() {
        ProgramDefinition definition = CompanySeriesPrograms.agentWorkforce();
        Outcome outcome = new CompanySeriesEvaluator().evaluate(definition, request(), new AuthorityRegistry(Map.of()));
        assertEquals("BLOCKED", outcome.report().gate());
        assertEquals("BLOCKED", outcome.report().status());
        assertFalse(outcome.report().ready());
        assertFalse(outcome.report().evidenceComplete());
        assertEquals(definition.gates().size(), outcome.report().blockers().size());
        assertFalse(outcome.report().externalOperationExecuted());
    }

    @Test
    void completeIndependentEvidenceReachesOnlyTheExactFinalGate() {
        for (ProgramDefinition definition : CompanySeriesPrograms.all()) {
            Request request = request();
            Map<String, EvidenceAuthority> authorities = new LinkedHashMap<>();
            for (GateDefinition gate : definition.gates())
                authorities.put(gate.id(), (ignored, expected) -> passed(definition, request, expected));
            Outcome outcome = new CompanySeriesEvaluator().evaluate(
                    definition, request, new AuthorityRegistry(authorities));
            assertEquals(definition.finalGate(), outcome.report().gate());
            assertEquals(definition.finalStatus(), outcome.report().status());
            assertTrue(outcome.report().ready());
            assertTrue(outcome.report().evidenceComplete());
            assertEquals(definition.dimensions(), outcome.report().supportedDimensions());
        }
    }

    @Test
    void failedEarlierGateCannotBeCompensatedByLaterPassingEvidence() {
        ProgramDefinition definition = CompanySeriesPrograms.groupIntegrationFactory();
        Request request = request();
        Map<String, EvidenceAuthority> authorities = new LinkedHashMap<>();
        for (GateDefinition gate : definition.gates()) {
            authorities.put(gate.id(), (ignored, expected) -> expected.id().equals("M18-B")
                    ? new GateEvidence(18, request.programId(), request.sourceVersion(), request.organizationId(),
                    expected.id(), EvidenceStatus.FAILED, 0.8, true, true, true, 1,
                    "authority", NOW, List.of("evidence-" + expected.id()), false)
                    : passed(definition, request, expected));
        }
        Outcome outcome = new CompanySeriesEvaluator().evaluate(definition, request, new AuthorityRegistry(authorities));
        assertEquals("M18-A", outcome.report().gate());
        assertEquals("PARTIAL", outcome.report().status());
        assertFalse(outcome.report().ready());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("M18-B")));
    }

    @Test
    void artifactWriterCreatesEverySpecifiedRootDirectoryAndReport() throws Exception {
        for (ProgramDefinition definition : CompanySeriesPrograms.all()) {
            Request request = request();
            Map<String, EvidenceAuthority> authorities = new LinkedHashMap<>();
            for (GateDefinition gate : definition.gates())
                authorities.put(gate.id(), (ignored, expected) -> passed(definition, request, expected));
            Outcome outcome = new CompanySeriesEvaluator().evaluate(
                    definition, request, new AuthorityRegistry(authorities));
            Map<String, Path> written = new CompanySeriesArtifactWriter().write(outcome);
            Path root = request.artifactWorkspace().resolve(definition.artifactRoot());
            for (String directory : definition.artifactDirectories())
                assertTrue(Files.isDirectory(root.resolve(directory)));
            for (String report : definition.reports())
                assertTrue(Files.isRegularFile(root.resolve("reports").resolve(report)));
            assertEquals(definition.reports().size() + 2, written.size());
            assertTrue(Files.readString(root.resolve("reports").resolve(definition.reports().getLast()))
                    .contains("\"external_operation_executed\" : false"));
        }
    }

    @Test
    void requestRejectsArtifactWorkspaceInsideRepository() {
        Path repository = temporary.resolve("repository");
        assertThrows(IllegalArgumentException.class, () -> new Request(
                repository.resolve("artifacts"), repository, "program", "v1", "org", "owner", NOW,
                List.of("admission-evidence")));
    }

    private Request request() {
        return new Request(temporary.resolve("evidence"), temporary.resolve("repository"),
                "program-1", "source-v1", "org-1", "owner-1", NOW,
                List.of("admission-evidence"));
    }

    private static GateEvidence passed(ProgramDefinition definition, Request request, GateDefinition gate) {
        return new GateEvidence(definition.batch(), request.programId(), request.sourceVersion(),
                request.organizationId(), gate.id(), EvidenceStatus.PASSED, 1.0,
                true, true, true, 0, "authority-" + gate.id(), NOW,
                List.of("evidence-" + gate.id()), false);
    }
}
