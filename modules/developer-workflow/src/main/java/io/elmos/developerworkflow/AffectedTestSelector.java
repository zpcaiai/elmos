package io.elmos.developerworkflow;

import java.util.ArrayDeque;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class AffectedTestSelector {
    private final Map<String, Set<String>> dependencies;
    private final Map<String, Set<String>> testsBySymbol;

    public AffectedTestSelector(Map<String, Set<String>> dependencies, Map<String, Set<String>> testsBySymbol) {
        this.dependencies = Map.copyOf(dependencies);
        this.testsBySymbol = Map.copyOf(testsBySymbol);
    }

    public TestSelection select(Set<String> changedSymbols, int maxSymbols, int maxTests) {
        if (changedSymbols.isEmpty()) return new TestSelection(Decision.DENY,"CHANGED_SYMBOL_REQUIRED",Set.of(),java.util.List.of());
        ArrayDeque<String> queue=new ArrayDeque<>(changedSymbols); Set<String> visited=new LinkedHashSet<>(); Set<String> tests=new LinkedHashSet<>();
        while (!queue.isEmpty()) {
            String symbol=queue.removeFirst();
            if (!visited.add(symbol)) continue;
            if (visited.size()>maxSymbols) return new TestSelection(Decision.ESCALATE,"IMPACT_BUDGET_EXCEEDED",tests,java.util.List.of("run:broader-suite"));
            if (!dependencies.containsKey(symbol) && !testsBySymbol.containsKey(symbol)) return new TestSelection(Decision.ESCALATE,"UNKNOWN_IMPACT_EDGE",tests,java.util.List.of(symbol));
            tests.addAll(testsBySymbol.getOrDefault(symbol,Set.of()));
            if (tests.size()>maxTests) return new TestSelection(Decision.ESCALATE,"TEST_BUDGET_EXCEEDED",tests,java.util.List.of("run:broader-suite"));
            dependencies.getOrDefault(symbol,Set.of()).stream().sorted().forEach(queue::addLast);
        }
        return new TestSelection(Decision.ALLOW,"AFFECTED_TESTS_SELECTED",tests,java.util.List.of("symbols:"+visited.size()));
    }
}
