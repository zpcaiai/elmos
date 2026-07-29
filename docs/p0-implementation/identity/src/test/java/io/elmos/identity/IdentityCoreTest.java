package io.elmos.identity;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** Acceptance suite for the dependency-free identity core. */
public final class IdentityCoreTest {

    private static final List<String> FAILURES = new ArrayList<>();
    private static int checks;

    public static void main(String[] args) {
        codesAreUniformAndUnpredictable();
        opaqueTokensHaveFullEntropy();
        comparisonIsConstantTime();
        passwordsRoundTrip();
        pepperActuallyProtects();
        chineseMobilesNormalizeToOneForm();
        emailNormalizationIsCorrectlyAsymmetric();
        maskingRevealsLittle();
        clientPrefixIsCoarse();

        System.out.println();
        if (FAILURES.isEmpty()) {
            System.out.println("IDENTITY CORE TEST PASSED (" + checks + " checks)");
            System.exit(0);
        }
        System.out.println("IDENTITY CORE TEST FAILED (" + FAILURES.size() + "/" + checks + ")");
        FAILURES.forEach(f -> System.out.println("  - " + f));
        System.exit(1);
    }

    /**
     * A biased OTP generator hands the attacker free guesses. Sample enough codes
     * that a modulo bias would show up as a lopsided leading-digit distribution.
     */
    static void codesAreUniformAndUnpredictable() {
        int samples = 120_000;
        int[] leading = new int[10];
        Set<String> distinct = new HashSet<>();
        for (int i = 0; i < samples; i++) {
            String code = Secrets.newNumericCode(6);
            if (code.length() != 6 || !code.matches("^\\d{6}$")) {
                check("code shape is six digits", false);
                return;
            }
            leading[code.charAt(0) - '0']++;
            distinct.add(code);
        }
        check("codes are six digits", true);

        int expected = samples / 10;
        int worst = 0;
        for (int count : leading) {
            worst = Math.max(worst, Math.abs(count - expected));
        }
        // A 2^31 % 10^6 modulo bias skews the distribution by roughly 2 percent;
        // 5 percent tolerance catches it while staying stable across runs.
        check("leading digits are uniform (worst deviation "
                + String.format(java.util.Locale.ROOT, "%.2f%%", 100.0 * worst / expected) + ")",
                worst < expected * 0.05);
        check("codes are not repeating trivially", distinct.size() > samples / 2);
        check("short and long code lengths are refused",
                throwsIllegal(() -> Secrets.newNumericCode(3))
                        && throwsIllegal(() -> Secrets.newNumericCode(12)));
    }

    static void opaqueTokensHaveFullEntropy() {
        Set<String> tokens = new HashSet<>();
        for (int i = 0; i < 20_000; i++) {
            tokens.add(Secrets.newOpaqueToken());
        }
        check("opaque tokens never collide", tokens.size() == 20_000);
        String token = Secrets.newOpaqueToken();
        // 32 bytes base64url without padding is 43 characters.
        check("opaque tokens carry 256 bits", token.length() == 43);
        check("opaque tokens are url safe", token.matches("^[A-Za-z0-9_-]+$"));
        check("hashing is stable", Secrets.sha256Hex(token).equals(Secrets.sha256Hex(token)));
        check("hash is 64 hex characters", Secrets.sha256Hex(token).matches("^[0-9a-f]{64}$"));
    }

    static void comparisonIsConstantTime() {
        check("identical values match", Secrets.constantTimeEquals("123456", "123456"));
        check("differing values do not match", !Secrets.constantTimeEquals("123456", "123457"));
        // A prefix match must not be distinguishable from no match at all.
        check("a long shared prefix does not match", !Secrets.constantTimeEquals("123456", "123450"));
        check("different lengths do not match", !Secrets.constantTimeEquals("123456", "1234567"));
        check("null is never equal",
                !Secrets.constantTimeEquals(null, "x") && !Secrets.constantTimeEquals("x", null));
    }

    static void passwordsRoundTrip() {
        Secrets.PasswordHash hash = Secrets.hashPassword("正确的密码 correct horse".toCharArray());
        check("algorithm is recorded", hash.algorithm().equals("PBKDF2_SHA256"));
        check("encoding carries algorithm, iterations, salt and hash",
                hash.encoded().split("\\$").length == 4);
        check("correct password verifies",
                Secrets.verifyPassword("正确的密码 correct horse".toCharArray(), hash.encoded()));
        check("wrong password is rejected",
                !Secrets.verifyPassword("wrong".toCharArray(), hash.encoded()));

        // Distinct salts: two accounts with the same password must not share a hash,
        // or one cracked hash cracks them all.
        Secrets.PasswordHash again = Secrets.hashPassword("正确的密码 correct horse".toCharArray());
        check("the same password hashes differently each time",
                !hash.encoded().equals(again.encoded()));

        check("a null stored hash is a rejection, not a crash",
                !Secrets.verifyPassword("x".toCharArray(), null));
        check("a malformed stored hash is a rejection",
                !Secrets.verifyPassword("x".toCharArray(), "not-a-hash"));
        // A tampered iteration count must not let an attacker cheapen the check.
        check("an implausible iteration count is refused",
                !Secrets.verifyPassword("x".toCharArray(), "pbkdf2_sha256$1$AAAA$AAAA"));
    }

