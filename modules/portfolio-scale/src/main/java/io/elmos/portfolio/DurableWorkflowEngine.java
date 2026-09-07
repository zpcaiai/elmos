package io.elmos.portfolio;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.*;

public final class DurableWorkflowEngine {
    @FunctionalInterface public interface Activity {
        ActivityResult run(int attempt, Optional<Checkpoint> priorCheckpoint);
    }
    @FunctionalInterface public interface ExternalEffect {
        void apply(String commitToken);
    }

    private final Map<String, String> requestFingerprints = new HashMap<>();
    private final Map<String, TaskOutcome> outcomes = new HashMap<>();
    private final Map<String, Checkpoint> checkpoints = new HashMap<>();
    private final Set<String> committedTokens = new HashSet<>();

    public TaskOutcome execute(TaskRequest request, Activity activity, ExternalEffect externalEffect) {
        String scopedKey = request.tenantId() + "\0" + request.idempotencyKey();
        String fingerprint = digest(request.workUnitId() + "\0" + request.inputDigest() + "\0" + request.externalEffectRequested());
        String previousFingerprint = requestFingerprints.get(scopedKey);
        if (previousFingerprint != null) {
            if (!previousFingerprint.equals(fingerprint)) throw new IllegalStateException("idempotency key reused with different input");
            TaskOutcome prior = outcomes.get(scopedKey);
            return new TaskOutcome(prior.status(), prior.attempts(), true, prior.externalEffectApplied(),
                    prior.commitToken(), prior.outputDigest(), prior.failures());
        }
        if (request.externalEffectRequested() && externalEffect == null) {
            throw new IllegalArgumentException("external effect handler is required");
        }

        List<String> failures = new ArrayList<>();
        for (int attempt = 1; attempt <= request.maximumAttempts(); attempt++) {
            ActivityResult result;
            try {
                result = activity.run(attempt, Optional.ofNullable(checkpoints.get(request.taskId())));
            } catch (RuntimeException error) {
                result = ActivityResult.failure(digest(request.taskId() + ":" + attempt), "ACTIVITY_EXCEPTION:" + error.getClass().getSimpleName());
            }
            checkpoints.put(request.taskId(), new Checkpoint(request.taskId(), attempt, result.stateDigest(), result.failureCode()));
            if (!result.succeeded()) {
                failures.add(result.failureCode());
                continue;
            }
            String commitToken = request.externalEffectRequested()
                    ? digest(request.tenantId() + "\0" + request.taskId() + "\0" + request.inputDigest()) : null;
            boolean applied = false;
            if (request.externalEffectRequested() && !committedTokens.contains(commitToken)) {
                try {
                    externalEffect.apply(commitToken);
                    committedTokens.add(commitToken);
                    applied = true;
                } catch (RuntimeException error) {
                    failures.add("EXTERNAL_EFFECT_EXCEPTION:" + error.getClass().getSimpleName());
                    continue;
                }
            }
            TaskOutcome outcome = new TaskOutcome(TaskStatus.SUCCEEDED, attempt, false,
                    request.externalEffectRequested() && (applied || committedTokens.contains(commitToken)),
                    commitToken, result.outputDigest(), failures);
            requestFingerprints.put(scopedKey, fingerprint);
            outcomes.put(scopedKey, outcome);
            return outcome;
        }
        TaskOutcome failed = new TaskOutcome(TaskStatus.FAILED, request.maximumAttempts(), false,
                false, null, null, failures);
        requestFingerprints.put(scopedKey, fingerprint);
        outcomes.put(scopedKey, failed);
        return failed;
    }

    public WorkflowSnapshot snapshot() {
        return new WorkflowSnapshot(requestFingerprints, outcomes, checkpoints, committedTokens);
    }

    public static DurableWorkflowEngine restore(WorkflowSnapshot snapshot) {
        DurableWorkflowEngine engine = new DurableWorkflowEngine();
        engine.requestFingerprints.putAll(snapshot.requestFingerprints());
        engine.outcomes.putAll(snapshot.outcomes());
        engine.checkpoints.putAll(snapshot.checkpoints());
        engine.committedTokens.addAll(snapshot.committedTokens());
        return engine;
    }

    private static String digest(String value) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
