package io.elmos.workflow;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Environment-aware validation for task and FinOps feature-flag rollout.
 *
 * <p>Forward rollout advances one stage at a time, follows the fixed feature
 * dependency order, and cannot enter an environment until the preceding
 * environment is fully enabled. Rollback may move directly to a safer stage,
 * but only after dependent features and downstream environments are lowered.
 * This class changes no remote flag provider state.</p>
 */
public final class TaskFinopsFeatureRollout {
    public enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    /** Safe enablement order; enum declaration order is not used as policy. */
    public enum Feature {
        AUTHENTICATED_ACCOUNT_BINDING,
        ACCOUNT_CONCURRENCY_LIMIT,
        DURABLE_WORKFLOW_START,
        CHECKPOINT_FORK_RECOVERY,
        EXACT_USAGE_METERING,
        PAYMENT_SETTLEMENT_RECONCILIATION
    }

    public enum Stage {
        OFF(0),
        SHADOW(1),
        CANARY(2),
        ON(3);

        private final int rank;

        Stage(int rank) {
            this.rank = rank;
        }

        int rank() {
            return rank;
        }
    }

    public enum Decision {
        APPLY,
        NO_CHANGE,
        REJECT
    }

    public enum ReasonCode {
        STAGE_ADVANCE_SKIPPED,
        PREREQUISITE_NOT_READY,
        PREVIOUS_ENVIRONMENT_NOT_ON,
        DEPENDENT_FEATURE_ACTIVE,
        DOWNSTREAM_ENVIRONMENT_ACTIVE
    }

    public record FlagState(Stage stage, int exposurePercent) {
        public FlagState {
            Objects.requireNonNull(stage, "stage");
            boolean valid = switch (stage) {
                case OFF, SHADOW -> exposurePercent == 0;
                case CANARY -> exposurePercent >= 1 && exposurePercent <= 99;
                case ON -> exposurePercent == 100;
            };
            if (!valid) {
                throw new IllegalArgumentException("ELMOS_MTF_ROLLOUT_EXPOSURE_INVALID");
            }
        }
    }

    public record FlagKey(Environment environment, Feature feature) {
        public FlagKey {
            Objects.requireNonNull(environment, "environment");
            Objects.requireNonNull(feature, "feature");
        }
    }

    public record RolloutSnapshot(Map<FlagKey, FlagState> states) {
        private static final FlagState OFF = new FlagState(Stage.OFF, 0);

        public RolloutSnapshot {
            states = Map.copyOf(Objects.requireNonNull(states, "states"));
        }

        public FlagState state(Environment environment, Feature feature) {
            return states.getOrDefault(new FlagKey(environment, feature), OFF);
        }
    }

    public record Change(
            Environment environment,
            Feature feature,
            FlagState desiredState
    ) {
        public Change {
            Objects.requireNonNull(environment, "environment");
            Objects.requireNonNull(feature, "feature");
            Objects.requireNonNull(desiredState, "desiredState");
        }
    }

    public record Violation(
            ReasonCode reasonCode,
            Environment relatedEnvironment,
            Feature relatedFeature
    ) {
        public Violation {
            Objects.requireNonNull(reasonCode, "reasonCode");
            Objects.requireNonNull(relatedEnvironment, "relatedEnvironment");
            Objects.requireNonNull(relatedFeature, "relatedFeature");
        }
    }

    public record Validation(Decision decision, List<Violation> violations) {
        public Validation {
            Objects.requireNonNull(decision, "decision");
            violations = List.copyOf(Objects.requireNonNull(violations, "violations"));
            if ((decision == Decision.REJECT) != !violations.isEmpty()) {
                throw new IllegalArgumentException("ELMOS_MTF_ROLLOUT_VALIDATION_INVALID");
            }
        }

        public boolean accepted() {
            return decision != Decision.REJECT;
        }
    }

    public static final class RolloutRejectedException extends RuntimeException {
        private final List<Violation> violations;

        private RolloutRejectedException(List<Violation> violations) {
            super("ELMOS_MTF_ROLLOUT_REJECTED_"
                    + violations.stream()
                            .map(violation -> violation.reasonCode().name())
                            .distinct()
                            .toList());
            this.violations = List.copyOf(violations);
        }

        public List<Violation> violations() {
            return violations;
        }
    }

