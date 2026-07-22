package io.elmos.verification;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;

public final class OracleGovernance {
    public enum OracleType { FORMAL_SPECIFICATION, BUSINESS_RULE, SOURCE_BEHAVIOR, EXISTING_TEST, RUNTIME_OBSERVATION, HUMAN_REVIEW, LLM_ADVISORY }
    public enum Trust { AUTHORITATIVE, STRONG, SUPPORTING, ADVISORY }
    public record Oracle(String id,String owner,OracleType type,Trust trust,String independenceGroup,String version,List<String> evidenceRefs) {
        public Oracle {
            VerificationModels.requireText(id,"oracle id"); VerificationModels.requireText(owner,"oracle owner");
            VerificationModels.requireText(independenceGroup,"oracle independence group"); VerificationModels.requireText(version,"oracle version");
            evidenceRefs=List.copyOf(evidenceRefs);
            if (type==OracleType.LLM_ADVISORY && (trust==Trust.AUTHORITATIVE||trust==Trust.STRONG)) throw new IllegalArgumentException("LLM oracle cannot be authoritative or strong");
        }
    }
    public record Observation(String oracleId,Status status,String resultDigest,List<String> evidenceRefs) {
        public Observation { VerificationModels.requireText(oracleId,"observation oracle"); evidenceRefs=List.copyOf(evidenceRefs); }
    }
    public record Decision(String claimId,Status status,List<String> supportingOracles,
                           List<String> conflictingOracles,List<String> blockers) {
        public Decision { supportingOracles=List.copyOf(supportingOracles); conflictingOracles=List.copyOf(conflictingOracles); blockers=List.copyOf(blockers); }
    }

    private final Map<String,Oracle> registry=new HashMap<>();
    public void register(Oracle oracle) { if (registry.putIfAbsent(oracle.id(),oracle)!=null) throw new IllegalArgumentException("duplicate oracle"); }

    public Decision resolve(String claimId,Criticality criticality,List<Observation> observations) {
        VerificationModels.requireText(claimId,"claim id"); List<String> pass=new ArrayList<>(),fail=new ArrayList<>(),blockers=new ArrayList<>(); Set<String> independent=new HashSet<>();
        for (Observation observation:observations) {
            Oracle oracle=registry.get(observation.oracleId()); if (oracle==null) { blockers.add("UNKNOWN_ORACLE:"+observation.oracleId()); continue; }
            if (observation.status()==Status.PASS) { pass.add(oracle.id()); independent.add(oracle.independenceGroup()); }
            else if (observation.status()==Status.FAIL) fail.add(oracle.id());
            else blockers.add("ORACLE_INCONCLUSIVE:"+oracle.id()+":"+observation.status());
        }
        if (!pass.isEmpty()&&!fail.isEmpty()) return new Decision(claimId,Status.BLOCKED,pass,fail,List.of("UNRESOLVED_ORACLE_CONFLICT"));
        boolean authoritativeFailure=fail.stream().map(registry::get).anyMatch(oracle->oracle.trust()==Trust.AUTHORITATIVE);
        if (authoritativeFailure || (!fail.isEmpty()&&pass.isEmpty())) return new Decision(claimId,Status.FAIL,pass,fail,blockers);
        int required=criticality==Criticality.P0?2:1;
        if (independent.size()<required) blockers.add("INDEPENDENT_ORACLES_BELOW_REQUIRED:"+independent.size()+"<"+required);
        Status status=blockers.isEmpty()&&!pass.isEmpty()?Status.PASS:Status.UNKNOWN;
        return new Decision(claimId,status,pass,fail,blockers);
    }
}
