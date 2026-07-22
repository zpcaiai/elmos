package io.elmos.verification;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;

public final class StructuredFuzzEngine {
    @FunctionalInterface public interface StructuredGenerator { byte[] generate(Random random, int caseIndex); }
    @FunctionalInterface public interface Target { Observation execute(byte[] input); }
    public record Observation(Set<String> coverageSignals, String failureCode) {
        public Observation { coverageSignals=Set.copyOf(coverageSignals); }
        public static Observation success(String... signals) { return new Observation(Set.of(signals),null); }
        public static Observation failure(String code,String... signals) { return new Observation(Set.of(signals),code); }
    }

    public TechniqueResult fuzz(String campaignId, Budget budget, StructuredGenerator generator, Target target) {
        Random random=new Random(budget.seed()); Set<String> coverage=new LinkedHashSet<>(); List<Counterexample> failures=new ArrayList<>();
        int executed=0,oversized=0;
        for (int index=0;index<budget.maximumCases();index++) {
            byte[] input=generator.generate(random,index);
            if (input.length>budget.maximumInputBytes()) { oversized++; continue; }
            executed++;
            Observation observation;
            try { observation=target.execute(input); }
            catch (RuntimeException error) { observation=Observation.failure("UNCAUGHT_"+error.getClass().getSimpleName(),"exception"); }
            coverage.addAll(observation.coverageSignals());
            if (observation.failureCode()!=null) {
                String encoded=java.util.HexFormat.of().formatHex(input);
                failures.add(CounterexampleFactory.create("fuzz",campaignId,budget.seed(),encoded,encoded,observation.failureCode()));
                break;
            }
        }
        Status status=failures.isEmpty()?Status.PASS:Status.FAIL;
        return new TechniqueResult("fuzz",campaignId,status,executed,
                Math.min(1,coverage.size()/(double)Math.max(1,budget.maximumStates())),failures,
                oversized==0?List.of():List.of("OVERSIZED_INPUTS_REJECTED:"+oversized),
                List.of("local://fuzz/seed/"+budget.seed()),Map.of("coverage_signals",coverage.size(),"rejected_oversized",oversized));
    }
}