    private static final List<Feature> SAFE_ORDER = List.of(
            Feature.AUTHENTICATED_ACCOUNT_BINDING,
            Feature.ACCOUNT_CONCURRENCY_LIMIT,
            Feature.DURABLE_WORKFLOW_START,
            Feature.CHECKPOINT_FORK_RECOVERY,
            Feature.EXACT_USAGE_METERING,
            Feature.PAYMENT_SETTLEMENT_RECONCILIATION);

    private TaskFinopsFeatureRollout() {}

    public static Validation validate(RolloutSnapshot snapshot, Change change) {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(change, "change");
        FlagState current = snapshot.state(change.environment(), change.feature());
        if (current.equals(change.desiredState())) {
            return new Validation(Decision.NO_CHANGE, List.of());
        }

        List<Violation> violations = new ArrayList<>();
        int currentRank = current.stage().rank();
        int desiredRank = change.desiredState().stage().rank();
        if (desiredRank > currentRank) {
            validateForward(snapshot, change, currentRank, desiredRank, violations);
        } else {
            validateRollback(snapshot, change, desiredRank, violations);
        }
        return violations.isEmpty()
                ? new Validation(Decision.APPLY, List.of())
                : new Validation(Decision.REJECT, violations);
    }

    public static RolloutSnapshot apply(RolloutSnapshot snapshot, Change change) {
        Validation validation = validate(snapshot, change);
        if (!validation.accepted()) {
            throw new RolloutRejectedException(validation.violations());
        }
        if (validation.decision() == Decision.NO_CHANGE) {
            return snapshot;
        }
        Map<FlagKey, FlagState> updated = new LinkedHashMap<>(snapshot.states());
        updated.put(new FlagKey(change.environment(), change.feature()), change.desiredState());
        return new RolloutSnapshot(updated);
    }

    private static void validateForward(
            RolloutSnapshot snapshot,
            Change change,
            int currentRank,
            int desiredRank,
            List<Violation> violations
    ) {
        if (desiredRank != currentRank + 1) {
            violations.add(new Violation(
                    ReasonCode.STAGE_ADVANCE_SKIPPED,
                    change.environment(),
                    change.feature()));
        }

        Environment previousEnvironment = previous(change.environment());
        if (previousEnvironment != null
                && snapshot.state(previousEnvironment, change.feature()).stage() != Stage.ON) {
            violations.add(new Violation(
                    ReasonCode.PREVIOUS_ENVIRONMENT_NOT_ON,
                    previousEnvironment,
                    change.feature()));
        }

        int featureIndex = SAFE_ORDER.indexOf(change.feature());
        for (int index = 0; index < featureIndex; index++) {
            Feature prerequisite = SAFE_ORDER.get(index);
            if (snapshot.state(change.environment(), prerequisite).stage().rank() < desiredRank) {
                violations.add(new Violation(
                        ReasonCode.PREREQUISITE_NOT_READY,
                        change.environment(),
                        prerequisite));
            }
        }
    }

    private static void validateRollback(
            RolloutSnapshot snapshot,
            Change change,
            int desiredRank,
            List<Violation> violations
    ) {
        int featureIndex = SAFE_ORDER.indexOf(change.feature());
        for (int index = featureIndex + 1; index < SAFE_ORDER.size(); index++) {
            Feature dependent = SAFE_ORDER.get(index);
            if (snapshot.state(change.environment(), dependent).stage().rank() > desiredRank) {
                violations.add(new Violation(
                        ReasonCode.DEPENDENT_FEATURE_ACTIVE,
                        change.environment(),
                        dependent));
            }
        }

        for (Environment environment : Environment.values()) {
            if (environment.ordinal() <= change.environment().ordinal()) {
                continue;
            }
            if (snapshot.state(environment, change.feature()).stage().rank() > desiredRank) {
                violations.add(new Violation(
                        ReasonCode.DOWNSTREAM_ENVIRONMENT_ACTIVE,
                        environment,
                        change.feature()));
            }
        }
    }

    private static Environment previous(Environment environment) {
        return switch (environment) {
            case DEVELOPMENT -> null;
            case STAGING -> Environment.DEVELOPMENT;
            case PRODUCTION -> Environment.STAGING;
        };
    }
}
