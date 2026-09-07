package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Certificates are embedded rather than generated at test time so the fixtures are byte-stable and
 * the test needs nothing but the JDK. They were produced once with `keytool` (EC P-256, 100 year
 * validity except where the case needs otherwise) and are test-only material: no private key from
 * this set exists anywhere.
 */
class WorkloadIdentityTest {

    private static final String CA = """
-----BEGIN CERTIFICATE-----
MIIBbTCCAROgAwIBAgIITElFoTJiIXUwCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
ZWxtb3Mtcm9vdC1jYTAgFw0yNjA4MTkwOTQyMDJaGA8yMTI2MDcyNjA5NDIwMlow
GDEWMBQGA1UEAxMNZWxtb3Mtcm9vdC1jYTBZMBMGByqGSM49AgEGCCqGSM49AwEH
A0IABMDAJFOpw+9wksO15JBp7eIXIMoHqhwzJvWElXJzv9mWyaKU1GJS7e22QBuR
P7me6fR3iVT1T7Eno4c9p+N+tbWjRTBDMB0GA1UdDgQWBBQDpDM/ZVNOpuJgYZCz
bfm8ca+xUzAOBgNVHQ8BAf8EBAMCAQYwEgYDVR0TAQH/BAgwBgEB/wIBATAKBggq
hkjOPQQDAwNIADBFAiAdOyxjyTolWWltuUkpr9Kf8Y3ezjFiXhBRPLMxn64PmAIh
AJG4YB+105aW7uZ8wiQ1Cy5qmNxRCLnbD0lq2VQXkKmt
-----END CERTIFICATE-----
""";

    private static final String ROGUE_CA = """
-----BEGIN CERTIFICATE-----
MIIBaTCCARCgAwIBAgIIKcZF2AE8t/4wCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
cm9ndWUtcm9vdC1jYTAgFw0yNjA4MTkwOTQyMDNaGA8yMTI2MDcyNjA5NDIwM1ow
GDEWMBQGA1UEAxMNcm9ndWUtcm9vdC1jYTBZMBMGByqGSM49AgEGCCqGSM49AwEH
A0IABHPTMUTbis9hXNoebNQMiv/8UX4gv/mX1k2/+dFUzhW08EVIbGWdYeN9XpOh
D9KccelkjYnI0sITLM29j5bil8+jQjBAMB0GA1UdDgQWBBSBz12gpDZWYo28FFzi
BUnGtEvzRzAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB/zAKBggqhkjO
PQQDAwNHADBEAiBh3hBdF2z68+3YGAEyCrLP14SJApY5WyrGluHe8eDKYwIgLrxA
uqe6ekvgy/ND3jyo/UeTcBBTsTZjEKQiFCUgong=
-----END CERTIFICATE-----
""";

    private static final String RUNNER = """
-----BEGIN CERTIFICATE-----
MIIBzDCCAXKgAwIBAgIIMqhs6676AHUwCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
ZWxtb3Mtcm9vdC1jYTAgFw0yNjA4MTkwOTQyMDZaGA8yMTI2MDcyNjA5NDIwNlow
GDEWMBQGA1UEAxMNcnVubmVyLW5vZGUtMTBZMBMGByqGSM49AgEGCCqGSM49AwEH
A0IABBc4spjCgtk+jNlt+GHbu3uS4lLmvYiSP8HBROolUcsw5QpE1jxJSQl29kN/
ET+Ar8Gul6DbeowgBNc0ISL3ZEajgaMwgaAwHQYDVR0OBBYEFJ6hPZfNnJmS3YWE
WQLiMllLFuEwMD4GA1UdEQQ3MDWGM3NwaWZmZTovL2VsbW9zLmludGVybmFsL25z
L3J1bm5lcnMvc2EvcnVubmVyLW5vZGUtMTAJBgNVHRMEAjAAMB8GA1UdIwQYMBaA
FAOkMz9lU06m4mBhkLNt+bxxr7FTMBMGA1UdJQQMMAoGCCsGAQUFBwMCMAoGCCqG
SM49BAMDA0gAMEUCICKOJrRajoHm9XJsi+RvXFF2okIN7PCXWcPfCgtaMMvMAiEA
m/Fzw3MmNQt07WdHGpdtJjYn0iDsMHMr1k7qnUD1D+8=
-----END CERTIFICATE-----
""";

