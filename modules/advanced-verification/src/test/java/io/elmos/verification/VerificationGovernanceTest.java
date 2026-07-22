package io.elmos.verification;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;
import static org.junit.jupiter.api.Assertions.*;

class VerificationGovernanceTest {
    @Test void scheduleExplorationFindsAndReplaysLostUpdate() {
        DeterministicScheduleExplorer explorer=new DeterministicScheduleExplorer();
        var t1=List.of(new DeterministicScheduleExplorer.Operation("t1","read"),new DeterministicScheduleExplorer.Operation("t1","write"));
        var t2=List.of(new DeterministicScheduleExplorer.Operation("t2","read"),new DeterministicScheduleExplorer.Operation("t2","write"));
        var result=explorer.explore("counter-increment",List.of(t1,t2),Set.of("LOST_UPDATE"),10,this::counterOutcome);
        assertEquals(Status.FAIL,result.status()); assertTrue(result.executedCases()<=6);
        assertEquals("FORBIDDEN_OUTCOME:LOST_UPDATE",result.counterexamples().getFirst().failureCode());
        var bounded=explorer.explore("counter-increment",List.of(t1,t2),Set.of("IMPOSSIBLE"),2,this::counterOutcome);
        assertEquals(Status.UNKNOWN,bounded.status()); assertTrue(bounded.unknowns().contains("SCHEDULE_BUDGET_EXHAUSTED"));
    }

    @Test void finiteDomainProofDistinguishesProvedDisprovedUnknownAndUnsupported() {
        BoundedProofEngine engine=new BoundedProofEngine(); List<Integer> domain=List.of(0,1,2,3);
        var proved=engine.proveFiniteDomain("bounded-square",domain,value->value*value>=0,10,List.of("domain is exactly 0..3"));
        assertEquals(ProofStatus.PROVED_WITHIN_DECLARED_FINITE_DOMAIN,proved.status()); assertEquals(4,proved.exploredStates());
        var disproved=engine.proveFiniteDomain("less-than-three",domain,value->value<3,10,List.of());
        assertEquals(ProofStatus.DISPROVED,disproved.status()); assertEquals(3,disproved.witness());
        assertEquals(ProofStatus.UNKNOWN_BUDGET_EXHAUSTED,engine.proveFiniteDomain("budgeted",domain,value->true,2,List.of()).status());
        assertEquals(ProofStatus.UNSUPPORTED,engine.unsupported("unbounded-integer-proof","SMT_SOLVER_NOT_CONFIGURED").status());
    }

    @Test void numericVerificationUsesExplicitScaleRoundingToleranceAndOverflow() {
        NumericVerificationEngine engine=new NumericVerificationEngine(); List<BigDecimal> inputs=List.of(new BigDecimal("1.005"),new BigDecimal("2.335"));
        var pass=engine.verifyDecimal("money-rounding",inputs,value->value,value->value,2,RoundingMode.HALF_EVEN,BigDecimal.ZERO);
        assertEquals(Status.PASS,pass.status());
        var fail=engine.verifyDecimal("money-regression",inputs,value->value,value->value.add(new BigDecimal("0.02")),2,RoundingMode.HALF_EVEN,new BigDecimal("0.01"));
        assertEquals(Status.FAIL,fail.status());
        assertEquals(Status.FAIL,engine.verifyIntegerAdditionNoOverflow("long-add",List.of(Long.MAX_VALUE),List.of(1L)).status());
    }

    @Test void conservationSecurityAndQueryOraclesAreDeterministic() {
        CrossDomainInvariantVerifier verifier=new CrossDomainInvariantVerifier();
        assertEquals(Status.PASS,verifier.verifyConservation("ledger-total",List.of(new BigDecimal("10.00"),new BigDecimal("5.00")),List.of(new BigDecimal("7.00"),new BigDecimal("8.00"))).status());
        assertEquals(Status.FAIL,verifier.verifyConservation("ledger-loss",List.of(BigDecimal.TEN),List.of(new BigDecimal("9.99"))).status());
        var denied=new CrossDomainInvariantVerifier.DeniedActionObservation("deny-1",true,"sha256:same","sha256:same","tenant-a","tenant-a");
        assertEquals(Status.PASS,verifier.verifyDeniedActions("denied-no-effect",List.of(denied)).status());
        var changed=new CrossDomainInvariantVerifier.DeniedActionObservation("deny-2",true,"before","after","tenant-a","tenant-a");
        assertEquals(Status.FAIL,verifier.verifyDeniedActions("denied-no-effect",List.of(changed)).status());
        List<Map<String,Object>> source=List.of(Map.of("id",1,"name","a"),Map.of("id",2,"name","b"));
        List<Map<String,Object>> target=List.of(Map.of("name","b","id",2),Map.of("name","a","id",1));
        assertEquals(Status.PASS,verifier.verifyCanonicalQueryRows("query-order-independent",source,target).status());
    }

