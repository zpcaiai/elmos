package io.elmos.companyseries;

import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable, evidence-bound contracts shared by authoritative company-series Batches 15-18. */
public final class CompanySeriesModels {
    private CompanySeriesModels() {}

    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, INCONCLUSIVE, NOT_APPLICABLE, BLOCKED }

    public record GateDefinition(String id, String label) {
        public GateDefinition { text(id, "id"); text(label, "label"); }
    }

    public record ProgramDefinition(int batch, String title, String model, String version,
                                    String finalStatus, List<GateDefinition> gates,
                                    List<String> dimensions, String artifactRoot,
                                    List<String> artifactDirectories, List<String> reports) {
        public ProgramDefinition {
            if (batch < 15 || batch > 18) throw new IllegalArgumentException("batch must be 15-18");
            text(title, "title"); text(model, "model"); text(version, "version");
            text(finalStatus, "finalStatus"); text(artifactRoot, "artifactRoot");
            gates = nonempty(gates, "gates"); dimensions = nonempty(dimensions, "dimensions");
            artifactDirectories = nonempty(artifactDirectories, "artifactDirectories");
            reports = nonempty(reports, "reports");
            if (new HashSet<>(gates.stream().map(GateDefinition::id).toList()).size() != gates.size())
                throw new IllegalArgumentException("gate IDs must be unique");
        }
        public String finalGate() { return gates.getLast().id(); }
    }

    public record Request(Path artifactWorkspace, Path repositoryPath, String programId,
                          String sourceVersion, String organizationId, String humanOwnerId,
                          Instant observedAt, List<String> admissionEvidenceRefs) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(repositoryPath, "repositoryPath");
            text(programId, "programId"); text(sourceVersion, "sourceVersion");
            text(organizationId, "organizationId"); text(humanOwnerId, "humanOwnerId");
            required(observedAt, "observedAt");
            admissionEvidenceRefs = nonempty(admissionEvidenceRefs, "admissionEvidenceRefs");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            Path repository = repositoryPath.toAbsolutePath().normalize();
            if (workspace.startsWith(repository))
                throw new IllegalArgumentException("company-series evidence workspace must be outside the repository");
        }
    }

    public record GateEvidence(int batch, String programId, String sourceVersion,
                               String organizationId, String gate, EvidenceStatus status,
                               double coverage, boolean tenantBoundaryPassed,
                               boolean legalAndPolicyPassed, boolean humanAccountabilityPassed,
                               int criticalOpenRisks, String authorityId, Instant observedAt,
                               List<String> evidenceRefs, boolean externalOperationExecuted) {
        public GateEvidence {
            if (batch < 15 || batch > 18) throw new IllegalArgumentException("batch must be 15-18");
            text(programId, "programId"); text(sourceVersion, "sourceVersion");
            text(organizationId, "organizationId"); text(gate, "gate"); required(status, "status");
            if (!Double.isFinite(coverage) || coverage < 0 || coverage > 1)
                throw new IllegalArgumentException("coverage must be between zero and one");
            if (criticalOpenRisks < 0) throw new IllegalArgumentException("criticalOpenRisks must be non-negative");
            text(authorityId, "authorityId"); required(observedAt, "observedAt");
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
            if (externalOperationExecuted)
                throw new IllegalArgumentException("company-series control plane cannot execute external operations");
        }
    }

    public record ConformanceReport(int batch, String model, String programId,
                                    String sourceVersion, String organizationId, String gate,
                                    String status, boolean ready, boolean evidenceComplete,
                                    List<String> supportedDimensions, List<String> blockers,
                                    List<String> restrictions, Instant evaluatedAt,
                                    List<String> evidenceRefs, boolean externalOperationExecuted) {
        public ConformanceReport {
            text(model, "model"); text(programId, "programId"); text(sourceVersion, "sourceVersion");
            text(organizationId, "organizationId"); text(gate, "gate"); text(status, "status");
            supportedDimensions = copy(supportedDimensions); blockers = copy(blockers);
            restrictions = nonempty(restrictions, "restrictions"); required(evaluatedAt, "evaluatedAt");
            evidenceRefs = copy(evidenceRefs);
            if (externalOperationExecuted)
                throw new IllegalArgumentException("conformance reports cannot claim external execution");
        }
    }

    public record Outcome(ProgramDefinition definition, Request request,
                          Map<String, GateEvidence> gateEvidence, ConformanceReport report) {
        public Outcome {
            required(definition, "definition"); required(request, "request"); required(report, "report");
            gateEvidence = gateEvidence == null ? Map.of() : Map.copyOf(gateEvidence);
            if (report.ready() && (!report.gate().equals(definition.finalGate())
                    || !report.status().equals(definition.finalStatus())
                    || !report.evidenceComplete() || !report.blockers().isEmpty()))
                throw new IllegalArgumentException("ready requires the exact final gate and complete external evidence");
        }
    }

    @FunctionalInterface
    public interface EvidenceAuthority {
        GateEvidence observe(Request request, GateDefinition gate);
    }

    public record AuthorityRegistry(Map<String, EvidenceAuthority> authorities) {
        public AuthorityRegistry { authorities = authorities == null ? Map.of() : Map.copyOf(authorities); }
        EvidenceAuthority authorityFor(String gate) { return authorities.get(gate); }
    }

    static void text(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static <T> T required(T value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " is required");
        return value;
    }
    static <T> List<T> nonempty(List<T> values, String field) {
        if (values == null || values.isEmpty() || values.stream().anyMatch(Objects::isNull))
            throw new IllegalArgumentException(field + " must not be empty");
        return List.copyOf(values);
    }
    static <T> List<T> copy(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
}
