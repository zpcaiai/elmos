package io.elmos.verification;

import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;

import static io.elmos.verification.VerificationModels.Counterexample;

public final class CounterexampleReplayRegistry {
    public record ReplayResult(boolean replayed,boolean fingerprintMatched,String observedFailureCode) {}
    private record Entry(Counterexample counterexample,Supplier<String> replay) {}
    private final Map<String,Entry> entries=new HashMap<>();

    public void register(Counterexample counterexample,Supplier<String> replay) {
        if (entries.putIfAbsent(counterexample.failureFingerprint(),new Entry(counterexample,replay))!=null) throw new IllegalArgumentException("duplicate counterexample fingerprint");
    }
    public ReplayResult replay(String fingerprint) {
        Entry entry=entries.get(fingerprint); if (entry==null) return new ReplayResult(false,false,null);
        String observed=entry.replay().get(); boolean matched=entry.counterexample().failureCode().equals(observed);
        return new ReplayResult(true,matched,observed);
    }
}
