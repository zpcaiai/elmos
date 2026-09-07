package io.elmos.verification;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Random;

import static io.elmos.verification.VerificationModels.*;

public final class PropertyVerificationEngine {
    @FunctionalInterface public interface Generator<T> { T generate(Random random, int caseIndex); }
    @FunctionalInterface public interface Property<T> { Optional<String> violation(T value); }
    @FunctionalInterface public interface Shrinker<T> { List<T> candidates(T value); }

    public <T> TechniqueResult verify(String propertyId, Budget budget, Generator<T> generator,
                                      Property<T> property, Shrinker<T> shrinker) {
        Random random=new Random(budget.seed()); List<Counterexample> failures=new ArrayList<>(); int executed=0;
        for (int index=0;index<budget.maximumCases();index++) {
            T value=generator.generate(random,index); executed++;
            Optional<String> violation=property.violation(value);
            if (violation.isPresent()) {
                T minimized=shrink(value,property,shrinker,budget.maximumShrinkSteps());
                failures.add(CounterexampleFactory.create("property",propertyId,budget.seed(),value,minimized,violation.get()));
                break;
            }
        }
        return new TechniqueResult("property",propertyId,failures.isEmpty()?Status.PASS:Status.FAIL,executed,
                executed/(double)budget.maximumCases(),failures,List.of(),List.of("local://property/seed/"+budget.seed()),
                Map.of("configured_cases",budget.maximumCases(),"executed_cases",executed));
    }

    private static <T> T shrink(T original, Property<T> property, Shrinker<T> shrinker, int maximumSteps) {
        T current=original; int steps=0; boolean changed=true;
        while (changed && steps<maximumSteps) {
            changed=false;
            for (T candidate:shrinker.candidates(current)) {
                steps++;
                if (property.violation(candidate).isPresent()) { current=candidate; changed=true; break; }
                if (steps>=maximumSteps) break;
            }
        }
        return current;
    }
}
