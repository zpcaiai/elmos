package io.elmos.identity;

import java.util.Locale;
import java.util.Optional;

/**
 * Normalisation and masking for the two things a person signs in with: a mainland
 * China mobile number and an email address.
 *
 * <p>Normalisation is a security property, not a convenience. The lookup HMAC is
 * computed over the normalised form, so {@code 13800138000},
 * {@code +86 138 0013 8000} and {@code 008613800138000} must all collapse to one
 * value - otherwise the same person creates three accounts, three trials, and
 * three ways to be enumerated.</p>
 */
public final class Destinations {

    private Destinations() {
    }

    public enum Channel { SMS, EMAIL }

    public record Destination(Channel channel, String normalized, String masked) {
    }

    /**
     * Normalises a mainland China mobile number to E.164.
     *
     * <p>Deliberately narrow: only +86 mobile numbers are accepted, because that is
     * the launch market and a permissive parser here would let a typo become a
     * successfully delivered SMS to a stranger.</p>
     */
    public static Optional<Destination> normalizeChineseMobile(String raw) {
        if (raw == null) {
            return Optional.empty();
        }
        String digits = raw.replaceAll("[\\s()\\-]", "");
        if (digits.startsWith("+86")) {
            digits = digits.substring(3);
        } else if (digits.startsWith("0086")) {
            digits = digits.substring(4);
        } else if (digits.startsWith("86") && digits.length() == 13) {
            digits = digits.substring(2);
        }
        // Mainland mobile numbers are 11 digits starting with 1, second digit 3-9.
        if (!digits.matches("^1[3-9]\\d{9}$")) {
            return Optional.empty();
        }
        String normalized = "+86" + digits;
        String masked = digits.substring(0, 3) + "****" + digits.substring(7);
        return Optional.of(new Destination(Channel.SMS, normalized, masked));
    }

    public static Optional<Destination> normalizeEmail(String raw) {
        if (raw == null) {
            return Optional.empty();
        }
        String trimmed = raw.trim();
        if (trimmed.length() > 320 || trimmed.chars().anyMatch(c -> c < 0x20 || c == 0x7F)) {
            return Optional.empty();
        }
        int at = trimmed.lastIndexOf('@');
        if (at <= 0 || at == trimmed.length() - 1) {
            return Optional.empty();
        }
        String local = trimmed.substring(0, at);
        String domain = trimmed.substring(at + 1).toLowerCase(Locale.ROOT);
        if (!domain.matches("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")) {
            return Optional.empty();
        }
        // The local part needs a real charset check, not just a length one.
        // Splitting on the LAST '@' means "user@@example.com" yields a local part
        // of "user@", which passes every length and dot rule while being invalid -
        // and would be delivered to an address the user did not type.
        if (local.isEmpty() || local.length() > 64
                || local.contains("..")
                || local.startsWith(".") || local.endsWith(".")
                || !local.matches("^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")) {
            return Optional.empty();
        }

        // Only the domain is lowercased. The local part is case-sensitive per RFC
        // 5321, and folding it would merge two addresses that some providers treat
        // as distinct mailboxes.
        String normalized = local + "@" + domain;
        String masked = local.charAt(0)
                + "***@" + domain;
        return Optional.of(new Destination(Channel.EMAIL, normalized, masked));
    }

    /** Coarse client identifier for rate limiting: the /24 or /48, never the full address. */
    public static String clientPrefix(String remoteAddress) {
        if (remoteAddress == null || remoteAddress.isBlank()) {
            return null;
        }
        String address = remoteAddress.trim();
        if (address.contains(":")) {
            String[] groups = address.split(":");
            StringBuilder prefix = new StringBuilder();
            for (int i = 0; i < Math.min(3, groups.length); i++) {
                if (i > 0) {
                    prefix.append(':');
                }
                prefix.append(groups[i]);
            }
            return prefix.toString();
        }
        String[] octets = address.split("\\.");
        if (octets.length != 4) {
            return null;
        }
        return octets[0] + "." + octets[1] + "." + octets[2];
    }
}
