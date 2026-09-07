package io.elmos.verification;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.verification.VerificationModels.*;

public final class ModelProtocolVerifier {
    public record Transition(String command, String from, String to) {
        public Transition { VerificationModels.requireText(command,"transition command"); VerificationModels.requireText(from,"transition source"); VerificationModels.requireText(to,"transition target"); }
    }
    public record Model(String id, Set<String> states, String initialState, Set<String> terminalStates,
                        List<Transition> transitions, Set<String> forbiddenTriples) {
        public Model {
            VerificationModels.requireText(id,"model id"); states=Set.copyOf(states); terminalStates=Set.copyOf(terminalStates);
            transitions=List.copyOf(transitions); forbiddenTriples=Set.copyOf(forbiddenTriples);
            if (!states.contains(initialState) || !states.containsAll(terminalStates)) throw new IllegalArgumentException("model states are incomplete");
            for (Transition transition:transitions) if (!states.contains(transition.from())||!states.contains(transition.to())) throw new IllegalArgumentException("transition references unknown state");
        }
    }
    @FunctionalInterface public interface Implementation { String apply(String state,String command); }

    public TechniqueResult verify(Model model, Implementation implementation, int maximumStates) {
        if (maximumStates<1) throw new IllegalArgumentException("state budget must be positive");
        List<Counterexample> failures=new ArrayList<>(); int executed=0; Set<String> covered=new HashSet<>();
        for (Transition transition:model.transitions()) {
            if (executed>=maximumStates) break; executed++;
            String observed;
            try { observed=implementation.apply(transition.from(),transition.command()); }
            catch (RuntimeException error) { observed="EXCEPTION:"+error.getClass().getSimpleName(); }
            String triple=transition.from()+"|"+transition.command()+"|"+observed;
            if (model.forbiddenTriples().contains(triple) || !transition.to().equals(observed)) {
                failures.add(CounterexampleFactory.create("model",model.id(),0,triple,triple,"TRANSITION_MISMATCH")); break;
            }
            covered.add(transition.from()+"|"+transition.command()+"|"+transition.to());
        }
        List<String> unknowns=new ArrayList<>();
        if (!allStatesCanReachTerminal(model)) unknowns.add("LIVENESS_PATH_TO_TERMINAL_MISSING");
        if (executed<model.transitions().size()) unknowns.add("STATE_BUDGET_EXHAUSTED");
        Status status=!failures.isEmpty()?Status.FAIL:unknowns.isEmpty()?Status.PASS:Status.UNKNOWN;
        return new TechniqueResult("model",model.id(),status,executed,model.transitions().isEmpty()?0:covered.size()/(double)model.transitions().size(),
                failures,unknowns,List.of("local://model/"+model.id()),Map.of("states",model.states().size(),"transitions",model.transitions().size()));
    }

    private static boolean allStatesCanReachTerminal(Model model) {
        Map<String,List<String>> reverse=new HashMap<>();
        for (Transition transition:model.transitions()) reverse.computeIfAbsent(transition.to(),ignored->new ArrayList<>()).add(transition.from());
        Set<String> reachable=new HashSet<>(model.terminalStates()); ArrayDeque<String> queue=new ArrayDeque<>(model.terminalStates());
        while (!queue.isEmpty()) for (String prior:reverse.getOrDefault(queue.remove(),List.of())) if (reachable.add(prior)) queue.add(prior);
        return reachable.containsAll(model.states());
    }
}
