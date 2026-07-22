package io.elmos.verification;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class VerificationModels {
    private VerificationModels() {}

    public enum Status { PASS, FAIL, UNKNOWN, NOT_RUN, UNSUPPORTED, BLOCKED }
    public enum ProofStatus { PROVED_WITHIN_DECLARED_FINITE_DOMAIN, DISPROVED, UNKNOWN_BUDGET_EXHAUSTED, UNSUPPORTED }
    public enum Criticality { P0, P1, P2, P3 }

    public record Budget(int maximumCases, int maximumStates, int maximumShrinkSteps,
                         long seed, long maximumInputBytes) {
        public Budget {
            if (maximumCases < 1 || maximumStates < 1 || maximumShrinkSteps < 0 || maximumInputBytes < 1) {
                throw new IllegalArgumentException("verification budgets must be positive and bounded");
            }
        }
    }

    public record Counterexample(String technique, String propertyId, long seed,
                                 String originalInput, String minimizedInput,
                                 String failureCode, String failureFingerprint,
                                 String replayCommand, List<String> evidenceRefs) {
        public Counterexample {
            requireText(technique, "counterexample technique");
            requireText(propertyId, "counterexample property");
            requireText(originalInput, "counterexample original input");
            requireText(minimizedInput, "counterexample minimized input");
            requireText(failureCode, "counterexample failure code");
            requireText(failureFingerprint, "counterexample fingerprint");
            requireText(replayCommand, "counterexample replay command");
            evidenceRefs = List.copyOf(evidenceRefs);
        }
    }

    public record TechniqueResult(String technique, String specificationId, Status status,
                                  int executedCases, double coverage,
                                  List<Counterexample> counterexamples,
                                  List<String> unknowns, List<String> evidenceRefs,
                                  Map<String, Number> metrics) {
        public TechniqueResult {
            requireText(technique, "technique");
            requireText(specificationId, "specification id");
            Objects.requireNonNull(status, "technique status");
            counterexamples = List.copyOf(counterexamples);
            unknowns = List.copyOf(unknowns);
            evidenceRefs = List.copyOf(evidenceRefs);
            metrics = Map.copyOf(metrics);
            if (executedCases < 0 || coverage < 0 || coverage > 1) throw new IllegalArgumentException("invalid technique result");
        }
    }

    public record ProofResult<T>(String propertyId, ProofStatus status, int exploredStates,
                                 int declaredDomainSize, T witness, List<String> assumptions,
                                 List<String> evidenceRefs) {
        public ProofResult {
            requireText(propertyId, "proof property");
            Objects.requireNonNull(status, "proof status");
            assumptions = List.copyOf(assumptions);
            evidenceRefs = List.copyOf(evidenceRefs);
            if (exploredStates < 0 || declaredDomainSize < 0) throw new IllegalArgumentException("invalid proof counts");
        }
    }

    static void requireText(String value, String label) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(label + " is required");
    }
}
