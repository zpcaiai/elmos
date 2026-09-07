package io.elmos.verification;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiPredicate;
import java.util.function.Function;

import static io.elmos.verification.VerificationModels.*;

public final class MetamorphicVerificationEngine {
    public <I,O> TechniqueResult verify(String relationId, List<I> inputs, Function<I,I> transformation,
                                        Function<I,O> subject, BiPredicate<O,O> relation,
                                        int maximumCases, long seed) {
        if (maximumCases<1) throw new IllegalArgumentException("metamorphic case budget must be positive");
        List<Counterexample> failures=new ArrayList<>(); int executed=0;
        for (I input:inputs) {
            if (executed>=maximumCases) break;
            I transformed=transformation.apply(input); O originalOutput=subject.apply(input); O transformedOutput=subject.apply(transformed); executed++;
            if (!relation.test(originalOutput,transformedOutput)) {
                String pair="input="+input+",transformed="+transformed+",outputs="+originalOutput+"/"+transformedOutput;
                failures.add(CounterexampleFactory.create("metamorphic",relationId,seed,pair,pair,"RELATION_VIOLATED"));
                break;
            }
        }
        Status status=inputs.isEmpty()?Status.UNKNOWN:failures.isEmpty()?Status.PASS:Status.FAIL;
        List<String> unknowns=inputs.isEmpty()?List.of("INPUT_CORPUS_EMPTY"):List.of();
        return new TechniqueResult("metamorphic",relationId,status,executed,
                inputs.isEmpty()?0:Math.min(1,executed/(double)Math.min(maximumCases,inputs.size())),failures,unknowns,
                List.of("local://metamorphic/"+relationId),Map.of("configured_cases",maximumCases,"executed_cases",executed));
    }
}
