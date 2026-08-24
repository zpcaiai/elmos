package io.elmos.cas;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * ELMOS-CAS-023 "redacted logs". Logs are cached and replayed on every hit, so a secret that
 * reaches a log reaches every future consumer of that cache entry - including consumers whose
 * permission scope would never have granted them the secret in the first place.
 *
 * <p>Redaction is by known value, not by pattern guessing. A regex for "things that look like a
 * token" both misses real secrets and mangles innocent output; the broker knows exactly which
 * values it handed out, and those are what get replaced.
 */
public final class LogRedaction {

    /** Short values are refused: redacting a two-character secret would blank out ordinary text. */
    private static final int MINIMUM_SECRET_LENGTH = 6;

    private final List<String> secrets = new ArrayList<>();

    public LogRedaction withSecret(String value) {
        if (value != null && value.length() >= MINIMUM_SECRET_LENGTH) {
            secrets.add(value);
        }
        return this;
    }

    public record Redacted(byte[] content, CasDigest digest, Set<String> redactedFingerprints) {
        public Redacted {
            content = content.clone();
        }

        @Override
        public byte[] content() {
            return content.clone();
        }
    }

    public Redacted redact(String log) {
        String result = log;
        Set<String> hit = new LinkedHashSet<>();
        // Longest first, so a secret that contains another secret is not partially rewritten into
        // a value that no longer matches the shorter one.
        List<String> ordered = new ArrayList<>(secrets);
        ordered.sort((left, right) -> right.length() - left.length());
        for (String secret : ordered) {
            if (result.contains(secret)) {
                hit.add(fingerprint(secret));
                result = result.replace(secret, "[REDACTED:" + fingerprint(secret) + "]");
            }
        }
        byte[] content = result.getBytes(StandardCharsets.UTF_8);
        return new Redacted(content, CasDigest.of(content), Set.copyOf(hit));
    }

    /** A stable, non-reversing label so an operator can correlate two redactions without the value. */
    public static String fingerprint(String secret) {
        return CasDigest.ofUtf8(secret).hex().substring(0, 8);
    }
}