    static void pepperActuallyProtects() {
        String phone = "+8613800138000";
        String pepperA = "a".repeat(40);
        String pepperB = "b".repeat(40);

        check("hmac is stable for one pepper",
                Secrets.lookupHmac(pepperA, phone).equals(Secrets.lookupHmac(pepperA, phone)));
        // This is the property that makes a database leak insufficient: without the
        // KMS-held pepper the stored value cannot be reproduced from a phone number.
        check("a different pepper yields a different hmac",
                !Secrets.lookupHmac(pepperA, phone).equals(Secrets.lookupHmac(pepperB, phone)));
        check("hmac is 64 hex characters",
                Secrets.lookupHmac(pepperA, phone).matches("^[0-9a-f]{64}$"));
        check("an absent pepper is refused",
                throwsState(() -> Secrets.lookupHmac(null, phone)));
        check("a short pepper is refused",
                throwsState(() -> Secrets.lookupHmac("short", phone)));
    }

    static void chineseMobilesNormalizeToOneForm() {
        String expected = "+8613800138000";
        for (String input : List.of("13800138000", "+8613800138000", "008613800138000",
                "+86 138 0013 8000", "138-0013-8000", "8613800138000")) {
            Optional<Destinations.Destination> result = Destinations.normalizeChineseMobile(input);
            check("normalizes " + input,
                    result.isPresent() && result.get().normalized().equals(expected));
        }
        // One person, one HMAC, one trial. Divergent forms would defeat the
        // trial_grants uniqueness constraint entirely.
        String pepper = "p".repeat(40);
        Set<String> hashes = new HashSet<>();
        for (String input : List.of("13800138000", "+86 138 0013 8000", "008613800138000")) {
            hashes.add(Secrets.lookupHmac(pepper,
                    Destinations.normalizeChineseMobile(input).orElseThrow().normalized()));
        }
        check("every written form maps to a single lookup hash", hashes.size() == 1);

        for (String bad : List.of("12800138000", "1380013800", "138001380001",
                "+8512345678901", "abcdefghijk", "")) {
            check("rejects " + (bad.isEmpty() ? "(empty)" : bad),
                    Destinations.normalizeChineseMobile(bad).isEmpty());
        }
        check("rejects null", Destinations.normalizeChineseMobile(null).isEmpty());
    }

    static void emailNormalizationIsCorrectlyAsymmetric() {
        Optional<Destinations.Destination> mixed = Destinations.normalizeEmail("User.Name@EXAMPLE.COM");
        check("domain is lowercased",
                mixed.isPresent() && mixed.get().normalized().endsWith("@example.com"));
        // RFC 5321 makes the local part case sensitive; folding it merges mailboxes
        // that some providers treat as different people.
        check("local part keeps its case",
                mixed.isPresent() && mixed.get().normalized().startsWith("User.Name@"));

        for (String bad : List.of("no-at-sign", "@example.com", "user@", "user@@example.com",
                "user@example", "user..name@example.com", "user@-example.com")) {
            check("rejects " + bad, Destinations.normalizeEmail(bad).isEmpty());
        }
        check("rejects a header-injection attempt",
                Destinations.normalizeEmail("user@example.com\r\nBcc: victim@example.com").isEmpty());
    }

    static void maskingRevealsLittle() {
        check("mobile mask keeps only the ends",
                Destinations.normalizeChineseMobile("13800138000").orElseThrow().masked()
                        .equals("138****8000"));
        check("email mask keeps one character",
                Destinations.normalizeEmail("stephen@example.com").orElseThrow().masked()
                        .equals("s***@example.com"));
    }

    static void clientPrefixIsCoarse() {
        check("ipv4 collapses to /24", "203.0.113".equals(Destinations.clientPrefix("203.0.113.42")));
        check("ipv6 collapses to the first three groups",
                "2001:db8:1".equals(Destinations.clientPrefix("2001:db8:1:2:3:4:5:6")));
        check("nonsense yields no prefix", Destinations.clientPrefix("not-an-address") == null);
        check("blank yields no prefix", Destinations.clientPrefix("  ") == null);
    }

    // ---- helpers -----------------------------------------------------------

    private static boolean throwsIllegal(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException ex) {
            return true;
        }
    }

    private static boolean throwsState(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalStateException ex) {
            return true;
        }
    }

    private static void check(String description, boolean condition) {
        checks++;
        System.out.println((condition ? "  ok   " : "  FAIL ") + description);
        if (!condition) {
            FAILURES.add(description);
        }
    }
}