    private static final String IMPOSTER = """
-----BEGIN CERTIFICATE-----
MIIBzDCCAXKgAwIBAgIIS9Wzh/UW3RswCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
cm9ndWUtcm9vdC1jYTAgFw0yNjA4MTkwOTQyMDhaGA8yMTI2MDcyNjA5NDIwOFow
GDEWMBQGA1UEAxMNcnVubmVyLW5vZGUtMTBZMBMGByqGSM49AgEGCCqGSM49AwEH
A0IABLYDDPNf9svaw59+zZq0M1/lLn7zML7lVAkyCKXLWScO0TE2hPz+aYbkNGwt
PBd6FX2LGtwJ0aL+tv+dwgUumBejgaMwgaAwHQYDVR0OBBYEFFVtqEVGkwJaLcr2
FF/dRkyIbT2oMD4GA1UdEQQ3MDWGM3NwaWZmZTovL2VsbW9zLmludGVybmFsL25z
L3J1bm5lcnMvc2EvcnVubmVyLW5vZGUtMTAJBgNVHRMEAjAAMB8GA1UdIwQYMBaA
FIHPXaCkNlZijbwUXOIFSca0S/NHMBMGA1UdJQQMMAoGCCsGAQUFBwMCMAoGCCqG
SM49BAMDA0gAMEUCIGC5nntTASi8XwEN6OgMVHyiYjZVb6gAwBbQBHxrPdyFAiEA
sad3O5oJlhiCotP6T1cc6KH65qqCNiVfyfRnArAFQ+8=
-----END CERTIFICATE-----
""";

    private static final String EXPIRED = """
-----BEGIN CERTIFICATE-----
MIIBzTCCAXSgAwIBAgIIX5CUxf0Z8zIwCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
ZWxtb3Mtcm9vdC1jYTAeFw0yNDA2MTAwOTQyMTBaFw0yNDA2MTEwOTQyMTBaMBox
GDAWBgNVBAMTD3J1bm5lci1ub2RlLW9sZDBZMBMGByqGSM49AgEGCCqGSM49AwEH
A0IABPVv5aAgg6d4eH0bW14kJWiT4kbdX2+mcP2YJOc/mVHkrt1nobo4wON3eo2Z
WGMQx1R+3ENJ6lJosCQUOjTfBEejgaUwgaIwHQYDVR0OBBYEFDiI5V/Z98ZcGs/S
OdHMIIcVKlNlMEAGA1UdEQQ5MDeGNXNwaWZmZTovL2VsbW9zLmludGVybmFsL25z
L3J1bm5lcnMvc2EvcnVubmVyLW5vZGUtb2xkMAkGA1UdEwQCMAAwHwYDVR0jBBgw
FoAUA6QzP2VTTqbiYGGQs235vHGvsVMwEwYDVR0lBAwwCgYIKwYBBQUHAwIwCgYI
KoZIzj0EAwMDRwAwRAIgFz2dsaVYYZ1rAZFPXfQ5Q6+oqEG82i++AD218Ka6SqkC
IHzeGj+9Jp4cxhXCR+5sE5RB4KSZmH0H2vOfB+oWlKsz
-----END CERTIFICATE-----
""";

