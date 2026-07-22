package io.elmos.verification;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

import static io.elmos.verification.VerificationModels.Counterexample;

final class CounterexampleFactory {
    private CounterexampleFactory() {}

    static Counterexample create(String technique, String propertyId, long seed, Object original,
                                 Object minimized, String failureCode) {
        String minimizedText=String.valueOf(minimized);
        String fingerprint=digest(technique+"\0"+propertyId+"\0"+failureCode+"\0"+minimizedText);
        String replay="mvn -pl modules/advanced-verification -Dverification.property="+propertyId+
                " -Dverification.seed="+seed+" test";
        return new Counterexample(technique,propertyId,seed,String.valueOf(original),minimizedText,
                failureCode,fingerprint,replay,List.of("local://advanced-verification/replay"));
    }

    static String digest(String value) {
        try {
            return "sha256:"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) { throw new IllegalStateException(error); }
    }
}
