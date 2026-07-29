package io.elmos.storage;

import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Pins the presigner to the published AWS example.
 *
 * <p>A signing implementation that is merely self-consistent is worthless: it will
 * agree with itself and be rejected by the service. The decisive check is the
 * documented vector below - matching a specific 64-hex signature by accident is
 * not possible.</p>
 */
public final class SigV4PresignerTest {

    private static final List<String> FAILURES = new ArrayList<>();
    private static int checks;

    public static void main(String[] args) {
        knownVector();
        encodingFollowsRfc3986();
        expiryIsBounded();
        pathStyleAndVirtualHostedDiffer();
        keyWithSpacesAndUnicodeIsEncoded();

        System.out.println();
        if (FAILURES.isEmpty()) {
            System.out.println("SIGV4 PRESIGNER TEST PASSED (" + checks + " checks)");
            System.exit(0);
        }
        System.out.println("SIGV4 PRESIGNER TEST FAILED (" + FAILURES.size() + "/" + checks + ")");
        FAILURES.forEach(f -> System.out.println("  - " + f));
        System.exit(1);
    }

    /**
     * AWS documentation, "Signing and authenticating REST requests - Example:
     * presigned URL". Bucket examplebucket, key test.txt, us-east-1,
     * 2013-05-24T00:00:00Z, 86400s expiry, the published example credentials.
     */
    static void knownVector() {
        URI url = SigV4Presigner.presign(
                "GET",
                "https://s3.amazonaws.com",
                "examplebucket",
                "test.txt",
                "us-east-1",
                false,
                SigV4Presigner.Credentials.of("AKIAIOSFODNN7EXAMPLE",
                        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
                Instant.parse("2013-05-24T00:00:00Z"),
                Duration.ofSeconds(86400),
                Map.of());

        String actual = queryParam(url.toString(), "X-Amz-Signature");
        String expected = "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404";

        System.out.println("  host        " + url.getHost());
        System.out.println("  expected    " + expected);
        System.out.println("  actual      " + actual);
        check("presigned signature matches the published AWS vector", expected.equals(actual));
        check("virtual-hosted host is used", "examplebucket.s3.amazonaws.com".equals(url.getHost()));
        check("credential scope is correct",
                queryParam(url.toString(), "X-Amz-Credential")
                        .equals("AKIAIOSFODNN7EXAMPLE%2F20130524%2Fus-east-1%2Fs3%2Faws4_request"));
    }

    static void encodingFollowsRfc3986() {
        // URLEncoder would emit '+' here; AWS requires %20.
        check("space encodes as %20", SigV4Presigner.encode("a b").equals("a%20b"));
        check("tilde is unreserved", SigV4Presigner.encode("a~b").equals("a~b"));
        check("asterisk is encoded", SigV4Presigner.encode("a*b").equals("a%2Ab"));
        check("slash is encoded in a segment", SigV4Presigner.encode("a/b").equals("a%2Fb"));
        check("path keeps separators", SigV4Presigner.encodePath("a/b c").equals("a/b%20c"));
    }

    static void expiryIsBounded() {
        check("zero expiry is rejected", throwsOn(Duration.ZERO));
        check("eight-day expiry is rejected", throwsOn(Duration.ofDays(8)));
        check("fifteen minutes is accepted", !throwsOn(Duration.ofMinutes(15)));
    }

    static void pathStyleAndVirtualHostedDiffer() {
        URI pathStyle = presign("org-a/obj/abc", true);
        URI virtualHosted = presign("org-a/obj/abc", false);
        check("path style keeps the bucket in the path",
                pathStyle.getPath().startsWith("/elmos-artifacts/"));
        check("virtual hosted moves the bucket into the host",
                virtualHosted.getHost().startsWith("elmos-artifacts."));
        // Different canonical requests must yield different signatures, otherwise
        // the bucket is not actually covered by the signature.
        check("the two styles sign differently",
                !queryParam(pathStyle.toString(), "X-Amz-Signature")
                        .equals(queryParam(virtualHosted.toString(), "X-Amz-Signature")));
    }

    static void keyWithSpacesAndUnicodeIsEncoded() {
        URI url = presign("org-a/报告 v2.zip", true);
        check("unicode key is percent-encoded", !url.toString().contains("报告"));
        check("space in key is not a plus", !url.getRawPath().contains("+"));
    }

    // ---- helpers -----------------------------------------------------------

    private static URI presign(String key, boolean pathStyle) {
        return SigV4Presigner.presign("PUT", "https://oss-cn-beijing.aliyuncs.com",
                "elmos-artifacts", key, "cn-beijing", pathStyle,
                SigV4Presigner.Credentials.of("AK", "SK"),
                Instant.parse("2026-07-28T12:00:00Z"), Duration.ofMinutes(10), Map.of());
    }

    private static boolean throwsOn(Duration expiry) {
        try {
            SigV4Presigner.presign("GET", "https://s3.amazonaws.com", "b", "k", "us-east-1", true,
                    SigV4Presigner.Credentials.of("AK", "SK"), Instant.now(), expiry, Map.of());
            return false;
        } catch (IllegalArgumentException ex) {
            return true;
        }
    }

    private static String queryParam(String url, String name) {
        for (String pair : url.substring(url.indexOf('?') + 1).split("&")) {
            int eq = pair.indexOf('=');
            if (eq > 0 && pair.substring(0, eq).equals(name)) {
                return pair.substring(eq + 1);
            }
        }
        return "";
    }

    private static void check(String description, boolean condition) {
        checks++;
        System.out.println((condition ? "  ok   " : "  FAIL ") + description);
        if (!condition) {
            FAILURES.add(description);
        }
    }
}
