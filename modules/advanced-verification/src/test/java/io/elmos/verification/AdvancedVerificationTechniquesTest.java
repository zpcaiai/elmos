package io.elmos.verification;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;
import static org.junit.jupiter.api.Assertions.*;

class AdvancedVerificationTechniquesTest {
    @Test void propertyRunsAreSeededBoundedAndShrinkFailures() {
        PropertyVerificationEngine engine=new PropertyVerificationEngine();
        Budget budget=new Budget(100,10,20,42,1024);
        var failed=engine.verify("minimum-five",budget,(random,index)->5+random.nextInt(96),
                value->value>=5?Optional.of("VALUE_NOT_BELOW_FIVE"):Optional.empty(),
                value->value<=5?List.of():List.of(Math.max(5,value/2)));
        assertEquals(Status.FAIL,failed.status()); assertEquals(1,failed.counterexamples().size());
        assertEquals("5",failed.counterexamples().getFirst().minimizedInput());
        var replayed=engine.verify("minimum-five",budget,(random,index)->5+random.nextInt(96),
                value->value>=5?Optional.of("VALUE_NOT_BELOW_FIVE"):Optional.empty(),
                value->value<=5?List.of():List.of(Math.max(5,value/2)));
        assertEquals(failed.counterexamples().getFirst().failureFingerprint(),replayed.counterexamples().getFirst().failureFingerprint());
    }

    @Test void propertyPassDoesNotClaimMoreThanConfiguredCases() {
        var result=new PropertyVerificationEngine().verify("square-nonnegative",new Budget(50,10,5,7,128),
                (random,index)->random.nextInt(1000),value->(long)value*value>=0?Optional.empty():Optional.of("NEGATIVE_SQUARE"),value->List.of());
        assertEquals(Status.PASS,result.status()); assertEquals(50,result.executedCases()); assertEquals(1,result.coverage());
    }

    @Test void metamorphicRelationsDetectBrokenBusinessRelationships() {
        MetamorphicVerificationEngine engine=new MetamorphicVerificationEngine();
        var pass=engine.verify("translation-invariance",List.of(1,2,3),value->value+10,value->value*2,
                (original,transformed)->transformed-original==20,10,1);
        assertEquals(Status.PASS,pass.status());
        var fail=engine.verify("incorrect-invariance",List.of(1,2),value->value+1,value->value*value,
                Integer::equals,10,1);
        assertEquals(Status.FAIL,fail.status()); assertEquals("RELATION_VIOLATED",fail.counterexamples().getFirst().failureCode());
    }

    @Test void mutationScoreCannotHideSurvivingCriticalMutants() {
        MutationVerificationEngine engine=new MutationVerificationEngine();
        List<Integer> inputs=List.of(-1,0,1,2);
        var result=engine.verify(inputs,value->value+1,List.of(
                new MutationVerificationEngine.Mutant<>("subtract",true,value->value-1),
                new MutationVerificationEngine.Mutant<>("equivalent",true,value->value+1)),.5);
        assertEquals(.5,result.score()); assertEquals(Status.FAIL,result.status());
        assertEquals(List.of("equivalent"),result.survivingCriticalMutants());
        assertTrue(result.killEvidence().containsKey("subtract"));
    }

    @Test void structuredFuzzingPersistsSeedCoverageAndCrashFingerprint() {
        StructuredFuzzEngine engine=new StructuredFuzzEngine(); Budget budget=new Budget(10,4,0,99,8);
        var result=engine.fuzz("binary-boundary",budget,(random,index)->new byte[]{(byte)(index==3?0x7f:index)},input->{
            if (input[0]==0x7f) return StructuredFuzzEngine.Observation.failure("MAGIC_CRASH","parsed","magic");
            return StructuredFuzzEngine.Observation.success("parsed","ordinary");
        });
        assertEquals(Status.FAIL,result.status()); assertEquals(4,result.executedCases());
        assertEquals("MAGIC_CRASH",result.counterexamples().getFirst().failureCode());
        assertTrue(result.evidenceRefs().getFirst().contains("99"));
    }

    @Test void fuzzingRejectsOversizedInputsWithoutExecutingThem() {
        var result=new StructuredFuzzEngine().fuzz("size-policy",new Budget(3,2,0,1,2),
                (random,index)->"oversized".getBytes(StandardCharsets.UTF_8),input->fail("oversized input executed"));
        assertEquals(Status.PASS,result.status()); assertEquals(0,result.executedCases());
        assertEquals(List.of("OVERSIZED_INPUTS_REJECTED:3"),result.unknowns());
    }

    @Test void modelVerificationChecksTransitionsAndLiveness() {
        ModelProtocolVerifier.Model model=new ModelProtocolVerifier.Model("job",
                Set.of("queued","running","done"),"queued",Set.of("done"),List.of(
                new ModelProtocolVerifier.Transition("start","queued","running"),
                new ModelProtocolVerifier.Transition("finish","running","done")),Set.of("done|start|running"));
        var pass=new ModelProtocolVerifier().verify(model,(state,command)->switch(state+":"+command) {
            case "queued:start" -> "running"; case "running:finish" -> "done"; default -> state;
        },10);
        assertEquals(Status.PASS,pass.status()); assertEquals(1,pass.coverage());
        var fail=new ModelProtocolVerifier().verify(model,(state,command)->"running",10);
        assertEquals(Status.FAIL,fail.status());
    }
}
