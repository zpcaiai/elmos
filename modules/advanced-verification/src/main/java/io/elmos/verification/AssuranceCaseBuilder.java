package io.elmos.verification;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static io.elmos.verification.VerificationModels.*;

public final class AssuranceCaseBuilder {
    public record Claim(String id,Criticality criticality,Status status,List<String> evidenceRefs,
                        List<String> assumptions,List<String> limitations,boolean independentlyReviewed) {
        public Claim { VerificationModels.requireText(id,"assurance claim"); evidenceRefs=List.copyOf(evidenceRefs); assumptions=List.copyOf(assumptions); limitations=List.copyOf(limitations); }
    }
    public record ResidualRisk(String id,String owner,String monitoringObligation,String acceptanceRef) {
        public ResidualRisk { VerificationModels.requireText(id,"residual risk"); VerificationModels.requireText(owner,"residual risk owner"); VerificationModels.requireText(monitoringObligation,"monitoring obligation"); }
    }
    public record AssuranceCase(String id,Status status,List<Claim> claims,List<ResidualRisk> residualRisks,
                                Map<String,Double> coverage,List<String> blockers) {
        public AssuranceCase { claims=List.copyOf(claims); residualRisks=List.copyOf(residualRisks); coverage=Map.copyOf(coverage); blockers=List.copyOf(blockers); }
    }

    public AssuranceCase build(String id,List<Claim> claims,List<ResidualRisk> risks,Map<String,Double> coverage) {
        if (claims.isEmpty()) throw new IllegalArgumentException("assurance claims are required"); List<String> blockers=new ArrayList<>();
        for (Claim claim:claims) {
            if (claim.status()!=Status.PASS) blockers.add("CLAIM_NOT_SUPPORTED:"+claim.id()+":"+claim.status());
            if (claim.evidenceRefs().isEmpty()) blockers.add("CLAIM_EVIDENCE_MISSING:"+claim.id());
            if (claim.criticality()==Criticality.P0&&!claim.independentlyReviewed()) blockers.add("P0_INDEPENDENT_REVIEW_MISSING:"+claim.id());
        }
        for (ResidualRisk risk:risks) if (risk.acceptanceRef()==null||risk.acceptanceRef().isBlank()) blockers.add("RESIDUAL_RISK_NOT_ACCEPTED:"+risk.id());
        for (var metric:coverage.entrySet()) if (metric.getValue()<0||metric.getValue()>1) blockers.add("INVALID_COVERAGE:"+metric.getKey());
        return new AssuranceCase(id,blockers.isEmpty()?Status.PASS:Status.BLOCKED,claims,risks,coverage,blockers);
    }
}
