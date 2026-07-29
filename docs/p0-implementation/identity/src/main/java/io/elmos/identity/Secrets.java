package io.elmos.identity;

import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;

/**
 * Cryptographic primitives for the authentication service.
 *
 * <p>Zero third-party dependencies, matching the rest of this work: everything
 * here is in the JDK. The one exception worth naming is Argon2id, which the JDK
 * does not provide - {@link #hashPassword} therefore uses PBKDF2-HMAC-SHA256 and
 * records the algorithm alongside the hash, so a deployment that adds an Argon2
 * dependency can migrate credentials on next sign-in without a flag day.</p>
 */
public final class Secrets {

    private static final SecureRandom RANDOM = new SecureRandom();

    /** OWASP's floor for PBKDF2-HMAC-SHA256 at the time of writing. */
    private static final int PBKDF2_ITERATIONS = 600_000;
    private static final int PBKDF2_KEY_BITS = 256;
    private static final int SALT_BYTES = 16;
    private static final int OPAQUE_TOKEN_BYTES = 32;

    private Secrets() {
    }

    // ---- one-time codes ----------------------------------------------------

    /**
     * A six-digit numeric code, uniformly distributed.
     *
     * <p>{@code random.nextInt(1000000)} would be correct, but the common
     * shortcut {@code abs(random.nextInt()) % 1000000} is not: 2^31 is not a
     * multiple of 10^6, so the low codes come up slightly more often. The bias is
     * small and entirely avoidable, and an attacker guessing codes benefits from
     * every bit of it.</p>
     */
    public static String newNumericCode(int digits) {
        if (digits < 4 || digits > 9) {
            throw new IllegalArgumentException("OTP_LENGTH_UNSUPPORTED");
        }
        int bound = (int) Math.pow(10, digits);
        int value = RANDOM.nextInt(bound);
        return String.format(Locale.ROOT, "%0" + digits + "d", value);
    }

    /** Opaque, 256 bits of entropy, URL-safe. Used for refresh tokens and invitations. */
    public static String newOpaqueToken() {
        byte[] bytes = new byte[OPAQUE_TOKEN_BYTES];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    // ---- keyed hashing -----------------------------------------------------

    /**
     * Keyed hash used for phone numbers and email addresses.
     *
     * <p>The pepper lives in KMS and never in the database, so a database copy on
     * its own cannot enumerate the user base - which a plain SHA-256 of a phone
     * number absolutely can, since the whole space of Chinese mobile numbers is
     * about 10^9 and trivially precomputed.</p>
     */
    public static String lookupHmac(String pepper, String normalizedDestination) {
        if (pepper == null || pepper.length() < 32) {
            // A short or absent pepper is worse than useless: it looks like
            // protection while providing none.
            throw new IllegalStateException("IDENTITY_PEPPER_NOT_CONFIGURED");
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of()
                    .formatHex(mac.doFinal(normalizedDestination.getBytes(StandardCharsets.UTF_8)))
                    .toLowerCase(Locale.ROOT);
        } catch (Exception ex) {
            throw new IllegalStateException("HmacSHA256 unavailable", ex);
        }
    }

    // ---- passwords ---------------------------------------------------------

    public record PasswordHash(String algorithm, String encoded) {
    }

    /** Encoded as {@code pbkdf2_sha256$<iterations>$<saltB64>$<hashB64>}. */
    public static PasswordHash hashPassword(char[] password) {
        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);
        byte[] hash = pbkdf2(password, salt, PBKDF2_ITERATIONS);
        Base64.Encoder encoder = Base64.getEncoder().withoutPadding();
        return new PasswordHash("PBKDF2_SHA256",
                "pbkdf2_sha256$" + PBKDF2_ITERATIONS + "$"
                        + encoder.encodeToString(salt) + "$" + encoder.encodeToString(hash));
    }

    /**
     * Verifies a password in constant time with respect to the hash contents.
     *
     * <p>Returns false for a malformed or absent stored hash rather than throwing,
     * so a passwordless account and a wrong password are indistinguishable from
     * the outside.</p>
     */
    public static boolean verifyPassword(char[] password, String encoded) {
        if (encoded == null) {
            return false;
        }
        String[] parts = encoded.split("\\$");
        if (parts.length != 4 || !"pbkdf2_sha256".equals(parts[0])) {
            return false;
        }
        try {
            int iterations = Integer.parseInt(parts[1]);
            if (iterations < 100_000 || iterations > 5_000_000) {
                return false;
            }
            Base64.Decoder decoder = Base64.getDecoder();
            byte[] salt = decoder.decode(parts[2]);
            byte[] expected = decoder.decode(parts[3]);
            return constantTimeEquals(pbkdf2(password, salt, iterations), expected);
        } catch (RuntimeException ex) {
            return false;
        }
    }

    private static byte[] pbkdf2(char[] password, byte[] salt, int iterations) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, PBKDF2_KEY_BITS);
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (Exception ex) {
            throw new IllegalStateException("PBKDF2 unavailable", ex);
        }
    }

    // ---- comparison --------------------------------------------------------

    /**
     * Length-independent, early-exit-free comparison.
     *
     * <p>{@code String.equals} returns on the first differing character, which
     * leaks a prefix match through timing. For a six-digit code that is enough to
     * turn 10^6 guesses into about 60.</p>
     */
    public static boolean constantTimeEquals(String left, String right) {
        if (left == null || right == null) {
            return false;
        }
        return constantTimeEquals(left.getBytes(StandardCharsets.UTF_8),
                right.getBytes(StandardCharsets.UTF_8));
    }

    public static boolean constantTimeEquals(byte[] left, byte[] right) {
        if (left == null || right == null) {
            return false;
        }
        // MessageDigest.isEqual is the JDK's constant-time comparison and, since
        // Java 7, does not short-circuit on length either.
        return MessageDigest.isEqual(left, right);
    }
}