    private static final String NO_EKU = """
-----BEGIN CERTIFICATE-----
MIIBzTCCAXOgAwIBAgIJAMzc72muXiPTMAoGCCqGSM49BAMDMBgxFjAUBgNVBAMT
DWVsbW9zLXJvb3QtY2EwIBcNMjYwODE5MDk0MjEyWhgPMjEyNjA3MjYwOTQyMTJa
MBgxFjAUBgNVBAMTDXJ1bm5lci1ub2RlLTIwWTATBgcqhkjOPQIBBggqhkjOPQMB
BwNCAAREANfxw8Swpo2JWYj6iXbTyyf4KnU/7lCxpJrbs7WokhSCv0R+dNo71oSw
yTPcPgCIpPa6XvqbabCgvnwi7hFjo4GjMIGgMB0GA1UdDgQWBBRGuNsoXaexfZRf
+crzVWCVN8ouMzA+BgNVHREENzA1hjNzcGlmZmU6Ly9lbG1vcy5pbnRlcm5hbC9u
cy9ydW5uZXJzL3NhL3J1bm5lci1ub2RlLTIwCQYDVR0TBAIwADAfBgNVHSMEGDAW
gBQDpDM/ZVNOpuJgYZCzbfm8ca+xUzATBgNVHSUEDDAKBggrBgEFBQcDATAKBggq
hkjOPQQDAwNIADBFAiAApe+CK18smL7k1r71mFTa1kMUwl5/Gb4RZ6tLMpXKxwIh
AIs6YIF1hOHxY4X6E5Wl8R3cMqH6Ich8rnrZ1RNU7ui+
-----END CERTIFICATE-----
""";

    private static final String FOREIGN = """
-----BEGIN CERTIFICATE-----
MIIBtzCCAV6gAwIBAgIIZ6mj33ckdGQwCgYIKoZIzj0EAwMwGDEWMBQGA1UEAxMN
ZWxtb3Mtcm9vdC1jYTAgFw0yNjA4MTkwOTQyMTRaGA8yMTI2MDcyNjA5NDIxNFow
FTETMBEGA1UEAxMKb3RoZXItbm9kZTBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IA
BGGtlA6av+H0mg4WAKowjZYDcUA6okkejok30DqwsFzqP1/5t8BH801MOnRZbVgN
4Kcst+wV1/Ojse70ZkiPN7SjgZIwgY8wHQYDVR0OBBYEFPYw29Xp6FO53TPiGFVv
hv+8UaNCMC0GA1UdEQQmMCSGInNwaWZmZTovL3BhcnRuZXIuZXhhbXBsZS9ucy94
L3NhL3kwCQYDVR0TBAIwADAfBgNVHSMEGDAWgBQDpDM/ZVNOpuJgYZCzbfm8ca+x
UzATBgNVHSUEDDAKBggrBgEFBQcDAjAKBggqhkjOPQQDAwNHADBEAiBksszgd2TE
m0fL2eHlcn16rsEu/xW87JYzmoxWfd1lAQIgMgarhvM7BJDK5kr0GzSOucUUNwTo
XDzdwGHhU0Wi9xk=
-----END CERTIFICATE-----
""";

    // Fixed instant after the fixtures were issued. Passing the instant in rather than reading the
    // system clock is what makes the expiry case deterministic instead of time-bomb flaky.
    private static final long NOW = 1_800_000_000_000L;

    private static List<X509Certificate> chain(String pem) {
        return WorkloadIdentity.parsePem(pem);
    }

    private static WorkloadIdentity.TrustBundle bundle() {
        return new WorkloadIdentity.TrustBundle("elmos.internal", chain(CA));
    }

    @Test void aRunnerCertificateFromTheTrustedCaIsAttested() {
        var verdict = WorkloadIdentity.Verifier.of(bundle()).verify(chain(RUNNER), NOW);
        assertTrue(verdict.attested(), verdict.reason());
        var identity = verdict.identity().orElseThrow();
        assertEquals("elmos.internal", identity.id().trustDomain());
        assertEquals("ns/runners/sa/runner-node-1", identity.id().path());
        assertEquals("spiffe://elmos.internal/ns/runners/sa/runner-node-1", identity.id().uri());
    }

    @Test void anIdenticalIdentitySignedByAnotherCaIsRefused() {
        var verdict = WorkloadIdentity.Verifier.of(bundle()).verify(chain(IMPOSTER), NOW);
        assertFalse(verdict.attested());
        assertTrue(verdict.reason().startsWith("CHAIN_NOT_TRUSTED"), verdict.reason());
        assertTrue(verdict.identity().isEmpty());
    }

