package io.elmos.verification;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

import static io.elmos.verification.VerificationModels.*;

public final class MutationVerificationEngine {
    public record Mutant<I,O>(String id, boolean critical, Function<I,O> behavior) {
        public Mutant { VerificationModels.requireText(id,"mutant id"); }
    }
    public record MutationResult(Status status, int total, int killed, double score,
                                 List<String> survivingMutants, List<String> survivingCriticalMutants,
                                 Map<String,String> killEvidence) {
        public MutationResult {
            survivingMutants=List.copyOf(survivingMutants); survivingCriticalMutants=List.copyOf(survivingCriticalMutants);
            killEvidence=Map.copyOf(killEvidence);
        }
    }

    public <I,O> MutationResult verify(List<I> inputs, Function<I,O> reference,
                                       List<Mutant<I,O>> mutants, double requiredScore) {
        if (inputs.isEmpty() || mutants.isEmpty() || requiredScore<0 || requiredScore>1) throw new IllegalArgumentException("mutation corpus, mutants and threshold are required");
        List<String> survivors=new ArrayList<>(),critical=new ArrayList<>(); Map<String,String> evidence=new LinkedHashMap<>(); int killed=0;
        for (Mutant<I,O> mutant:mutants) {
            String witness=null;
            for (I input:inputs) {
                O expected=reference.apply(input); O observed=mutant.behavior().apply(input);
                if (!java.util.Objects.equals(expected,observed)) { witness=String.valueOf(input); break; }
            }
            if (witness==null) { survivors.add(mutant.id()); if (mutant.critical()) critical.add(mutant.id()); }
            else { killed++; evidence.put(mutant.id(),CounterexampleFactory.digest(mutant.id()+"\0"+witness)); }
        }
        double score=killed/(double)mutants.size(); Status status=score>=requiredScore&&critical.isEmpty()?Status.PASS:Status.FAIL;
        return new MutationResult(status,mutants.size(),killed,score,survivors,critical,evidence);
    }
}
