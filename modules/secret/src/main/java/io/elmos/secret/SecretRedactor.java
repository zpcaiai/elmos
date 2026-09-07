package io.elmos.secret;

import java.util.Collection;
import java.util.regex.Pattern;

public final class SecretRedactor {
    private static final Pattern AUTHORIZATION = Pattern.compile("(?i)(authorization\\s*[:=]\\s*)(bearer|token|basic)\\s+[^\\s,;]+", Pattern.MULTILINE);
    private static final Pattern PASSWORD = Pattern.compile("(?i)((password|passwd|token|secret)\\s*[:=]\\s*)[^\\s,;]+", Pattern.MULTILINE);

    public String redact(String text, Collection<char[]> knownValues) {
        if (text == null) return null;
        String redacted = text;
        if (knownValues != null) for (char[] value : knownValues) {
            if (value != null && value.length >= 4) redacted = redacted.replace(new String(value), "[REDACTED]");
        }
        redacted = AUTHORIZATION.matcher(redacted).replaceAll("$1[REDACTED]");
        return PASSWORD.matcher(redacted).replaceAll("$1[REDACTED]");
    }
}