    @Test void anExpiredCertificateIsRefusedAtTheVerificationInstant() {
        var verdict = WorkloadIdentity.Verifier.of(bundle()).verify(chain(EXPIRED), NOW);
        assertFalse(verdict.attested());
        assertTrue(verdict.reason().startsWith("CHAIN_NOT_TRUSTED"), verdict.reason());
    }

    @Test void aServerCertificatePresentedAsAClientIdentityIsRefused() {
        var verdict = WorkloadIdentity.Verifier.of(bundle()).verify(chain(NO_EKU), NOW);
        assertFalse(verdict.attested());
        assertEquals("CLIENT_AUTH_EKU_MISSING", verdict.reason());
    }

    @Test void aValidCertificateFromAnotherTrustDomainIsRefused() {
        var verdict = WorkloadIdentity.Verifier.of(bundle()).verify(chain(FOREIGN), NOW);
        assertFalse(verdict.attested());
        assertEquals("TRUST_DOMAIN_MISMATCH", verdict.reason());
    }

    @Test void aRevokedSerialIsRefusedBeforeAnyChainWork() {
        X509Certificate leaf = chain(RUNNER).get(0);
        String serial = leaf.getSerialNumber().toString(16);
        var verifier = new WorkloadIdentity.Verifier(bundle(), Set.of(serial), Optional.empty());
        assertEquals("CERTIFICATE_REVOKED", verifier.verify(chain(RUNNER), NOW).reason());
    }

    @Test void anImplausiblyLongLivedLeafIsRefusedWhenALimitIsConfigured() {
        long oneDay = 24L * 60 * 60 * 1000;
        var strict = new WorkloadIdentity.Verifier(bundle(), Set.of(), Optional.of(oneDay));
        assertEquals("LEAF_LIFETIME_TOO_LONG", strict.verify(chain(RUNNER), NOW).reason());

        long twoCenturies = 200L * 365 * 24 * 60 * 60 * 1000;
        var lenient = new WorkloadIdentity.Verifier(bundle(), Set.of(), Optional.of(twoCenturies));
        assertTrue(lenient.verify(chain(RUNNER), NOW).attested());
    }

    @Test void anEmptyChainIsRefused() {
        assertEquals("NO_CERTIFICATE_PRESENTED",
                WorkloadIdentity.Verifier.of(bundle()).verify(List.of(), NOW).reason());
    }

    @Test void theAttestedWriterIdentityCarriesTheSpiffePathAsTheNodeId() {
        var verifier = WorkloadIdentity.Verifier.of(bundle());
        var verdict = verifier.verify(chain(RUNNER), NOW);
        ActionCache.WriterIdentity writer = verifier.attestedWriter(verdict, "cas-writer");

        assertTrue(writer.attested());
        assertEquals("cas-writer", writer.serviceId());
        assertEquals("elmos.internal", writer.trustDomain());
        assertEquals("ns/runners/sa/runner-node-1", writer.nodeId());
    }

    @Test void anUnattestedVerdictCannotBeTurnedIntoAWriterIdentity() {
        var verifier = WorkloadIdentity.Verifier.of(bundle());
        var rejected = verifier.verify(chain(IMPOSTER), NOW);
        var error = assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> verifier.attestedWriter(rejected, "cas-writer"));
        assertEquals("WRITER_NOT_ATTESTED", error.reason());
    }

    @Test void spiffeIdParsingRejectsMalformedInput() {
        assertThrows(IllegalArgumentException.class, () -> WorkloadIdentity.SpiffeId.parse("https://x/y"));
        assertThrows(IllegalArgumentException.class, () -> WorkloadIdentity.SpiffeId.parse("spiffe:///path"));
        assertThrows(IllegalArgumentException.class, () -> WorkloadIdentity.SpiffeId.parse("spiffe://domain/"));
        assertEquals("d", WorkloadIdentity.SpiffeId.parse("spiffe://d/p").trustDomain());
    }
}
