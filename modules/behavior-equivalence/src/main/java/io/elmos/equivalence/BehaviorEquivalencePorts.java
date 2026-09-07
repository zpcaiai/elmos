package io.elmos.equivalence;

import io.elmos.equivalence.BehaviorEquivalenceModels.*;

/** Side-effecting Batch 9 capabilities. Implementations belong in approved isolated runners. */
public final class BehaviorEquivalencePorts {
    private BehaviorEquivalencePorts() {}

    public interface DualRuntimeAuthority {
        EnvironmentAlignment prepare(Request request);
        default void cleanup(Request request, EnvironmentAlignment alignment) { }
    }

    public interface DifferentialExecutionAuthority {
        CleanRun execute(Request request, EnvironmentAlignment alignment, int cleanRunIndex);
    }

    public interface EquivalenceOracleAuthority {
        Comparison compare(ComparisonRequest request);
    }

    public interface Batch8RepairFeedbackAuthority {
        void submit(Request request, RepairFeedback feedback);
    }
}