    @Test void oracleGovernanceRequiresIndependenceAndBlocksConflict() {
        OracleGovernance governance=new OracleGovernance();
        governance.register(new OracleGovernance.Oracle("business","owner",OracleGovernance.OracleType.BUSINESS_RULE,OracleGovernance.Trust.AUTHORITATIVE,"business","v1",List.of("rule.json")));
        governance.register(new OracleGovernance.Oracle("model","owner",OracleGovernance.OracleType.FORMAL_SPECIFICATION,OracleGovernance.Trust.STRONG,"formal","v1",List.of("model.json")));
        assertThrows(IllegalArgumentException.class,()->governance.register(new OracleGovernance.Oracle("llm","owner",OracleGovernance.OracleType.LLM_ADVISORY,OracleGovernance.Trust.AUTHORITATIVE,"model","v1",List.of())));
        var pass=governance.resolve("claim",Criticality.P0,List.of(
                new OracleGovernance.Observation("business",Status.PASS,"a",List.of("a")),
                new OracleGovernance.Observation("model",Status.PASS,"b",List.of("b"))));
        assertEquals(Status.PASS,pass.status());
        var conflict=governance.resolve("claim",Criticality.P0,List.of(
                new OracleGovernance.Observation("business",Status.PASS,"a",List.of("a")),
                new OracleGovernance.Observation("model",Status.FAIL,"b",List.of("b"))));
        assertEquals(Status.BLOCKED,conflict.status()); assertTrue(conflict.blockers().contains("UNRESOLVED_ORACLE_CONFLICT"));
    }

    @Test void counterexampleReplayMustMatchFailureFingerprintSemantics() {
        var result=new PropertyVerificationEngine().verify("replayable",new Budget(1,1,0,5,10),
                (random,index)->7,value->java.util.Optional.of("FAILURE"),value->List.of());
        Counterexample counterexample=result.counterexamples().getFirst(); CounterexampleReplayRegistry registry=new CounterexampleReplayRegistry();
        registry.register(counterexample,()->"FAILURE");
        assertTrue(registry.replay(counterexample.failureFingerprint()).fingerprintMatched());
        assertFalse(registry.replay("sha256:missing").replayed());
    }

    @Test void assuranceCasePreservesUnsupportedClaimsAndResidualRiskOwnership() {
        AssuranceCaseBuilder builder=new AssuranceCaseBuilder();
        var supported=new AssuranceCaseBuilder.Claim("claim-1",Criticality.P0,Status.PASS,List.of("evidence.json"),List.of(),List.of("finite corpus"),true);
        var accepted=new AssuranceCaseBuilder.ResidualRisk("risk-1","risk-owner","monitor production regression","approval-1");
        assertEquals(Status.PASS,builder.build("case",List.of(supported),List.of(accepted),Map.of("property",1d,"mutation",.9)).status());
        var unsupported=new AssuranceCaseBuilder.Claim("claim-2",Criticality.P0,Status.UNKNOWN,List.of(),List.of(),List.of(),false);
        var blocked=builder.build("case",List.of(unsupported),List.of(),Map.of("property",.5));
        assertEquals(Status.BLOCKED,blocked.status()); assertTrue(blocked.blockers().stream().anyMatch(value->value.startsWith("CLAIM_NOT_SUPPORTED")));
    }

    private String counterOutcome(List<DeterministicScheduleExplorer.Operation> schedule) {
        int value=0; Map<String,Integer> reads=new HashMap<>();
        for (var operation:schedule) {
            if (operation.operationId().equals("read")) reads.put(operation.threadId(),value);
            else value=reads.get(operation.threadId())+1;
        }
        return value==2?"SERIALIZABLE":"LOST_UPDATE";
    }
}
